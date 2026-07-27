"""VM-side cache for the catalog owned by Enterprise Knowledge."""

from __future__ import annotations

import logging
import time
from typing import Any

from core.config import settings
from ek_client import ek_client

logger = logging.getLogger(__name__)

_catalog: list[dict[str, Any]] = []
_updated_at: str | None = None
_last_checked_at = 0.0


async def refresh_rag_catalog(*, force: bool = False) -> list[dict[str, Any]]:
    global _catalog, _updated_at, _last_checked_at

    now = time.monotonic()
    if not force and now - _last_checked_at < settings.RAG_CATALOG_CACHE_TTL_SECONDS:
        return _catalog

    try:
        response = await ek_client.rag_catalog(since=_updated_at)
        if response.get("updated"):
            _catalog = response.get("documents", [])
            _updated_at = response.get("updated_at")
            logger.info("Loaded RAG catalog from EK: %s documents, updated_at=%s", len(_catalog), _updated_at)
        else:
            logger.debug("RAG catalog unchanged at updated_at=%s", _updated_at)
        _last_checked_at = now
    except Exception:
        logger.exception("Unable to refresh RAG catalog from Enterprise Knowledge.")

    return _catalog


def cached_rag_catalog() -> list[dict[str, Any]]:
    return _catalog
