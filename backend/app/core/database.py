"""
Kyotech AI — Conexão assíncrona com PostgreSQL
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"command_timeout": 30, "server_settings": {"tcp_keepalives_idle": "60"}},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """Dependency injection para FastAPI."""
    async with async_session() as session:
        yield session
