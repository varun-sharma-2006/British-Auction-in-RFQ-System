from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class UTCDateTime(TypeDecorator):
    """Timezone-aware timestamp that always round-trips as UTC.

    Stored as TIMESTAMPTZ on PostgreSQL. On SQLite (used by the test suite)
    the tzinfo is dropped by the driver, so we re-attach UTC on the way out.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; pass timezone-aware values")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    # Behind a transaction-mode pooler (PgBouncer, e.g. Neon's "-pooler" host) a server-side prepared
    # statement can land on a different backend connection, so turn psycopg's auto-prepare off there.
    connect_args = {"prepare_threshold": None} if "pooler" in url else {}
    # pool_recycle: serverless Postgres (Neon) suspends when idle and drops connections.
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10, pool_recycle=300,
                         connect_args=connect_args)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
