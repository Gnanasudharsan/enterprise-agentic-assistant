"""Knowledge-base documents: list, upload, and passage lookup (all ACL-checked)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import String, cast, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_retriever, get_user_groups
from app.db.models import Chunk, Document
from app.rag.embeddings import EmbeddingError
from app.rag.ingestion import ingest_document
from app.rag.parsing import UnsupportedFileType, parse_document
from app.rag.retrieval import Retriever
from app.schemas.documents import ChunkDetail, DocumentList, DocumentSummary, UploadResult

router = APIRouter(prefix="/api/v1", tags=["knowledge base"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def visible_to(groups: list[str]):
    return Document.acl.overlap(cast(groups, ARRAY(String)))


async def summarize(db: AsyncSession, docs: list[Document]) -> list[DocumentSummary]:
    if not docs:
        return []
    counts = dict(
        (
            await db.execute(
                select(Chunk.document_id, func.count(Chunk.id))
                .where(Chunk.document_id.in_([d.id for d in docs]))
                .group_by(Chunk.document_id)
            )
        ).all()
    )
    return [
        DocumentSummary(
            id=d.id,
            doc_key=d.doc_key,
            title=d.title,
            doc_type=d.doc_type,
            owner=d.owner,
            version=d.version,
            source_updated=d.source_updated,
            source_path=d.source_path,
            acl=d.acl,
            embedding_model=d.embedding_model,
            chunk_count=counts.get(d.id, 0),
            updated_at=d.updated_at,
        )
        for d in docs
    ]


@router.get("/documents", response_model=DocumentList)
async def list_documents(
    groups: Annotated[list[str], Depends(get_user_groups)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentList:
    docs = (
        await db.scalars(select(Document).where(visible_to(groups)).order_by(Document.doc_key))
    ).all()
    return DocumentList(documents=await summarize(db, list(docs)))


@router.post("/documents", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File(description=".md, .txt, .pdf, or .docx (max 5 MB)")],
    groups: Annotated[list[str], Depends(get_user_groups)],
    retriever: Annotated[Retriever, Depends(get_retriever)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    acl: Annotated[str | None, Form(description="Comma-separated groups")] = None,
) -> UploadResult:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File is larger than 5 MB.")
    requested_acl = tuple(g.strip() for g in (acl or "").split(",") if g.strip()) or None

    try:
        doc = parse_document(
            file.filename or "upload.txt",
            data,
            source_path=f"uploads/{file.filename}",
            acl=requested_acl,
        )
    except UnsupportedFileType as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    # You may only publish to groups you belong to, and only overwrite documents you can see.
    if not set(doc.acl) <= set(groups):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can only share documents with groups you belong to."
        )
    existing = await db.scalar(select(Document).where(Document.doc_key == doc.doc_key))
    if existing and not set(existing.acl) & set(groups):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A document with this ID already exists.")

    try:
        result = await ingest_document(db, doc, retriever.embedder)
    except EmbeddingError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Embedding the document failed.") from exc

    stored = await db.scalar(select(Document).where(Document.doc_key == doc.doc_key))
    assert stored is not None
    [summary] = await summarize(db, [stored])
    return UploadResult(status=result.status, document=summary)


@router.get("/chunks/{chunk_id}", response_model=ChunkDetail)
async def get_chunk(
    chunk_id: uuid.UUID,
    groups: Annotated[list[str], Depends(get_user_groups)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChunkDetail:
    row = (
        await db.execute(
            select(Chunk, Document).join(Document).where(Chunk.id == chunk_id, visible_to(groups))
        )
    ).first()
    if row is None:  # same answer for "missing" and "not allowed": no existence leak
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Passage not found.")
    chunk, document = row
    [summary] = await summarize(db, [document])
    return ChunkDetail(
        chunk_id=chunk.id,
        chunk_index=chunk.chunk_index,
        section=chunk.section,
        content=chunk.content,
        token_count=chunk.token_count,
        document=summary,
    )
