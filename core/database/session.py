from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from core.config import settings
from core.database.models import Base

engine_kwargs = {"echo": False, "future": True}
if "sqlite" in settings.DATABASE_URL:
    engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": settings.SQLITE_BUSY_TIMEOUT / 1000.0,
    }
else:
    engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
    engine_kwargs["pool_timeout"] = settings.DB_POOL_TIMEOUT
    engine_kwargs["pool_recycle"] = settings.DB_POOL_RECYCLE
    engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs
)

if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={settings.SQLITE_BUSY_TIMEOUT}")
        finally:
            cursor.close()

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)


async def init_db() -> None:
    """Initialize database tables and apply migrations if needed.
    In production (ENV=prod), schema is handled exclusively by Alembic migrations.
    """
    if settings.ENV != "prod":
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
                    # Sanitize search_page_offset for existing users to keep pagination within [0, 4]
                    connection.execute(text("UPDATE users SET search_page_offset = search_page_offset % 5 WHERE search_page_offset IS NOT NULL AND search_page_offset >= 5"))

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
