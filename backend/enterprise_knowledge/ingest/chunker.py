"""Chunk Markdown text into retrieval units for embedding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


DEFAULT_CHUNK_SIZE_TOKENS = 768
DEFAULT_OVERLAP_TOKENS = 96


@dataclass
class TextChunk:
    """A Markdown chunk ready for embedding."""

    content: str
    chunk_index: int
    meta_info: dict = field(default_factory=dict)


def _split_markdown_blocks(text: str) -> List[str]:
    blocks: List[str] = []
    current: List[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue

        if stripped.startswith("#") and current:
            blocks.append("\n".join(current).strip())
            current = [line]
            continue

        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())

    return [block for block in blocks if block]


def _token_estimate(text: str) -> int:
    # Used only for local chunk sizing before the exact google-genai count gate.
    return max(1, len(text) // 4)


def chunk_text(
    text: str,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    source_meta: dict | None = None,
) -> List[TextChunk]:
    if not text or not text.strip():
        return []

    source_meta = source_meta or {}
    blocks = _split_markdown_blocks(text)

    chunks: List[TextChunk] = []
    current_chunk: List[str] = []
    current_tokens = 0
    chunk_index = 0
    overlap_chars = overlap_tokens * 4

    def flush_current() -> None:
        nonlocal current_chunk, current_tokens, chunk_index
        if not current_chunk:
            return

        content = "\n\n".join(current_chunk).strip()
        if content:
            chunks.append(TextChunk(
                content=content,
                chunk_index=chunk_index,
                meta_info={
                    **source_meta,
                    "char_count": len(content),
                    "estimated_tokens": _token_estimate(content),
                },
            ))
            chunk_index += 1

        overlap_text = content[-overlap_chars:].strip() if overlap_chars > 0 else ""
        current_chunk = [overlap_text] if overlap_text else []
        current_tokens = _token_estimate(overlap_text) if overlap_text else 0

    for block in blocks:
        block_tokens = _token_estimate(block)

        if block_tokens >= chunk_size_tokens:
            flush_current()
            max_chars = chunk_size_tokens * 4
            step = max(1, max_chars - overlap_chars)
            for start in range(0, len(block), step):
                sub = block[start:start + max_chars].strip()
                if sub:
                    chunks.append(TextChunk(
                        content=sub,
                        chunk_index=chunk_index,
                        meta_info={
                            **source_meta,
                            "char_count": len(sub),
                            "estimated_tokens": _token_estimate(sub),
                        },
                    ))
                    chunk_index += 1
            current_chunk = []
            current_tokens = 0
            continue

        if current_chunk and current_tokens + block_tokens > chunk_size_tokens:
            flush_current()

        current_chunk.append(block)
        current_tokens += block_tokens

    if current_chunk:
        content = "\n\n".join(current_chunk).strip()
        if content and (not chunks or chunks[-1].content != content):
            chunks.append(TextChunk(
                content=content,
                chunk_index=chunk_index,
                meta_info={
                    **source_meta,
                    "char_count": len(content),
                    "estimated_tokens": _token_estimate(content),
                },
            ))

    return chunks
