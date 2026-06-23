import unittest

from sqlalchemy import inspect

from contract_agent.runtime import database
from contract_agent.runtime.config import Settings
from contract_agent.runtime.schema import ensure_runtime_schema


class RuntimeSchemaTests(unittest.TestCase):
    def tearDown(self):
        database._engine = None
        database._engine_dsn = None
        database._session_factory = None
        database._session_factory_dsn = None

    def test_runtime_schema_creates_knowledge_and_memory_tables(self):
        runtime_settings = Settings(postgres_dsn="sqlite+pysqlite:///:memory:")
        ensure_runtime_schema(runtime_settings)

        table_names = set(inspect(database.get_engine(runtime_settings)).get_table_names())

        self.assertIn("knowledge_chunks", table_names)
        self.assertIn("agent_outputs", table_names)


if __name__ == "__main__":
    unittest.main()
