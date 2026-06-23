
from contract_agent.provider.interface import LLMConfig, LLMProvider, ModelResponse, ToolCall

__all__ = [
    "LLMConfig",
    "LLMProvider",
    "ModelProviderFactory",
    "ModelProviderService",
    "ModelResponse",
    "ProviderRuntimeOptions",
    "ToolCall",
    "create_model_provider_service",
]


def __getattr__(name: str):
    if name in {"ModelProviderFactory", "create_model_provider_service"}:
        from contract_agent.provider.factory import ModelProviderFactory, create_model_provider_service

        exports = {
            "ModelProviderFactory": ModelProviderFactory,
            "create_model_provider_service": create_model_provider_service,
        }
        return exports[name]
    if name in {"ModelProviderService", "ProviderRuntimeOptions"}:
        from contract_agent.provider.service import ModelProviderService, ProviderRuntimeOptions

        exports = {
            "ModelProviderService": ModelProviderService,
            "ProviderRuntimeOptions": ProviderRuntimeOptions,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
