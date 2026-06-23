__all__ = [
    "ActionContext",
    "ActionHandler",
    "ActionReference",
    "ActionRegistry",
    "ActionResult",
    "ChatService",
    "ContractChunker",
    "ContractClassifier",
    "ContractExtractor",
    "ContractParser",
    "QueryKnowledgeAction",
    "ReactTraceStep",
    "ReviewService",
    "RuleEngine",
    "references_to_search_results",
]


def __getattr__(name: str):
    if name == "ChatService":
        from contract_agent.services.chat_service import ChatService

        return ChatService
    if name == "ReviewService":
        from contract_agent.services.review_service import ReviewService

        return ReviewService
    if name == "ContractParser":
        from contract_agent.services.parser import ContractParser

        return ContractParser
    if name == "ContractClassifier":
        from contract_agent.services.classifier import ContractClassifier

        return ContractClassifier
    if name == "ContractExtractor":
        from contract_agent.services.extractor import ContractExtractor

        return ContractExtractor
    if name == "RuleEngine":
        from contract_agent.services.rule_engine import RuleEngine

        return RuleEngine
    if name == "ContractChunker":
        from contract_agent.services.chunker import ContractChunker

        return ContractChunker
    if name in {
        "ActionContext",
        "ActionHandler",
        "ActionReference",
        "ActionRegistry",
        "ActionResult",
        "QueryKnowledgeAction",
        "ReactTraceStep",
        "references_to_search_results",
    }:
        from contract_agent.services import react_runtime

        return getattr(react_runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
