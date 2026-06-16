import unittest

from contract_agent.db import models as legacy_models
from contract_agent.knowledge import models as knowledge_models
from contract_agent.knowledge import repository as knowledge_repository
from contract_agent.rag import knowledge_chunk_repository as legacy_repository


class KnowledgePersistenceTests(unittest.TestCase):
    def test_db_models_reexport_knowledge_models(self):
        self.assertIs(legacy_models.Base, knowledge_models.Base)
        self.assertIs(legacy_models.KnowledgeChunkModel, knowledge_models.KnowledgeChunkModel)

    def test_rag_repository_reexports_knowledge_repository(self):
        self.assertIs(legacy_repository.KnowledgeChunkRepository, knowledge_repository.KnowledgeChunkRepository)


if __name__ == "__main__":
    unittest.main()
