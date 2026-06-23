import unittest
from tempfile import TemporaryDirectory

from sqlalchemy.orm import Session

from contract_agent.runtime import database
from contract_agent.runtime.config import Settings, temporary_settings


class RuntimeDatabaseTests(unittest.TestCase):
    def tearDown(self):
        database._engine = None
        database._engine_dsn = None
        database._session_factory = None
        database._session_factory_dsn = None

    def test_session_local_creates_sqlalchemy_session(self):
        with temporary_settings(postgres_dsn="sqlite+pysqlite:///:memory:"):
            session = database.SessionLocal()
            try:
                self.assertIsInstance(session, Session)
            finally:
                session.close()

    def test_session_scope_commits_and_closes_session(self):
        runtime_settings = Settings(postgres_dsn="sqlite+pysqlite:///:memory:")

        with database.session_scope(runtime_settings) as session:
            self.assertIsInstance(session, Session)

    def test_engine_cache_is_partitioned_by_dsn(self):
        with TemporaryDirectory() as tmpdir:
            first = database.get_engine(dsn="sqlite+pysqlite:///:memory:")
            second = database.get_engine(dsn=f"sqlite+pysqlite:///{tmpdir}/database-test-cache.db")

            self.assertIsNot(first, second)

    def test_session_factory_cache_is_partitioned_by_dsn(self):
        with TemporaryDirectory() as tmpdir:
            first = database.get_session_factory(dsn="sqlite+pysqlite:///:memory:")
            second = database.get_session_factory(dsn=f"sqlite+pysqlite:///{tmpdir}/database-test-cache.db")

            self.assertIsNot(first, second)


if __name__ == "__main__":
    unittest.main()
