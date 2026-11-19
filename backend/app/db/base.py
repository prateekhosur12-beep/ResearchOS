"""Async database engine + session factory (SQLite by default, Postgres-ready)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine: AsyncEngine = create_async_engine(
    settings.resolved_database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create tables. SQLite + create_all is the documented, verified path.

    A real migration tool (alembic) is intentionally not introduced: the project
    ships a single schema revision and rolling it by hand would add risk without
    benefit at this scale. See DATABASE.md.
    """
    from app.db import models  # noqa: F401  (register mappers)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _apply_light_migrations()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()


#: Columns added after the first schema revision. ``create_all`` never alters an
#: existing table, and this project deliberately has no alembic dependency, so the
#: additive columns are applied in place (existing rows keep NULL defaults).
_ADDITIVE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "projects": [
        ("research_instructions", "TEXT"),
        ("research_questions", "JSON"),
    ],
}


async def _apply_light_migrations() -> None:
    """Add missing columns to existing SQLite databases without touching data."""
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    async with engine.begin() as conn:
        for table, columns in _ADDITIVE_COLUMNS.items():
            rows = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
            existing = {row[1] for row in rows}
            for name, ddl_type in columns:
                if name not in existing:
                    await conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"
                    )
