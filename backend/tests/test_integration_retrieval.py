"""Hybrid retrieval against real Postgres + pgvector, with the offline embedder."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.rag.embeddings import HashingEmbedder
from app.rag.ingestion import ingest_directory
from app.rag.retrieval import Retriever
from tests.conftest import CORPUS_DIR

pytestmark = pytest.mark.integration

EMPLOYEE = ["all-employees"]


@pytest.fixture
async def corpus(pg_session):
    await ingest_directory(pg_session, CORPUS_DIR, HashingEmbedder())
    return pg_session


@pytest.mark.parametrize("mode", ["hybrid", "vector", "keyword"])
async def test_finds_pto_carryover_in_every_mode(corpus, mode):
    hits = await Retriever(HashingEmbedder()).search(
        corpus, "How many unused PTO days carry over?", EMPLOYEE, mode=mode
    )
    assert hits[0].doc_key == "HR-001"
    assert "Paid time off" in hits[0].section


async def test_exact_identifier_match(corpus):
    hits = await Retriever(HashingEmbedder()).search(corpus, "INC-198", EMPLOYEE, mode="keyword")
    assert hits[0].doc_key == "INC-198"


async def test_hybrid_records_ranks_from_both_channels(corpus):
    [top] = await Retriever(HashingEmbedder()).search(
        corpus, "INC-204 root cause", EMPLOYEE, top_k=1
    )
    assert (top.doc_key, top.vector_rank, top.keyword_rank) == ("INC-204", 1, 1)


async def test_restricted_documents_are_never_returned_without_access(corpus):
    retriever = Retriever(HashingEmbedder(), candidates=100)
    for query in ["engineering salary bands merit budget", "Q4 OKRs leadership headcount"]:
        hits = await retriever.search(corpus, query, EMPLOYEE, top_k=20)
        assert not {h.doc_key for h in hits} & {"HR-007", "LDR-014"}

    hr = await retriever.search(corpus, "engineering salary bands", [*EMPLOYEE, "hr-confidential"])
    assert hr[0].doc_key == "HR-007"


async def test_no_groups_means_no_results(corpus):
    assert await Retriever(HashingEmbedder()).search(corpus, "PTO", []) == []


async def test_chunks_from_other_embedding_models_are_ignored(corpus):
    class Other(HashingEmbedder):
        model = "some-other-model"

    assert await Retriever(Other()).search(corpus, "PTO", EMPLOYEE, mode="vector") == []


class ReverseReranker:
    async def score(self, query, passages):
        return [float(i) for i in range(len(passages))]  # last candidate ranks first


async def test_reranker_reorders_candidates(corpus):
    base = await Retriever(HashingEmbedder()).search(corpus, "PTO carry over", EMPLOYEE, top_k=3)
    reranked = await Retriever(HashingEmbedder(), reranker=ReverseReranker()).search(
        corpus, "PTO carry over", EMPLOYEE, top_k=3
    )
    assert [h.chunk_id for h in reranked] != [h.chunk_id for h in base]
    skipped = await Retriever(HashingEmbedder(), reranker=ReverseReranker()).search(
        corpus, "PTO carry over", EMPLOYEE, top_k=3, rerank=False
    )
    assert [h.chunk_id for h in skipped] == [h.chunk_id for h in base]


async def test_search_endpoint(corpus, migrated_db):
    settings = Settings(
        _env_file=None,
        llm_provider="fake",
        embedding_provider="hashing",
        database_url=migrated_db,
    )
    with TestClient(create_app(settings)) as client:
        resp = client.post("/api/v1/search", json={"query": "laptop lost or stolen", "top_k": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["embedding_model"] == "hashing-v1"
    assert body["hits"][0]["doc_key"] == "SEC-001"
