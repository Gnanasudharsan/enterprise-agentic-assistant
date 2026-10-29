"""Knowledge-base command line.

python -m app.rag.cli ingest [PATH]     # ingest a directory (default: DOCUMENTS_DIR)
"""

import argparse
import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.db.session import build_engine, build_sessionmaker
from app.rag.factory import build_embedder
from app.rag.ingestion import ingest_directory


async def _ingest(path: Path) -> None:
    settings = get_settings()
    engine = build_engine(settings.sqlalchemy_url)
    embedder = build_embedder(settings)
    try:
        async with build_sessionmaker(engine)() as session:
            results = await ingest_directory(session, path, embedder)
    finally:
        await embedder.aclose()
        await engine.dispose()

    for r in results:
        print(f"  {r.status:<9} {r.doc_key:<10} {r.chunks:>3} chunks  {r.title}")
    total = sum(r.chunks for r in results)
    print(f"{len(results)} documents, {total} chunks (embedder: {embedder.model})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.rag.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Ingest a directory of documents")
    ingest.add_argument("path", nargs="?", help="Directory (default: DOCUMENTS_DIR setting)")
    args = parser.parse_args()

    if args.command == "ingest":
        asyncio.run(_ingest(Path(args.path or get_settings().documents_dir)))


if __name__ == "__main__":
    main()
