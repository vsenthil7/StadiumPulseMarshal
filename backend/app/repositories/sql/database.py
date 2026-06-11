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


class RefreshTokenRow(Base):
    __tablename__ = "refresh_tokens"
    token: Mapped[str] = mapped_column(String, primary_key=True)
    family_id: Mapped[str] = mapped_column(String, index=True)
    subject: Mapped[str] = mapped_column(String, index=True)
    expires_at: Mapped[float] = mapped_column(Float, index=True)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class BudgetRow(Base):
    __tablename__ = "error_budgets"
    slo_id: Mapped[str] = mapped_column(String, primary_key=True)
    document: Mapped[dict] = mapped_column(JSON)


class OutboxRow(Base):
    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[str] = mapped_column(String, index=True)
    document: Mapped[dict] = mapped_column(JSON)


class BurnAckRow(Base):
    __tablename__ = "burn_acks"
    # key = "{slo_id}:{severity}" with a kind discriminator (ack|silence).
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    field: Mapped[str] = mapped_column(String, primary_key=True)
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    document: Mapped[dict] = mapped_column(JSON)


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    resource_type: Mapped[str] = mapped_column(String, index=True)
    resource_id: Mapped[str] = mapped_column(String, index=True)
    actor: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    document: Mapped[dict] = mapped_column(JSON)


class Database:
    """Holds the engine + session factory and creates tables on init."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._engine: AsyncEngine = create_async_engine(url, future=True)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    async def init_schema(self) -> None:
        """Run Alembic ``upgrade head`` when alembic + ini are available
        (production), else fall back to ``create_all`` (tests / minimal env).

        In-memory SQLite can't be migrated by Alembic (it opens a separate
        connection to a distinct in-memory DB), so those always use create_all.
        """
        if ":memory:" in self._url:
            await self.create_all()
            return
        try:
            import asyncio
            import os

            from alembic import command as alembic_cmd
            from alembic.config import Config as AlembicConfig

            here = os.path.dirname(os.path.abspath(__file__))
            backend_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
            ini = os.path.join(backend_root, "alembic.ini")
            if not os.path.exists(ini):
                raise FileNotFoundError(ini)
            cfg = AlembicConfig(ini)
            cfg.set_main_option("script_location", os.path.join(backend_root, "alembic"))
            sync_url = self._url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")
            cfg.set_main_option("sqlalchemy.url", sync_url)
            await asyncio.get_event_loop().run_in_executor(
                None, alembic_cmd.upgrade, cfg, "head")
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(
                "alembic upgrade unavailable (%s); using create_all", exc)
            await self.create_all()

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    def session(self) -> AsyncSession:
        return self._session_factory()

    async def dispose(self) -> None:
        await self._engine.dispose()
