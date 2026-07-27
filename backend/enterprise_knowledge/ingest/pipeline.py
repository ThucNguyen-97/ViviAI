"""Markdown-only RAG ingest pipeline."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.models import Chunk, RagDocument
from ingest.chunker import chunk_text
from ingest.embedder import ContextWindowError, embed_documents, ensure_context_window

logger = logging.getLogger(__name__)

# The Markdown source directory lives under the broader knowledge directory.
DEFAULT_RAG_DIR = Path("/app/knowledge/rag_documents")
SUPPORTED_EXTENSION = ".md"


@dataclass
class IngestFileResult:
    file_name: str
    status: str
    chunks_created: int = 0
    error_message: Optional[str] = None


@dataclass
class IngestReport:
    total_scanned: int = 0
    total_success: int = 0
    total_skipped: int = 0
    total_error: int = 0
    total_deleted: int = 0
    results: List[IngestFileResult] = field(default_factory=list)


def _is_markdown(file_path: Path) -> bool:
    return file_path.suffix.lower() == SUPPORTED_EXTENSION


def _read_markdown(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")


async def ingest_file(
    file_path: Path,
    db: AsyncSession,
    gemini_api_key: Optional[str] = None,
) -> IngestFileResult:
    file_name = file_path.name

    if not _is_markdown(file_path):
        return IngestFileResult(
            file_name=file_name,
            status="error",
            error_message="Định dạng không hỗ trợ. RAG ingest hiện chỉ nhận file Markdown (.md).",
        )

    file_stat = file_path.stat()
    disk_mtime = datetime.utcfromtimestamp(file_stat.st_mtime)

    existing_result = await db.execute(
        select(RagDocument).where(RagDocument.file_path == str(file_path))
    )
    existing_doc = existing_result.scalar_one_or_none()

    is_update = False
    if existing_doc is not None:
        db_mtime = existing_doc.file_modified_at
        if db_mtime is None or disk_mtime > db_mtime or existing_doc.file_size != file_stat.st_size:
            logger.info("File '%s' changed; re-ingesting.", file_name)
            is_update = True
            await db.delete(existing_doc)
            await db.flush()
        else:
            return IngestFileResult(
                file_name=file_name,
                status="skipped",
                error_message="Không có thay đổi.",
            )

    try:
        raw_text = _read_markdown(file_path)
        if not raw_text.strip():
            return IngestFileResult(
                file_name=file_name,
                status="error",
                error_message="File Markdown trống.",
            )

        document_tokens = ensure_context_window(raw_text, api_key=gemini_api_key)
        chunks = chunk_text(
            text=raw_text,
            source_meta={
                "file_name": file_name,
                "file_type": "markdown",
                "document_tokens": document_tokens,
                "embedding_model": settings.EMBEDDING_MODEL_NAME,
            },
        )
        if not chunks:
            return IngestFileResult(
                file_name=file_name,
                status="error",
                error_message="Không tạo được chunk nào từ nội dung Markdown.",
            )

        chunk_texts = [chunk.content for chunk in chunks]
        embeddings = embed_documents(chunk_texts, api_key=gemini_api_key)
        if len(embeddings) != len(chunks):
            raise RuntimeError(f"Số embedding ({len(embeddings)}) không khớp số chunk ({len(chunks)}).")

        rag_doc = RagDocument(
            id=uuid.uuid4(),
            file_name=file_name,
            file_path=str(file_path),
            file_size=file_stat.st_size,
            file_type="markdown",
            storage_url=None,
            file_modified_at=disk_mtime,
        )
        db.add(rag_doc)
        await db.flush()

        db.add_all([
            Chunk(
                id=uuid.uuid4(),
                rag_document_id=rag_doc.id,
                content=chunks[index].content,
                embedding=embeddings[index],
                chunk_index=chunks[index].chunk_index,
                meta_info=chunks[index].meta_info,
            )
            for index in range(len(chunks))
        ])
        await db.commit()

        return IngestFileResult(
            file_name=file_name,
            status="updated" if is_update else "success",
            chunks_created=len(chunks),
        )

    except ContextWindowError as exc:
        await db.rollback()
        return IngestFileResult(file_name=file_name, status="error", error_message=str(exc))
    except UnicodeDecodeError as exc:
        await db.rollback()
        return IngestFileResult(
            file_name=file_name,
            status="error",
            error_message=f"Không đọc được Markdown bằng UTF-8: {exc}.",
        )
    except Exception as exc:
        await db.rollback()
        logger.error("Error ingesting '%s': %s", file_name, exc, exc_info=True)
        return IngestFileResult(file_name=file_name, status="error", error_message=str(exc))


async def run_ingest_pipeline(
    db: AsyncSession,
    rag_dir: Path = DEFAULT_RAG_DIR,
    gemini_api_key: Optional[str] = None,
) -> IngestReport:
    if not rag_dir.exists():
        logger.warning("RAG directory does not exist: %s", rag_dir)
        return IngestReport()

    all_files = [file_path for file_path in rag_dir.rglob("*") if file_path.is_file()]
    markdown_file_paths = {str(file_path) for file_path in all_files if _is_markdown(file_path)}

    report = IngestReport(total_scanned=len(all_files))
    logger.info("Starting Markdown ingest: found %s files in '%s'.", len(all_files), rag_dir)

    for file_path in all_files:
        result = await ingest_file(file_path, db, gemini_api_key=gemini_api_key)
        report.results.append(result)

        if result.status in ("success", "updated"):
            report.total_success += 1
        elif result.status == "skipped":
            report.total_skipped += 1
        else:
            report.total_error += 1

    db_docs_result = await db.execute(select(RagDocument))
    db_docs = db_docs_result.scalars().all()

    for doc in db_docs:
        if doc.file_path not in markdown_file_paths:
            logger.info("Source file for '%s' is gone or unsupported; deleting DB record.", doc.file_name)
            await db.delete(doc)
            report.total_deleted += 1

    if report.total_deleted > 0:
        await db.commit()

    logger.info(
        "Ingest completed: %s success/update, %s skipped, %s errors, %s deleted.",
        report.total_success,
        report.total_skipped,
        report.total_error,
        report.total_deleted,
    )
    return report
