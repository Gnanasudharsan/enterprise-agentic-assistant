from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def build_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
