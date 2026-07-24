import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from admin.router import router as admin_dashboard_router
from core.config import settings
from business.router import router as business_router
from db.base import get_db
from ingest.pipeline import run_ingest_pipeline, IngestReport
from internal.router import router as internal_router
from rag.router import router as rag_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-Internal-Api-Key", auto_error=False)


class EKSecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware thiết lập Security Headers cho EK Service."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # EK chỉ giao tiếp nội bộ, không có frontend trực tiếp nên CSP cực kỳ hạn chế
        response.headers["Content-Security-Policy"] = "default-src 'none';"
        return response


app = FastAPI(
    title="VietMAS Enterprise Knowledge Service",
    version="0.1.0",
    description="API quản lý tri thức doanh nghiệp: ingest Markdown RAG, truy vấn vector DB.",
    dependencies=[Depends(api_key_header)],
)

# Security Headers Middleware
app.add_middleware(EKSecurityHeadersMiddleware)

# CORS: Thu hẹp — EK chỉ chấp nhận request từ VM Service (localhost:8001)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Internal-Api-Key"],
)

app.include_router(business_router)
app.include_router(rag_router)
app.include_router(admin_dashboard_router)
app.include_router(internal_router)



# ── Health check ────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "ek-service", "phase": 1}


# ── Ingest API ──────────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    message: str
    total_scanned: int
    total_success: int
    total_skipped: int
    total_error: int
    total_deleted: int
    results: list


@app.post("/admin/ingest", response_model=IngestResponse, tags=["Admin - Ingest"])
async def trigger_ingest(
    rag_dir: Optional[str] = Query(
        default=None,
        description="Đường dẫn thư mục Markdown RAG (mặc định: /app/rag_documents)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Kích hoạt pipeline ingest Markdown RAG.

    - Quét thư mục `rag_documents/` (hoặc thư mục được chỉ định).
    - Chỉ ingest file `.md`; các định dạng khác được báo lỗi định dạng.
    - File trùng không đổi sẽ bị bỏ qua; file đổi mtime hoặc size sẽ được ingest lại.
    - Tài liệu vượt ngữ cảnh 8.192 token của `gemini-embedding-2` sẽ bị báo lỗi.
    - Chunk → Embed bằng Google Gen AI SDK → Lưu vào PostgreSQL/pgvector.
    """
    target_dir = Path(rag_dir) if rag_dir else Path("/app/rag_documents")

    if not target_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Thư mục không tồn tại: {target_dir}",
        )

    gemini_key = settings.GEMINI_API_KEY

    report: IngestReport = await run_ingest_pipeline(
        db=db,
        rag_dir=target_dir,
        gemini_api_key=gemini_key,
    )

    return IngestResponse(
        message=(
            f"Ingest hoàn tất: {report.total_success} thành công/cập nhật, "
            f"{report.total_skipped} bỏ qua, {report.total_error} lỗi, "
            f"{report.total_deleted} đã xóa khỏi DB."
        ),
        total_scanned=report.total_scanned,
        total_success=report.total_success,
        total_skipped=report.total_skipped,
        total_error=report.total_error,
        total_deleted=report.total_deleted,
        results=[
            {
                "file_name": r.file_name,
                "status": r.status,
                "chunks_created": r.chunks_created,
                "error_message": r.error_message,
            }
            for r in report.results
        ],
    )


@app.get("/admin/rag-documents", tags=["Admin - Ingest"])
async def list_rag_documents(
    db: AsyncSession = Depends(get_db),
):
    """
    Liệt kê tất cả tài liệu RAG đã được ingest vào DB.
    """
    from sqlalchemy import select, func
    from db.models import RagDocument, Chunk

    # Query tài liệu kèm số chunk
    result = await db.execute(
        select(
            RagDocument.id,
            RagDocument.file_name,
            RagDocument.file_type,
            RagDocument.file_size,
            RagDocument.created_at,
            func.count(Chunk.id).label("chunk_count"),
        )
        .outerjoin(Chunk, Chunk.rag_document_id == RagDocument.id)
        .group_by(RagDocument.id)
        .order_by(RagDocument.created_at.desc())
    )
    rows = result.all()

    return {
        "total": len(rows),
        "documents": [
            {
                "id": str(row.id),
                "file_name": row.file_name,
                "file_type": row.file_type,
                "file_size": row.file_size,
                "chunk_count": row.chunk_count,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@app.delete("/admin/rag-documents/{doc_id}", tags=["Admin - Ingest"])
async def delete_rag_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Xóa một tài liệu RAG và toàn bộ chunk liên quan khỏi DB.
    """
    import uuid as _uuid
    from sqlalchemy import select, delete
    from db.models import RagDocument, Chunk

    try:
        doc_uuid = _uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="doc_id không hợp lệ.")

    doc = await db.get(RagDocument, doc_uuid)
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    await db.delete(doc)
    await db.commit()

    return {"message": f"Đã xóa tài liệu '{doc.file_name}' và tất cả chunks liên quan."}
