"""SQLAlchemy engine, session, and table creation."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_async_engine = None
_async_session_factory = None
_sync_engine = None
_sync_session_factory = None


def init_async_db(url: str) -> None:
    global _async_engine, _async_session_factory
    _async_engine = create_async_engine(url, echo=False)
    _async_session_factory = async_sessionmaker(_async_engine, class_=AsyncSession, expire_on_commit=False)


def init_sync_db(url: str) -> None:
    global _sync_engine, _sync_session_factory
    _sync_engine = create_engine(url, echo=False)
    _sync_session_factory = sessionmaker(_sync_engine, class_=Session, expire_on_commit=False)


def get_async_session() -> AsyncSession:
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_async_db() first.")
    return _async_session_factory()


def get_sync_session() -> Session:
    if _sync_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_sync_db() first.")
    return _sync_session_factory()


async def create_tables() -> None:
    if _async_engine is None:
        raise RuntimeError("Database not initialized.")
    async with _async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def create_tables_sync() -> None:
    if _sync_engine is None:
        raise RuntimeError("Database not initialized.")
    Base.metadata.create_all(_sync_engine)
