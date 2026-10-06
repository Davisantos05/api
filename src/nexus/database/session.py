"""Engine and session construction isolated from application code."""

import os
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./nexus.db"


def create_database_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine compatible with SQLite and PostgreSQL URLs."""

    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    engine = create_engine(database_url, echo=echo, connect_args=connect_args)
    if database_url.startswith("sqlite"):
        event.listen(
            engine,
            "connect",
            lambda connection, _record: connection.execute("PRAGMA foreign_keys=ON"),
        )
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build short-lived SQLAlchemy 2.x sessions."""

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide factory configured from the environment."""

    database_url = os.getenv("NEXUS_DATABASE_URL", DEFAULT_DATABASE_URL)
    return create_session_factory(create_database_engine(database_url))
