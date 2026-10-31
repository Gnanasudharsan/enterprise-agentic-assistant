from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def build_engine(url: str, pool_size: int = 5) -> AsyncEngine:
    if not url.startswith("postgresql"):  # SQLite in tests has no connection pool to size
        return create_async_engine(url, pool_pre_ping=True)
    return create_async_engine(url, pool_pre_ping=True, pool_size=pool_size, max_overflow=2)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
