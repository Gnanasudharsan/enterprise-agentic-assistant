"""Knowledge-base command line.

python -m app.rag.cli ingest [PATH]     # ingest a directory (default: DOCUMENTS_DIR)
"""

import argparse
import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.db.session import build_engine, build_sessionmaker
from app.llm.factory import build_llm_client
from app.rag.factory import build_embedder, build_retriever
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


async def _search(query: str, mode: str, groups: list[str]) -> None:
    settings = get_settings()
    engine = build_engine(settings.sqlalchemy_url)
    llm = build_llm_client(settings)
    retriever = build_retriever(settings, build_embedder(settings), llm)
    try:
        async with build_sessionmaker(engine)() as session:
            hits = await retriever.search(session, query, groups, mode=mode)
    finally:
        await retriever.embedder.aclose()
        await llm.aclose()
        await engine.dispose()

    for i, h in enumerate(hits, start=1):
        ranks = f"vec={h.vector_rank or '-'} kw={h.keyword_rank or '-'}"
        print(f"{i}. [{h.doc_key}] {h.section}  ({h.score:.4f}; {ranks})")
        print(f"   {h.content[:140].replace(chr(10), ' ')}...")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.rag.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Ingest a directory of documents")
    ingest.add_argument("path", nargs="?", help="Directory (default: DOCUMENTS_DIR setting)")
    search = sub.add_parser("search", help="Search the knowledge base")
    search.add_argument("query")
    search.add_argument("--mode", default="hybrid", choices=["hybrid", "vector", "keyword"])
    search.add_argument("--groups", help="Comma-separated groups (default: USER_GROUPS)")
    args = parser.parse_args()

    if args.command == "ingest":
        asyncio.run(_ingest(Path(args.path or get_settings().documents_dir)))
    elif args.command == "search":
        groups = args.groups.split(",") if args.groups else get_settings().user_groups
        asyncio.run(_search(args.query, args.mode, groups))


if __name__ == "__main__":
    main()
