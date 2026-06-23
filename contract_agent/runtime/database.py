from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from contract_agent.config import Settings, settings_snapshot

_engine: Engine | None = None
_engine_dsn: str | None = None
_session_factory: sessionmaker[Session] | None = None
_session_factory_dsn: str | None = None


def _resolve_dsn(runtime_settings: Settings | None = None, dsn: str | None = None) -> str:
    active_dsn = dsn or (runtime_settings or settings_snapshot()).postgres_dsn
    if not active_dsn:
        raise RuntimeError("POSTGRES_DSN 未配置，无法初始化 PostgreSQL 引擎。")
    return active_dsn


def get_engine(runtime_settings: Settings | None = None, *, dsn: str | None = None) -> Engine:
    active_dsn = _resolve_dsn(runtime_settings, dsn)

    global _engine, _engine_dsn, _session_factory, _session_factory_dsn
    if _engine is None or _engine_dsn != active_dsn:
        _engine = create_engine(
            active_dsn,
            pool_pre_ping=True,
            future=True,
        )
        _engine_dsn = active_dsn
        _session_factory = None
        _session_factory_dsn = None
    return _engine


def get_session_factory(
    runtime_settings: Settings | None = None,
    *,
    dsn: str | None = None,
) -> sessionmaker[Session]:
    active_dsn = _resolve_dsn(runtime_settings, dsn)

    global _session_factory, _session_factory_dsn
    if _session_factory is None or _session_factory_dsn != active_dsn:
        _session_factory = sessionmaker(
            bind=get_engine(dsn=active_dsn),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        _session_factory_dsn = active_dsn
    return _session_factory


def SessionLocal(runtime_settings: Settings | None = None, *, dsn: str | None = None) -> Session:
    return get_session_factory(runtime_settings, dsn=dsn)()


@contextmanager
def session_scope(runtime_settings: Settings | None = None, *, dsn: str | None = None) -> Iterator[Session]:
    session = SessionLocal(runtime_settings, dsn=dsn)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
