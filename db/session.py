import os
from pathlib import Path
from typing import AsyncGenerator
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Load .env specifically from ticket_demo folder
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

DATABASE_URL = os.getenv(
    "TICKET_DEMO_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
)
DATABASE_URL_DIRECT = os.getenv(
    "TICKET_DEMO_DATABASE_URL_DIRECT",
    DATABASE_URL,
)

# Supabase pgbouncer (transaction mode) requirements for asyncpg:
#   - statement_cache_size=0  → no prepared statements (pgbouncer resets them)
#   - NullPool                → don't reuse connections; pgbouncer does the pooling
#     (pool_pre_ping is unreliable with asyncpg dialect under pgbouncer)
connect_args = {
    "statement_cache_size": 0,
    "prepared_statement_cache_size": 0,
}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    connect_args=connect_args,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
