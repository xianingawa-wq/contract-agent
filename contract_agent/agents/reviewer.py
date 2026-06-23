import re

from contract_agent.schemas.review import RiskItem

from contract_agent.provider.client import get_chat_model
from contract_agent.constants.prompts import risk_explain_prompt
from contract_agent.config import ModelRuntimeConfig, Settings


class LLMReviewer:
    def __init__(
        self,
        runtime_settings: Settings | None = None,
        model_config: ModelRuntimeConfig | None = None,
        llm=None,
    ) -> None:
        self.runtime_settings = runtime_settings
        self.model_config = model_config
        self.llm = llm or get_chat_model(
            model_config=model_config, runtime_settings=runtime_settings
        )

    def enrich_risk(
        self,
        risk: RiskItem,
        contract_type: str,
        clause_text: str,
        retrieved_contexts: list[str],
    ) -> RiskItem:
        context_text = "\n\n".join(retrieved_contexts) if retrieved_contexts else "无额外检索上下文"
        chain = risk_explain_prompt | self.llm
        result = chain.invoke(
            {
                "contract_type": contract_type,
                "title": risk.title,
                "risk_domain": risk.risk_domain or "未分类",
                "description": risk.description,
                "evidence": risk.evidence,
                "clause_text": clause_text,
                "retrieved_context": context_text,
            }
        )
        explanation, suggestion = self._parse_sections(result.content)
        risk.ai_explanation = explanation
        if suggestion:
            risk.suggestion = suggestion
        return risk

    def _parse_sections(self, content: str) -> tuple[str, str | None]:
        text = content.strip()
        explanation_match = re.search(r"风险解释[:：]\s*(.+?)(?=\n\s*修改建议[:：]|$)", text, re.S)
        suggestion_match = re.search(r"修改建议[:：]\s*(.+)$", text, re.S)

        explanation = explanation_match.group(1).strip() if explanation_match else text
        suggestion = suggestion_match.group(1).strip() if suggestion_match else None
        return explanation, suggestion
