from contract_agent.provider.impl.openai.embeddings import OpenAIEmbeddings


class DashScopeEmbeddings(OpenAIEmbeddings):
    """DashScope embeddings use the OpenAI-compatible embeddings API shape."""
