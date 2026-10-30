"""Analytics data command line.

python -m app.analytics.cli seed [--force]    # load the synthetic dataset (idempotent)
python -m app.analytics.cli query "SQL"       # run a query through the guard + executor
"""

import argparse
import asyncio

from app.analytics.seed import seed
from app.analytics.sql import SQLExecutor, validate_sql
from app.core.config import get_settings
from app.db.session import build_engine


async def _seed(force: bool) -> None:
    engine = build_engine(get_settings().sqlalchemy_url)
    try:
        async with engine.begin() as conn:
            counts = await seed(conn, force=force)
    finally:
        await engine.dispose()
    if counts is None:
        print("Analytics data already present (use --force to reload).")
    else:
        print("Loaded " + ", ".join(f"{n} {table}" for table, n in counts.items()))


async def _query(sql: str) -> None:
    settings = get_settings()
    validated = validate_sql(sql, max_rows=settings.sql_max_rows)
    engine = build_engine(settings.sqlalchemy_url)
    executor = SQLExecutor(
        engine, timeout_ms=settings.sql_timeout_ms, max_rows=settings.sql_max_rows
    )
    try:
        result = await executor.run(validated.sql)
    finally:
        await engine.dispose()
    print(validated.sql)
    print(" | ".join(result.columns))
    for row in result.rows:
        print(" | ".join("" if v is None else str(v) for v in row))
    more = " (truncated)" if result.truncated else ""
    print(f"{len(result.rows)} rows{more} in {result.elapsed_ms} ms")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.analytics.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    seed_cmd = sub.add_parser("seed", help="Load the synthetic analytics dataset")
    seed_cmd.add_argument("--force", action="store_true", help="Replace existing data")
    query_cmd = sub.add_parser("query", help="Run a read-only query")
    query_cmd.add_argument("sql")
    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(_seed(args.force))
    else:
        asyncio.run(_query(args.sql))


if __name__ == "__main__":
    main()
