"""Store parsed documents as chunks with embeddings. Re-ingestion is idempotent."""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document
from app.rag.chunking import chunk_document, embedding_text
from app.rag.embeddings import Embedder
from app.rag.parsing import SUPPORTED_EXTENSIONS, ParsedDocument, parse_document

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestResult:
    doc_key: str
    title: str
    status: Literal["created", "updated", "unchanged"]
    chunks: int


def content_hash(doc: ParsedDocument) -> str:
    payload = json.dumps(asdict(doc), sort_keys=True, default=list)
    return hashlib.sha256(payload.encode()).hexdigest()


async def ingest_document(
    session: AsyncSession, doc: ParsedDocument, embedder: Embedder
) -> IngestResult:
    """Insert or replace one document. Skips work if content and embedder are unchanged."""
    digest = content_hash(doc)
    existing = await session.scalar(select(Document).where(Document.doc_key == doc.doc_key))
    if existing and existing.content_hash == digest and existing.embedding_model == embedder.model:
        count = len(await existing.awaitable_attrs.chunks)
        return IngestResult(doc.doc_key, doc.title, "unchanged", count)

    drafts = chunk_document(doc.title, doc.body)
    vectors = await embedder.embed([embedding_text(d) for d in drafts])

    fields = {
        "title": doc.title,
        "doc_type": doc.doc_type,
        "owner": doc.owner,
        "source_path": doc.source_path,
        "version": doc.version,
        "source_updated": doc.updated,
        "acl": list(doc.acl),
        "content_hash": digest,
        "embedding_model": embedder.model,
    }
    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        (await existing.awaitable_attrs.chunks).clear()
        await session.flush()  # delete old chunks before inserting replacements
        document, status = existing, "updated"
    else:
        document = Document(doc_key=doc.doc_key, **fields)
        session.add(document)
        status = "created"

    document.chunks.extend(
        Chunk(
            chunk_index=i,
            section=d.section,
            content=d.content,
            token_count=d.token_count,
            embedding=vec,
        )
        for i, (d, vec) in enumerate(zip(drafts, vectors, strict=True))
    )
    await session.commit()
    logger.info("Ingested %s (%s, %d chunks)", doc.doc_key, status, len(drafts))
    return IngestResult(doc.doc_key, doc.title, status, len(drafts))


def iter_document_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and p.name != "README.md"
    )


async def ingest_directory(
    session: AsyncSession, root: Path, embedder: Embedder
) -> list[IngestResult]:
    results = []
    for path in iter_document_files(root):
        doc = parse_document(path.name, path.read_bytes(), source_path=str(path.relative_to(root)))
        results.append(await ingest_document(session, doc, embedder))
    return results
