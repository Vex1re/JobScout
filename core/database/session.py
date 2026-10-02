from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from core.config import settings
from core.database.models import Base

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


async def init_db() -> None:
    """Initialize database tables and apply migrations if needed."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _migrate(connection):
            from sqlalchemy import inspect, text
            inspector = inspect(connection)
            tables = inspector.get_table_names()

            if "users" in tables:
                cols = {c["name"] for c in inspector.get_columns("users")}
                if "city" not in cols:
                    connection.execute(text("ALTER TABLE users ADD COLUMN city VARCHAR(100)"))
                if "search_page_offset" not in cols:
                    connection.execute(text("ALTER TABLE users ADD COLUMN search_page_offset INTEGER DEFAULT 0"))
                if "last_query_index" not in cols:
                    connection.execute(text("ALTER TABLE users ADD COLUMN last_query_index INTEGER DEFAULT 0"))
                if "enabled_sources" not in cols:
                    connection.execute(text("ALTER TABLE users ADD COLUMN enabled_sources JSON"))

            if "vacancies" in tables:
                cols = {c["name"] for c in inspector.get_columns("vacancies")}
                if "city" not in cols:
                    connection.execute(text("ALTER TABLE vacancies ADD COLUMN city VARCHAR(100)"))
                if "min_experience" not in cols:
                    connection.execute(text("ALTER TABLE vacancies ADD COLUMN min_experience FLOAT"))
                if "max_experience" not in cols:
                    connection.execute(text("ALTER TABLE vacancies ADD COLUMN max_experience FLOAT"))
                if "target_grade" not in cols:
                    connection.execute(text("ALTER TABLE vacancies ADD COLUMN target_grade VARCHAR(50)"))

        await conn.run_sync(_migrate)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency / generator for database session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
