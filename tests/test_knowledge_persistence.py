import unittest

from contract_agent.db import models as legacy_models
from contract_agent.knowledge import models as knowledge_models
from contract_agent.knowledge import repository as knowledge_repository


class KnowledgePersistenceTests(unittest.TestCase):
    def test_db_models_reexport_knowledge_models(self):
        self.assertIs(legacy_models.Base, knowledge_models.Base)
        self.assertIs(legacy_models.KnowledgeChunkModel, knowledge_models.KnowledgeChunkModel)

    def test_knowledge_repository_is_canonical_repository_path(self):
        self.assertTrue(hasattr(knowledge_repository, "KnowledgeChunkRepository"))


class KnowledgeRagPackageTests(unittest.TestCase):
    def test_knowledge_rag_contains_retrieval_modules(self):
        from contract_agent.knowledge.rag import retriever, vector_store

        self.assertTrue(hasattr(retriever, "ContractKnowledgeRetriever"))
        self.assertTrue(hasattr(vector_store, "load_vector_store"))


if __name__ == "__main__":
    unittest.main()
