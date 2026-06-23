from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from contract_agent.config import Settings, settings_snapshot
from contract_agent.config import RetrievalConfig
from contract_agent.orchestration.protocol import AgentFinding, AgentOutput, AgentStatus
from contract_agent.services.rule_engine import RuleEngine


def _runtime_settings(ctx: dict[str, Any]) -> Settings:
    value = ctx.get("runtime_settings")
    if isinstance(value, Settings):
        return value
    return settings_snapshot()


# ---------------------------------------------------------------------------
# JSON parsing helper — extract structured data from LLM responses
# ---------------------------------------------------------------------------

def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling markdown fences and trailing commas."""
    text = raw.strip()
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        text = m.group(0)
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Agent 1: Parser — LLM-driven contract parsing with rule-based preprocessing
# ---------------------------------------------------------------------------

def parser_agent(ctx: dict[str, Any]) -> AgentOutput:
    contract_text: str = ctx.get("contract_text", "")
    contract_type: str | None = ctx.get("contract_type")
    our_side: str = ctx.get("our_side", "甲方")

    from contract_agent.constants.agent_prompts import parser_prompt
    from contract_agent.provider.client import get_chat_model
    from contract_agent.services.parser import ContractParser
    from contract_agent.services.classifier import ContractClassifier

    # Rule-based preprocessing (kept as LLM input context)
    parser = ContractParser()
    classifier = ContractClassifier()
    document = parser.parse_text(contract_text)
    detected_type = contract_type or classifier.classify(contract_text)

    preprocessed = []
    for chunk in document.clause_chunks[:40]:
        preprocessed.append({
            "clause_no": chunk.clause_no,
            "section_title": chunk.section_title,
            "text": chunk.source_text[:120],
        })

    llm = get_chat_model()
    chain = parser_prompt | llm
    # Truncate contract text for LLM — full text kept in ctx for downstream agents
    llm_text = contract_text if len(contract_text) <= 1500 else contract_text[:1500] + f"\n…(全文共 {len(contract_text)} 字符)…"
    result = chain.invoke({
        "contract_text": llm_text,
        "preprocessed_clauses": json.dumps(preprocessed, ensure_ascii=False),
    })

    parsed = _parse_llm_json(result.content)
    clauses = parsed.get("clauses", [])
    if not clauses and preprocessed:
        # Fallback: use preprocessed clauses if LLM returned nothing
        clauses = [{"clause_no": c["clause_no"], "section_title": c["section_title"], "type": "其他", "summary": c["text"][:50]} for c in preprocessed]

    return AgentOutput(
        agent_id="parser",
        status=AgentStatus.COMPLETED,
        input_summary=f"解析合同，共 {len(clauses)} 个条款",
        structured_data={
            "parsed_clauses": clauses,
            "detected_contract_type": parsed.get("contract_type", detected_type),
            "extracted_fields": {
                "parties": parsed.get("parties", {}),
                "subject_matter": parsed.get("subject_matter", ""),
                "total_amount": parsed.get("total_amount", ""),
                "key_dates": parsed.get("key_dates", []),
                "risk_areas": parsed.get("risk_areas", []),
            },
            "our_side": our_side,
        },
        token_used=0,
        llm_calls=1,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Agent 2: Risk Checker — LLM as primary + rule engine as hints
# ---------------------------------------------------------------------------

def risk_checker_agent(ctx: dict[str, Any]) -> AgentOutput:
    clauses: list[dict] = ctx.get("parsed_clauses", [])
    runtime_settings = _runtime_settings(ctx)
    contract_type: str = ctx.get("detected_contract_type", runtime_settings.default_contract_type)
    our_side: str = ctx.get("our_side", "甲方")
    contract_text: str = ctx.get("contract_text", "")

    from contract_agent.constants.agent_prompts import risk_checker_prompt
    from contract_agent.provider.client import get_chat_model
    from contract_agent.schemas.document import ClauseChunk, DocumentMetadata, ParsedDocument

    # Rule engine as supplementary hints
    rule_engine = RuleEngine()
    rule_hints = []
    try:
        dummy_doc = ParsedDocument(
            raw_text=contract_text,
            metadata=DocumentMetadata(
                doc_id="multi-agent-review",
                file_name="contract.txt",
                file_type="txt",
                source_path="multi-agent",
            ),
            spans=[],
            clause_chunks=[
                ClauseChunk(
                    chunk_id=c.get("clause_no", str(i)),
                    chunk_level="clause",
                    clause_no=c.get("clause_no"),
                    section_title=c.get("section_title", ""),
                    source_text=c.get("summary", c.get("text", "")),
                    start_offset=0,
                    end_offset=len(c.get("summary", c.get("text", ""))),
                )
                for i, c in enumerate(clauses)
            ],
        )
        risks = rule_engine.check(contract_type, dummy_doc)
        rule_hints = [{"title": r.title, "severity": r.severity, "clause_no": r.clause_no, "description": r.description, "suggestion": r.suggestion} for r in risks]
    except Exception:
        pass

    llm = get_chat_model()
    chain = risk_checker_prompt | llm
    result = chain.invoke({
        "contract_type": contract_type,
        "our_side": our_side,
        "parsed_clauses": json.dumps(clauses, ensure_ascii=False),
        "rule_engine_hints": json.dumps(rule_hints, ensure_ascii=False),
    })

    parsed = _parse_llm_json(result.content)
    findings_data = parsed.get("findings", [])

    findings = []
    for fd in findings_data:
        findings.append(AgentFinding(
            clause=fd.get("clause", ""),
            risk=fd.get("risk", "info"),
            summary=fd.get("summary", ""),
            suggestion=fd.get("suggestion"),
            detail={"title": fd.get("title", ""), "party_impact": fd.get("party_impact", "中性")},
        ))

    return AgentOutput(
        agent_id="risk_checker",
        status=AgentStatus.COMPLETED,
        input_summary=f"审查 {len(clauses)} 个条款，发现 {len(findings)} 项风险",
        findings=findings,
        structured_data={"risk_findings": [f.model_dump() for f in findings]},
        next_agent_hints={
            "has_high_risk": any(f.risk == "high" for f in findings),
            "focus_clauses": [f.clause for f in findings if f.risk == "high"][:3],
        },
        token_used=0,
        llm_calls=1,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Agent 3: Legal Reference — vector retrieval + LLM analysis
# ---------------------------------------------------------------------------

def legal_ref_agent(ctx: dict[str, Any]) -> AgentOutput:
    findings_data: list[dict] = ctx.get("risk_findings", [])
    runtime_settings = _runtime_settings(ctx)
    retrieval_config = RetrievalConfig.from_settings(runtime_settings)
    contract_type: str = ctx.get("detected_contract_type", runtime_settings.default_contract_type)

    if not findings_data:
        return AgentOutput(
            agent_id="legal_ref",
            status=AgentStatus.SKIPPED,
            input_summary="无风险发现，跳过法条引用",
            llm_calls=0,
        )

    from contract_agent.constants.agent_prompts import legal_ref_prompt
    from contract_agent.provider.client import get_chat_model
    from contract_agent.knowledge.rag.vector_store import load_vector_store
    from contract_agent.knowledge.rag.retriever import ContractKnowledgeRetriever

    # Vector retrieval (kept as LLM input)
    retrieved_docs = []
    try:
        vector_store = load_vector_store(runtime_settings.knowledge_vector_store_dir, runtime_settings=runtime_settings)
        retriever = ContractKnowledgeRetriever(vector_store, retrieval_config=retrieval_config)
        for i, fd in enumerate(findings_data[:5]):
            query = f"{contract_type} {fd.get('summary', '')}"
            docs = retriever.retrieve_documents_with_rerank(
                query=query,
                fetch_k=retrieval_config.fetch_k,
                final_k=min(retrieval_config.final_k, 2),
            )
            for doc in docs:
                retrieved_docs.append({
                    "finding_index": i,
                    "finding_summary": fd.get("summary", "")[:80],
                    "source": doc.metadata.get("title", "未知"),
                    "article": doc.metadata.get("article_label", ""),
                    "snippet": doc.page_content[:300],
                })
    except Exception:
        return AgentOutput(
            agent_id="legal_ref",
            status=AgentStatus.SKIPPED,
            input_summary="知识库不可用，跳过法条引用",
            llm_calls=0,
        )

    if not retrieved_docs:
        return AgentOutput(
            agent_id="legal_ref",
            status=AgentStatus.SKIPPED,
            input_summary="未检索到相关法条",
            llm_calls=0,
        )

    llm = get_chat_model()
    chain = legal_ref_prompt | llm
    result = chain.invoke({
        "contract_type": contract_type,
        "risk_findings": json.dumps(findings_data[:5], ensure_ascii=False),
        "retrieved_docs": json.dumps(retrieved_docs, ensure_ascii=False),
    })

    parsed = _parse_llm_json(result.content)
    refs = parsed.get("refs", [])

    return AgentOutput(
        agent_id="legal_ref",
        status=AgentStatus.COMPLETED if refs else AgentStatus.SKIPPED,
        input_summary=f"检索并分析 {len(refs)} 条法律引用",
        structured_data={"legal_refs": refs},
        token_used=0,
        llm_calls=1,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Agent 4: Redrafter — LLM-based rewrite generation
# ---------------------------------------------------------------------------

def redrafter_agent(ctx: dict[str, Any]) -> AgentOutput:
    findings_data: list[dict] = ctx.get("risk_findings", [])
    legal_refs: list[dict] = ctx.get("legal_refs", [])
    contract_text: str = ctx.get("contract_text", "")

    if not findings_data:
        return AgentOutput(
            agent_id="redrafter",
            status=AgentStatus.SKIPPED,
            input_summary="无风险发现，跳过改写",
            llm_calls=0,
        )

    from contract_agent.constants.agent_prompts import redrafter_prompt
    from contract_agent.provider.client import get_chat_model

    findings_with_refs = []
    for i, fd in enumerate(findings_data):
        refs_for_finding = [r for r in legal_refs if r.get("finding_index") == i]
        findings_with_refs.append({
            "index": i,
            "clause": fd.get("clause", ""),
            "risk": fd.get("risk", "info"),
            "summary": fd.get("summary", ""),
            "suggestion": fd.get("suggestion", ""),
            "legal_refs": refs_for_finding,
        })

    llm = get_chat_model()
    chain = redrafter_prompt | llm
    result = chain.invoke({
        "risk_findings_with_refs": json.dumps(findings_with_refs, ensure_ascii=False),
        "contract_text": contract_text,
    })

    parsed = _parse_llm_json(result.content)
    suggestions = parsed.get("suggestions", [])

    return AgentOutput(
        agent_id="redrafter",
        status=AgentStatus.COMPLETED if suggestions else AgentStatus.SKIPPED,
        input_summary=f"生成 {len(suggestions)} 条改写建议",
        structured_data={"redraft_suggestions": suggestions},
        token_used=0,
        llm_calls=1,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
