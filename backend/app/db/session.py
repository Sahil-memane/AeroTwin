from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    # SQLAlchemy's default (5 + 10 overflow = 15 total) was proven live
    # to fully exhaust under Phase 8 load-test conditions — a single
    # demo engine at 0.5s intervals was enough on its own once ingestion
    # concurrency wasn't bounded (see ingestion.py's per-engine lock).
    # The plan's ~50-concurrent-engines target needs headroom for that
    # many ingestion paths plus normal API/dashboard/WS traffic
    # concurrently; Postgres's own default max_connections (100) has
    # plenty of room for this.
    pool_size=20,
    max_overflow=30,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db():
    """Dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session

