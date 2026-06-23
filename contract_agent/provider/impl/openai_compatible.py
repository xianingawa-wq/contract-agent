from contract_agent.provider.impl.openai.embeddings import OpenAIEmbeddings
from contract_agent.provider.impl.openai.message_codec import (
    with_strict_objects as _with_strict_objects,
)
from contract_agent.provider.impl.openai.provider import OpenAIProvider

OpenAICompatibleEmbeddings = OpenAIEmbeddings
OpenAICompatibleProvider = OpenAIProvider

__all__ = ["OpenAICompatibleEmbeddings", "OpenAICompatibleProvider", "_with_strict_objects"]
