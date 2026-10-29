"""Ingestion against real Postgres + pgvector."""

import dataclasses

import pytest
from sqlalchemy import func, select, text

from app.db.models import Chunk, Document
from app.rag.embeddings import HashingEmbedder
from app.rag.ingestion import ingest_directory, ingest_document
from app.rag.parsing import parse_document
from tests.conftest import CORPUS_DIR

pytestmark = pytest.mark.integration


class OtherEmbedder(HashingEmbedder):
    model = "hashing-other"


async def test_corpus_ingestion_is_idempotent(pg_session):
    first = await ingest_directory(pg_session, CORPUS_DIR, HashingEmbedder())
    assert len(first) == 12
    assert {r.status for r in first} == {"created"}

    second = await ingest_directory(pg_session, CORPUS_DIR, HashingEmbedder())
    assert {r.status for r in second} == {"unchanged"}
    assert await pg_session.scalar(select(func.count(Document.id))) == 12
    assert await pg_session.scalar(select(func.count(Chunk.id))) == sum(r.chunks for r in first)


async def test_reingestion_replaces_chunks_and_tracks_acl(pg_session):
    path = CORPUS_DIR / "hr" / "compensation-bands.md"
    doc = parse_document(path.name, path.read_bytes())
    created = await ingest_document(pg_session, doc, HashingEmbedder())

    changed = dataclasses.replace(doc, body=doc.body + "\n\n## Appendix\n\n" + "New text. " * 40)
    updated = await ingest_document(pg_session, changed, HashingEmbedder())

    assert (created.status, updated.status) == ("created", "updated")
    assert updated.chunks > created.chunks
    stored = await pg_session.scalar(select(Document).where(Document.doc_key == "HR-007"))
    assert stored.acl == ["hr-confidential"]
    count = await pg_session.scalar(
        select(func.count(Chunk.id)).where(Chunk.document_id == stored.id)
    )
    assert count == updated.chunks  # old chunks removed, not duplicated


async def test_changing_embedder_reembeds_unchanged_content(pg_session):
    path = CORPUS_DIR / "security" / "information-security-policy.md"
    doc = parse_document(path.name, path.read_bytes())
    await ingest_document(pg_session, doc, HashingEmbedder())
    again = await ingest_document(pg_session, doc, OtherEmbedder())
    assert again.status == "updated"
    stored = await pg_session.scalar(select(Document).where(Document.doc_key == "SEC-001"))
    assert stored.embedding_model == "hashing-other"


async def test_generated_search_vector_is_populated(pg_session):
    await ingest_directory(pg_session, CORPUS_DIR, HashingEmbedder())
    hits = await pg_session.scalar(
        text("SELECT count(*) FROM chunks WHERE search_vector @@ to_tsquery('english', 'INC-204')")
    )
    assert hits >= 1
