from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.base import get_db
from rag.retriever import DEFAULT_SCORE_THRESHOLD, DEFAULT_TOP_K, similarity_search
from rag.schemas import RagSearchRequest, RagSearchResponse

router = APIRouter(prefix="/rag", tags=["RAG Retrieval"])


@router.post("/search", response_model=RagSearchResponse)
async def rag_search(
    request: RagSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Return relevant chunks and source metadata for the VM/LLM layer.

    Enterprise Knowledge intentionally does not synthesize the final answer here.
    """
    top_k = request.top_k or DEFAULT_TOP_K
    score_threshold = (
        request.score_threshold
        if request.score_threshold is not None
        else DEFAULT_SCORE_THRESHOLD
    )
    gemini_key = settings.GEMINI_API_KEY

    results = await similarity_search(
        db,
        query=request.query,
        top_k=top_k,
        score_threshold=score_threshold,
        gemini_api_key=gemini_key,
    )

    return RagSearchResponse(
        query=request.query,
        top_k=top_k,
        score_threshold=score_threshold,
        total=len(results),
        results=results,
    )
