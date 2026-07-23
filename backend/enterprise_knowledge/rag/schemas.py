from typing import Any, Optional

from pydantic import BaseModel, Field

from core.config import settings


class RagSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User question or search query.")
    top_k: int = Field(
        default=settings.RAG_DEFAULT_TOP_K,
        ge=1,
        le=20,
        description="Maximum number of chunks to return.",
    )
    score_threshold: float = Field(
        default=settings.RAG_DEFAULT_SCORE_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score to include.",
    )


class RagSource(BaseModel):
    document_id: str
    file_name: str
    file_type: str
    file_path: str
    storage_url: Optional[str] = None


class RagSearchResult(BaseModel):
    chunk_id: str
    chunk_index: int
    content: str
    score: float
    distance: float
    source: RagSource
    meta_info: dict[str, Any] | None = None


class RagSearchResponse(BaseModel):
    query: str
    top_k: int
    score_threshold: float
    total: int
    results: list[RagSearchResult]
