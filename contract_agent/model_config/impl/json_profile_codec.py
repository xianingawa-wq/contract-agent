from __future__ import annotations

from contract_agent.model_config.interface import ModelEndpointConfig, ModelRole, ModelRuntimeConfig


class JsonModelProfileCodec:
    def decode(self, raw: dict[str, object], fallback: ModelRuntimeConfig) -> ModelRuntimeConfig:
        if any(key in raw for key in (ModelRole.CHAT.value, ModelRole.EMBEDDING.value, ModelRole.RERANK.value)):
            return ModelRuntimeConfig(
                chat=self._endpoint_from_json(raw.get(ModelRole.CHAT.value), fallback.chat),
                embedding=self._endpoint_from_json(raw.get(ModelRole.EMBEDDING.value), fallback.embedding),
                rerank=self._endpoint_from_json(raw.get(ModelRole.RERANK.value), fallback.rerank),
            )
        return self._decode_legacy_profile(raw, fallback)

    def encode(self, config: ModelRuntimeConfig) -> dict[str, object]:
        return {
            ModelRole.CHAT.value: self._endpoint_to_json(config.chat),
            ModelRole.EMBEDDING.value: self._endpoint_to_json(config.embedding),
            ModelRole.RERANK.value: self._endpoint_to_json(config.rerank),
        }

    def _decode_legacy_profile(self, raw: dict[str, object], fallback: ModelRuntimeConfig) -> ModelRuntimeConfig:
        legacy_api_key = str(raw.get("api_key") or "") if raw.get("api_key_configured") else ""
        legacy_endpoint = ModelEndpointConfig(
            role=ModelRole.CHAT,
            provider=str(raw.get("provider") or fallback.chat.provider),
            base_url=str(raw.get("base_url") or fallback.chat.base_url),
            api_key=legacy_api_key or fallback.chat.api_key,
            model=str(raw.get("chat_model") or fallback.chat.model),
        )
        return ModelRuntimeConfig(
            chat=legacy_endpoint,
            embedding=ModelEndpointConfig(
                role=ModelRole.EMBEDDING,
                provider=legacy_endpoint.provider,
                base_url=legacy_endpoint.base_url,
                api_key=legacy_endpoint.api_key,
                model=str(raw.get("embedding_model") or fallback.embedding.model),
            ),
            rerank=fallback.rerank,
        )

    def _endpoint_from_json(self, raw: object, fallback: ModelEndpointConfig) -> ModelEndpointConfig:
        if not isinstance(raw, dict):
            return fallback
        return ModelEndpointConfig(
            role=fallback.role,
            provider=str(raw.get("provider") or fallback.provider),
            base_url=str(raw.get("base_url") or fallback.base_url),
            api_key=str(raw.get("api_key") or fallback.api_key),
            model=str(raw.get("model") or fallback.model),
        )

    def _endpoint_to_json(self, endpoint: ModelEndpointConfig) -> dict[str, object]:
        return {
            "provider": endpoint.provider,
            "base_url": endpoint.base_url,
            "api_key": endpoint.api_key,
            "model": endpoint.model,
        }
