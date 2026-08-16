"""Engine / session-factory setup. Business logic never imports this module
directly -- it receives a `session_factory` through its constructor instead,
so it can be tested against an in-memory database without monkeypatching a
global. See docs/postmortem/PROJECT_POSTMORTEM.md item 15."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from quantum_tick.persistence.models import Base


def make_session_factory(database_url: str) -> sessionmaker:
    if database_url.startswith("sqlite:///./"):
        db_path = Path(database_url.replace("sqlite:///./", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
