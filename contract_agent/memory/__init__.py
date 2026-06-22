__all__ = [
    "AgentOutputRecord",
    "AgentOutputRepository",
    "Base",
    "ColdLayer",
    "HotLayer",
    "MemoryManager",
    "WarmLayer",
]


def __getattr__(name: str):
    if name in {"AgentOutputRecord", "Base"}:
        from contract_agent.memory.models import AgentOutputRecord, Base

        return {"AgentOutputRecord": AgentOutputRecord, "Base": Base}[name]
    if name == "AgentOutputRepository":
        from contract_agent.memory.repository import AgentOutputRepository

        return AgentOutputRepository
    if name == "ColdLayer":
        from contract_agent.memory.cold_store import ColdLayer

        return ColdLayer
    if name == "HotLayer":
        from contract_agent.memory.hot_store import HotLayer

        return HotLayer
    if name == "MemoryManager":
        from contract_agent.memory.manager import MemoryManager

        return MemoryManager
    if name == "WarmLayer":
        from contract_agent.memory.warm_store import WarmLayer

        return WarmLayer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
