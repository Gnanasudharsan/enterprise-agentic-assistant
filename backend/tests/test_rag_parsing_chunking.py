from pathlib import Path

import pytest

from app.rag.chunking import ChunkDraft, chunk_document, embedding_text
from app.rag.embeddings import HashingEmbedder
from app.rag.parsing import UnsupportedFileType, parse_document, parse_front_matter

CORPUS = Path(__file__).resolve().parents[2] / "datasets" / "documents"

DOC = """---
title: Travel Guide
doc_id: FIN-009
acl: finance, leadership
version: 1.2
---

# Travel Guide

Short intro line.

## Flights

Book economy for short flights. Premium economy is allowed for long flights.

## Hotels

### Standard cities

Up to $250 per night.
"""


def test_front_matter_is_parsed_and_removed():
    meta, body = parse_front_matter(DOC)
    assert meta["doc_id"] == "FIN-009"
    assert body.lstrip().startswith("# Travel Guide")


def test_parse_document_reads_metadata_and_acl():
    doc = parse_document("travel.md", DOC.encode())
    assert (doc.doc_key, doc.title, doc.version) == ("FIN-009", "Travel Guide", "1.2")
    assert doc.acl == ("finance", "leadership")


def test_parse_document_defaults_without_front_matter():
    doc = parse_document("team-notes.md", b"# Team Notes\n\nSome text here.", acl=("eng",))
    assert (doc.doc_key, doc.title, doc.acl) == ("team-notes", "Team Notes", ("eng",))


def test_unsupported_file_type_rejected():
    with pytest.raises(UnsupportedFileType):
        parse_document("image.png", b"\x89PNG")


def test_chunks_follow_heading_paths_and_merge_tiny_sections():
    doc = parse_document("travel.md", DOC.encode())
    chunks = chunk_document(doc.title, doc.body, min_words=5)
    sections = [c.section for c in chunks]
    # The 3-word intro is merged into the next section instead of standing alone.
    assert sections[0] == "Travel Guide › Flights"
    assert chunks[0].content.startswith("Short intro line.")
    # "Hotels" has no own text; its subsection keeps the full path.
    assert "Travel Guide › Hotels › Standard cities" in sections


def test_large_sections_split_with_overlap_and_respect_budget():
    sentences = " ".join(f"Sentence number {i} explains a policy detail." for i in range(80))
    chunks = chunk_document("Big", f"## Section\n\n{sentences}", max_words=60, overlap_words=12)
    assert len(chunks) > 1
    assert all(len(c.content.split()) <= 60 for c in chunks)
    # Consecutive chunks share trailing/leading sentences.
    assert chunks[0].content.split(". ")[-1] in chunks[1].content


def test_chunking_never_splits_inside_code_fences():
    body = (
        "## Setup\n\n```\n# not a heading\nrun --flag\n```\n\nAfter the code block we explain more."
    )
    chunks = chunk_document("Doc", body, min_words=1)
    assert len(chunks) == 1
    assert "# not a heading" in chunks[0].content


def test_corpus_chunks_are_reasonable():
    for path in CORPUS.rglob("*.md"):
        if path.name == "README.md":
            continue
        doc = parse_document(path.name, path.read_bytes())
        chunks = chunk_document(doc.title, doc.body)
        assert chunks, path
        assert all(10 <= len(c.content.split()) <= 260 for c in chunks), path


def test_embedding_text_includes_section_path():
    assert embedding_text(ChunkDraft("A › B", "body")) == "A › B\n\nbody"


async def test_hashing_embedder_is_normalized_and_lexically_sensitive():
    emb = HashingEmbedder()
    pto, pto2, other = await emb.embed(
        ["paid time off carry over", "how much paid time off carries over", "laptop encryption"]
    )
    dot = lambda a, b: sum(x * y for x, y in zip(a, b, strict=True))  # noqa: E731
    assert dot(pto, pto) == pytest.approx(1.0)
    assert dot(pto, pto2) > dot(pto, other)
    [stop_only] = await emb.embed(["what is the"])
    assert dot(stop_only, stop_only) == pytest.approx(1.0)
