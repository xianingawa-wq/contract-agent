import unittest

from contract_agent.knowledge import models as knowledge_models
from contract_agent.knowledge import repository as knowledge_repository


class KnowledgePersistenceTests(unittest.TestCase):
    def test_knowledge_models_are_canonical(self):
        self.assertEqual(knowledge_models.KnowledgeChunkModel.__tablename__, "knowledge_chunks")

    def test_knowledge_repository_is_canonical_repository_path(self):
        self.assertTrue(hasattr(knowledge_repository, "KnowledgeChunkRepository"))


class KnowledgeRagPackageTests(unittest.TestCase):
    def test_knowledge_rag_contains_retrieval_modules(self):
        from contract_agent.knowledge.rag import retriever, vector_store

        self.assertTrue(hasattr(retriever, "ContractKnowledgeRetriever"))
        self.assertTrue(hasattr(vector_store, "load_vector_store"))


if __name__ == "__main__":
    unittest.main()
