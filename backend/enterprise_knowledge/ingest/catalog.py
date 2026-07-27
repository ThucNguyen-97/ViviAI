"""Runtime catalog generated from Markdown RAG front matter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml


_catalog: list[dict[str, Any]] = []
_updated_at: Optional[str] = None
_fingerprint: Optional[str] = None


def parse_front_matter(raw_text: str) -> tuple[dict[str, Any], str]:
    """Return YAML front matter and Markdown body from a document."""
    lines = raw_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw_text

    try:
        end_index = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return {}, raw_text

    parsed = yaml.safe_load("\n".join(lines[1:end_index])) or {}
    if not isinstance(parsed, dict):
        raise ValueError("YAML Front Matter phải là một object/map.")

    body = "\n".join(lines[end_index + 1:])
    return parsed, body


def _normalize_topics(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("Trường 'topics' phải là chuỗi hoặc danh sách chuỗi.")


def _read_catalog(rag_dir: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for file_path in sorted(rag_dir.rglob("*.md")):
        if not file_path.is_file():
            continue
        metadata, _ = parse_front_matter(file_path.read_text(encoding="utf-8"))
        documents.append(
            {
                "file_name": file_path.name,
                "topics": _normalize_topics(metadata.get("topics")),
            }
        )
    return documents


def rebuild_rag_catalog(rag_dir: Path) -> dict[str, Any]:
    """Rebuild the process-local catalog and update its timestamp only on change."""
    global _catalog, _updated_at, _fingerprint

    next_catalog = _read_catalog(rag_dir) if rag_dir.exists() else []
    next_fingerprint = hashlib.sha256(
        repr(next_catalog).encode("utf-8")
    ).hexdigest()

    if next_fingerprint != _fingerprint:
        _catalog = next_catalog
        _fingerprint = next_fingerprint
        _updated_at = datetime.now(timezone.utc).isoformat()

    return get_rag_catalog()


def get_rag_catalog() -> dict[str, Any]:
    return {
        "updated_at": _updated_at,
        "documents": list(_catalog),
    }
