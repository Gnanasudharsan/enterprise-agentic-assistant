from app.core.config import Settings
from app.llm.base import LLMClient
from app.rag.embeddings import Embedder, HashingEmbedder, OpenAIEmbedder
from app.rag.reranking import LLMReranker
from app.rag.retrieval import Retriever


def build_embedder(settings: Settings) -> Embedder:
    if settings.resolved_embedding_provider == "hashing":
        return HashingEmbedder()
    assert settings.llm_api_key is not None  # guaranteed by resolved_embedding_provider
    return OpenAIEmbedder(
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.embedding_model,
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def build_retriever(settings: Settings, embedder: Embedder, llm: LLMClient) -> Retriever:
    reranker = LLMReranker(llm) if settings.reranker == "llm" else None
    return Retriever(
        embedder,
        candidates=settings.retrieval_candidates,
        top_k=settings.retrieval_top_k,
        rrf_k=settings.rrf_k,
        reranker=reranker,
    )
