from __future__ import annotations

import os

from sqlalchemy import Engine
from sqlmodel import Session, create_engine


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return database_url


def create_database_engine() -> Engine:
    return create_engine(get_database_url(), pool_pre_ping=True)


def create_session() -> Session:
    return Session(create_database_engine())
