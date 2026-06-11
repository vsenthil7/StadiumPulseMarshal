"""SQLAlchemy async engine, session factory and ORM tables.

Pydantic domain objects are persisted as JSON documents keyed by id. This keeps
the mapping thin and faithful to the domain while providing real, queryable,
durable storage (SQLite by default; any SQLAlchemy async URL works).
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class IncidentRow(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    venue_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)
    document: Mapped[dict] = mapped_column(JSON)


class RemediationRow(Base):
    __tablename__ = "remediations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, index=True)
    document: Mapped[dict] = mapped_column(JSON)


class AuditRow(Base):
    __tablename__ = "audit"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document: Mapped[dict] = mapped_column(JSON)


class NotificationRow(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    incident_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)
    document: Mapped[dict] = mapped_column(JSON)


class BudgetRow(Base):
    __tablename__ = "error_budgets"
    slo_id: Mapped[str] = mapped_column(String, primary_key=True)
    document: Mapped[dict] = mapped_column(JSON)


class Database:
    """Holds the engine + session factory and creates tables on init."""

    def __init__(self, url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(url, future=True)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    def session(self) -> AsyncSession:
        return self._session_factory()

    async def dispose(self) -> None:
        await self._engine.dispose()
