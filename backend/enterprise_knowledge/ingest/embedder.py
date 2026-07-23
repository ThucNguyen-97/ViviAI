"""Gemini embedding helpers for the RAG ingest and retrieval flows."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional

from google import genai
from google.genai import types

from core.config import settings

logger = logging.getLogger(__name__)

MODEL_NAME = settings.EMBEDDING_MODEL_NAME
EMBEDDING_DIM = settings.EMBEDDING_DIMENSION
EMBEDDING_CONTEXT_TOKENS = settings.EMBEDDING_CONTEXT_TOKENS

DOCUMENT_PREFIX = "Retrieval document: "
QUERY_PREFIX = "Retrieval query: "


class EmbeddingConfigError(RuntimeError):
    """Raised when Gemini embedding configuration is incomplete."""


class ContextWindowError(ValueError):
    """Raised when an input exceeds the embedding context window."""


@lru_cache(maxsize=1)
def get_genai_client(api_key: Optional[str] = None) -> genai.Client:
    resolved_key = api_key or settings.GEMINI_API_KEY
    if not resolved_key:
        raise EmbeddingConfigError("Cần cấu hình GOOGLE_API_KEY hoặc truyền API key để dùng Gemini embedding.")
    return genai.Client(api_key=resolved_key)


def count_tokens(text: str, api_key: Optional[str] = None, model: str = MODEL_NAME) -> int:
    response = get_genai_client(api_key).models.count_tokens(
        model=model,
        contents=text,
    )
    return int(response.total_tokens or 0)


def ensure_context_window(
    text: str,
    api_key: Optional[str] = None,
    max_tokens: int = EMBEDDING_CONTEXT_TOKENS,
) -> int:
    token_count = count_tokens(text, api_key=api_key)
    if token_count > max_tokens:
        raise ContextWindowError(
            f"Nội dung vượt ngữ cảnh embedding: {token_count} tokens > {max_tokens} tokens."
        )
    return token_count


def _embedding_values(response: types.EmbedContentResponse) -> List[float]:
    if not response.embeddings:
        raise RuntimeError("Gemini không trả về embedding.")
    values = response.embeddings[0].values
    if values is None:
        raise RuntimeError("Gemini trả về embedding rỗng.")
    return [float(v) for v in values]


def embed_documents(texts: List[str], api_key: Optional[str] = None) -> List[List[float]]:
    if not texts:
        return []

    client = get_genai_client(api_key)
    embeddings: List[List[float]] = []

    for text in texts:
        prefixed = DOCUMENT_PREFIX + text
        ensure_context_window(prefixed, api_key=api_key)
        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=prefixed,
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
        )
        values = _embedding_values(response)
        if len(values) != EMBEDDING_DIM:
            raise RuntimeError(f"Embedding dimension không khớp: {len(values)} != {EMBEDDING_DIM}.")
        embeddings.append(values)

    return embeddings


def embed_query(query: str, api_key: Optional[str] = None) -> List[float]:
    prefixed = QUERY_PREFIX + query
    ensure_context_window(prefixed, api_key=api_key)
    response = get_genai_client(api_key).models.embed_content(
        model=MODEL_NAME,
        contents=prefixed,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
    )
    values = _embedding_values(response)
    if len(values) != EMBEDDING_DIM:
        raise RuntimeError(f"Embedding dimension không khớp: {len(values)} != {EMBEDDING_DIM}.")
    return values
