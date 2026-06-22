__all__ = [
    "ContractEditor",
    "LLMReviewer",
    "legal_ref_agent",
    "parser_agent",
    "redrafter_agent",
    "risk_checker_agent",
]


def __getattr__(name: str):
    if name == "ContractEditor":
        from contract_agent.agents.editor import ContractEditor

        return ContractEditor
    if name == "LLMReviewer":
        from contract_agent.agents.reviewer import LLMReviewer

        return LLMReviewer
    if name in {"legal_ref_agent", "parser_agent", "redrafter_agent", "risk_checker_agent"}:
        from contract_agent.agents import workers

        return getattr(workers, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
