from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from contract_agent.logger.audit import AuditLogger, get_audit_logger
from contract_agent.config import Settings, settings_snapshot
from contract_agent.config import RetrievalConfig
from contract_agent.schemas.review import (
    HealthResponse,
    KnowledgeReference,
    ReviewReport,
    ReviewRequest,
    ReviewResponse,
    ReviewSummary,
)
from contract_agent.trace.tokens import TokenTrace
from contract_agent.services.classifier import ContractClassifier
from contract_agent.services.extractor import ContractExtractor
from contract_agent.services.rule_engine import RuleEngine

if TYPE_CHECKING:
    from contract_agent.knowledge.rag.retriever import ContractKnowledgeRetriever


class ReviewService:
    def __init__(
        self,
        audit_logger: AuditLogger | None = None,
        runtime_settings: Settings | None = None,
        parser: Any | None = None,
    ) -> None:
        self.settings = runtime_settings or settings_snapshot()
        self.retrieval_config = RetrievalConfig.from_settings(self.settings)
        self.classifier = ContractClassifier()
        self.extractor = ContractExtractor()
        self._parser = parser
        self.rule_engine = RuleEngine()
        self._llm_reviewer = None
        self._knowledge_retriever = None
        self.audit_logger = (audit_logger or get_audit_logger()).with_prefix("[Service][Review]", scope="review")

    def health(self) -> HealthResponse:
        from contract_agent.knowledge.rag.vector_store import is_knowledge_base_ready

        return HealthResponse(
            status="ok",
            llm_configured=bool(self.settings.chat_api_key and self._llm_reviewer_available()),
            knowledge_base_ready=is_knowledge_base_ready(self.settings.knowledge_vector_store_dir, runtime_settings=self.settings),
        )

    def review(self, payload: ReviewRequest) -> ReviewResponse:
        with self.audit_logger.trace(
            "review",
            entrypoint="text",
            contract_type=payload.contract_type,
            our_side=payload.our_side,
            text_length=len(payload.contract_text),
        ):
            with self.audit_logger.span("review.parse", parser="text"):
                document = self.parser.parse_text(payload.contract_text)
            return self._review_document(document=document, contract_type=payload.contract_type, our_side=payload.our_side)

    def review_file(self, file_name: str, content: bytes, contract_type: str | None, our_side: str) -> ReviewResponse:
        with self.audit_logger.trace(
            "review",
            entrypoint="file",
            contract_type=contract_type,
            our_side=our_side,
            file_name=file_name,
            content_bytes=len(content),
        ):
            with self.audit_logger.span("review.parse", parser="file", file_name=file_name):
                document = self.parser.parse_bytes(file_name, content)
            return self._review_document(document=document, contract_type=contract_type, our_side=our_side)

    def parse_file(self, file_name: str, content: bytes):
        return self.parser.parse_bytes(file_name, content)

    @property
    def parser(self):
        if self._parser is None:
            from contract_agent.services.parser import ContractParser

            self._parser = ContractParser()
        return self._parser

    def _review_document(self, document, contract_type: str | None, our_side: str) -> ReviewResponse:
        contract_text = document.raw_text
        with self.audit_logger.span("review.classify"):
            detected_contract_type = contract_type or self.classifier.classify(contract_text)
        self.audit_logger.emit(
            "review.started",
            contract_type=detected_contract_type or self.settings.default_contract_type,
            our_side=our_side,
            text_length=len(contract_text),
            source_title=document.metadata.title or document.metadata.file_name,
        )

        try:
            trace = TokenTrace()
            trace.add_input("contract_text", contract_text)
            with self.audit_logger.span("review.dependencies"):
                llm_reviewer = self._require_llm_reviewer()
                knowledge_retriever = self._require_knowledge_retriever()
            with self.audit_logger.span("review.extract"):
                extracted_fields = self.extractor.extract(contract_text)
            with self.audit_logger.span("review.rules"):
                risks = self.rule_engine.check(detected_contract_type, document)
            self.audit_logger.emit(
                "review.rules.completed",
                contract_type=detected_contract_type or self.settings.default_contract_type,
                risk_count=len(risks),
            )
            risks = self._apply_party_context(risks, our_side)
            with self.audit_logger.span("review.enrich", risk_count=len(risks)):
                risks = self._enrich_risks(
                    risks,
                    document,
                    detected_contract_type,
                    llm_reviewer,
                    knowledge_retriever,
                    token_trace=trace,
                )
            with self.audit_logger.span("review.report", risk_count=len(risks)):
                report = self._build_report(risks, detected_contract_type, document.metadata.title or document.metadata.file_name)
            trace_summary = trace.summary()

            response = ReviewResponse(
                summary=ReviewSummary(
                    contract_type=detected_contract_type or self.settings.default_contract_type,
                    overall_risk=self._overall_risk(risks),
                    risk_count=len(risks),
                ),
                extracted_fields=extracted_fields,
                risks=risks,
                report=report,
                trace=trace_summary,
            )
            self.audit_logger.emit(
                "review.completed",
                contract_type=response.summary.contract_type,
                overall_risk=response.summary.overall_risk,
                risk_count=response.summary.risk_count,
                estimated_total_tokens=trace_summary.estimated_total_tokens,
            )
            return response
        except Exception as exc:
            self.audit_logger.emit(
                "review.failed",
                contract_type=detected_contract_type or self.settings.default_contract_type,
                error=str(exc),
            )
            raise

    def _overall_risk(self, risks: list) -> str:
        severities = {risk.severity for risk in risks}
        if "high" in severities:
            return "high"
        if "medium" in severities:
            return "medium"
        if "low" in severities:
            return "low"
        return "info"

    def _require_llm_reviewer(self):
        if not self.settings.chat_api_key:
            raise RuntimeError("CHAT_API_KEY 或 LLM_API_KEY 未配置，当前交付要求必须启用 LLM。QWEN_API_KEY 仍可作为兼容别名。")
        if self._llm_reviewer is None:
            try:
                from contract_agent.agents.reviewer import LLMReviewer

                self._llm_reviewer = LLMReviewer()
            except Exception as exc:
                raise RuntimeError(f"LLM 初始化失败：{exc}") from exc
        return self._llm_reviewer

    def _llm_reviewer_available(self) -> bool:
        try:
            from contract_agent.agents.reviewer import LLMReviewer  # noqa: F401

            return True
        except Exception:
            return False

    def _require_knowledge_retriever(self) -> ContractKnowledgeRetriever:
        if self._knowledge_retriever is None:
            try:
                from contract_agent.knowledge.rag.retriever import ContractKnowledgeRetriever
                from contract_agent.knowledge.rag.vector_store import load_vector_store

                vector_store = load_vector_store(self.settings.knowledge_vector_store_dir, runtime_settings=self.settings)
            except Exception as exc:
                raise RuntimeError(f"法律知识库加载失败：{exc}") from exc
            self._knowledge_retriever = ContractKnowledgeRetriever(
                vector_store,
                retrieval_config=self.retrieval_config,
                audit_logger=self.audit_logger,
            )
        return self._knowledge_retriever

    def _apply_party_context(self, risks: list, our_side: str) -> list:
        filtered = []
        for risk in risks:
            if risk.rule_id == "JUR_001" and our_side in risk.evidence:
                continue
            filtered.append(risk)
        return filtered

    def _enrich_risks(
        self,
        risks: list,
        document,
        contract_type: str,
        llm_reviewer,
        knowledge_retriever,
        token_trace: TokenTrace | None = None,
    ) -> list:
        for risk in risks:
            clause_text = self._find_clause_text(document, risk)
            query = f"{contract_type} {risk.title} {risk.risk_domain or ''} {risk.evidence} {clause_text}"
            retrieved_docs = knowledge_retriever.retrieve_documents_with_rerank(
                query=query,
                fetch_k=self.retrieval_config.fetch_k,
                final_k=self.retrieval_config.final_k,
            )
            retrieved_contexts = [doc.page_content for doc in retrieved_docs]
            if token_trace is not None:
                token_trace.add_input("risk_enrichment_context", "\n".join([query, clause_text, *retrieved_contexts]))
            risk.basis_sources = [
                KnowledgeReference(
                    source_title=doc.metadata.get("title") or doc.metadata.get("doc_name") or "未命名知识片段",
                    article_label=doc.metadata.get("article_label"),
                    snippet=doc.page_content[:240],
                    source_path=doc.metadata.get("source_path"),
                )
                for doc in retrieved_docs
            ]
            llm_reviewer.enrich_risk(risk, contract_type, clause_text, retrieved_contexts)
            if token_trace is not None:
                token_trace.add_output("risk_enrichment_output", "\n".join(filter(None, [risk.ai_explanation, risk.suggestion])))
            self.audit_logger.emit(
                "review.risk.enriched",
                rule_id=risk.rule_id,
                title=risk.title,
                severity=risk.severity,
                basis_sources=len(risk.basis_sources),
            )
        return risks

    def _build_report(self, risks: list, contract_type: str, document_title: str) -> ReviewReport:
        if risks:
            overview = f"《{document_title}》已按{contract_type}完成校审，共识别出 {len(risks)} 项风险，整体风险等级为 {self._overall_risk(risks)}。"
            key_findings = [f"{risk.title}：{risk.evidence}" for risk in risks[:5]]
            next_actions = [risk.suggestion for risk in risks[:5]]
        else:
            overview = f"《{document_title}》已按{contract_type}完成校审，暂未识别出明确风险。"
            key_findings = []
            next_actions = ["建议结合业务背景继续人工复核关键商务条款。"]

        return ReviewReport(
            generated_at=datetime.now(timezone.utc),
            overview=overview,
            key_findings=key_findings,
            next_actions=next_actions,
        )

    def _find_clause_text(self, document, risk) -> str:
        for chunk in document.clause_chunks:
            if chunk.clause_no == risk.clause_no and chunk.section_title == risk.section_title:
                return chunk.source_text
        return risk.evidence
