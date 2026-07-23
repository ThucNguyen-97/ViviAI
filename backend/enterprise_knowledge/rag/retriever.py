"""Semantic retrieval over pgvector-backed RAG chunks."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.models import Chunk, RagDocument
from ingest.embedder import embed_query
from rag.schemas import RagSearchResult, RagSource

DEFAULT_TOP_K = settings.RAG_DEFAULT_TOP_K
DEFAULT_SCORE_THRESHOLD = settings.RAG_DEFAULT_SCORE_THRESHOLD


async def similarity_search(
    db: AsyncSession,
    *,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    gemini_api_key: Optional[str] = None,
) -> list[RagSearchResult]:
    query_text = query.strip()
    if not query_text:
        return []

    query_embedding = embed_query(query_text, api_key=gemini_api_key)
    distance = Chunk.embedding.cosine_distance(query_embedding)
    max_distance = 1.0 - score_threshold

    statement = (
        select(Chunk, RagDocument, distance.label("distance"))
        .join(RagDocument, RagDocument.id == Chunk.rag_document_id)
        .where(distance <= max_distance)
        .order_by(distance.asc())
        .limit(top_k)
    )
    rows = (await db.execute(statement)).all()

    results: list[RagSearchResult] = []
    for chunk, document, raw_distance in rows:
        chunk_distance = float(raw_distance)
        results.append(
            RagSearchResult(
                chunk_id=str(chunk.id),
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=max(0.0, min(1.0, 1.0 - chunk_distance)),
                distance=chunk_distance,
                source=RagSource(
                    document_id=str(document.id),
                    file_name=document.file_name,
                    file_type=document.file_type,
                    file_path=document.file_path,
                    storage_url=document.storage_url,
                ),
                meta_info=chunk.meta_info,
            )
        )

    return results
