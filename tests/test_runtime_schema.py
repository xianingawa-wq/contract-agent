import unittest

from sqlalchemy import inspect

from contract_agent.db.init_db import ensure_postgres_schema
from contract_agent.runtime import database
from contract_agent.runtime.config import settings
from contract_agent.runtime.schema import ensure_runtime_schema


class RuntimeSchemaTests(unittest.TestCase):
    def tearDown(self):
        database._engine = None
        database._session_factory = None

    def test_db_init_reexports_runtime_schema_initializer(self):
        self.assertIs(ensure_postgres_schema, ensure_runtime_schema)

    def test_runtime_schema_creates_knowledge_and_memory_tables(self):
        original_dsn = settings.postgres_dsn
        try:
            settings.postgres_dsn = "sqlite+pysqlite:///:memory:"
            ensure_runtime_schema()

            table_names = set(inspect(database.get_engine()).get_table_names())
        finally:
            settings.postgres_dsn = original_dsn

        self.assertIn("knowledge_chunks", table_names)
        self.assertIn("agent_outputs", table_names)


if __name__ == "__main__":
    unittest.main()
