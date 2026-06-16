import unittest

from sqlalchemy.orm import Session

from contract_agent.runtime import database
from contract_agent.runtime.config import settings


class RuntimeDatabaseTests(unittest.TestCase):
    def tearDown(self):
        database._engine = None
        database._session_factory = None

    def test_session_local_creates_sqlalchemy_session(self):
        original_dsn = settings.postgres_dsn
        try:
            settings.postgres_dsn = "sqlite+pysqlite:///:memory:"
            session = database.SessionLocal()
            try:
                self.assertIsInstance(session, Session)
            finally:
                session.close()
        finally:
            settings.postgres_dsn = original_dsn

    def test_session_scope_commits_and_closes_session(self):
        original_dsn = settings.postgres_dsn
        try:
            settings.postgres_dsn = "sqlite+pysqlite:///:memory:"
            with database.session_scope() as session:
                self.assertIsInstance(session, Session)
        finally:
            settings.postgres_dsn = original_dsn


if __name__ == "__main__":
    unittest.main()
