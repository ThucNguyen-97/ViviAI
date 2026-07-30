from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from llm.adapters import LlmProviderError
from llm.router import llm_router
from llm.schemas import LlmGenerateRequest, LlmGenerateResponse, RouterStatusResponse
from _1__ai_firewall.router import router as chat_router
from _3__executor.mcp_tools.mcp_catalog import catalog_as_rows, refresh_mcp_catalog
from runtime.rag_catalog import refresh_rag_catalog

app = FastAPI(title="VietMAS VM Service", version="0.3.0")


@app.on_event("startup")
async def load_rag_catalog_on_startup() -> None:
    refresh_mcp_catalog()
    await refresh_rag_catalog(force=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "vm-service", "phase": 3}


@app.get("/mcp/catalog", tags=["MCP Catalog"])
async def mcp_catalog():
    """Danh sách tất cả MCP servers và các tools khả dụng."""
    return catalog_as_rows()


@app.get("/llm/status", response_model=RouterStatusResponse)
async def llm_status():
    return llm_router.status()


@app.post("/llm/generate", response_model=LlmGenerateResponse)
async def llm_generate(request: LlmGenerateRequest):
    try:
        return await llm_router.generate(request)
    except LlmProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "provider": exc.provider,
                "error_type": exc.error_type,
                "message": str(exc),
                "retryable": exc.retryable,
            },
        ) from exc


@app.get("/email/history", tags=["Email History"])
async def email_history(
    sender: str = Query(default="", description="Lọc theo email/tên người gửi."),
    query: str = Query(default="", description="Từ khóa trong tiêu đề hoặc nội dung email."),
    date_from: str = Query(default="", description="Lọc thư từ ngày này (ISO 8601, ví dụ '2026-07-01')."),
    only_unreplied: bool = Query(
        default=False,
        description=(
            "Chỉ hiển thị các thread mà email MỚI NHẤT trong thread không phải từ công ty "
            "(tức là công ty chưa phản hồi). Dựa trên from_email so sánh với EMAIL_SMTP_FROM."
        ),
    ),
    limit: int = Query(default=20, ge=1, le=200, description="Số bản ghi tối đa trả về."),
):
    """Xem lịch sử email trong bảng history_message (SQLite local).

    Endpoint này KHÔNG kết nối IMAP. Chỉ đọc dữ liệu đã đồng bộ.
    Trạng thái phản hồi (only_unreplied) được xác định bằng CTE:
    thread bị coi là chưa phản hồi khi email mới nhất trong thread đó
    có from_email KHÁC địa chỉ công ty (EMAIL_SMTP_FROM).
    """
    import sqlite3
    from _3__executor.mcp_tools.email_mcp.server import DB_PATH, _company_email, _init_db

    _init_db()
    company = _company_email()

    params: list = []

    if only_unreplied:
        sql = """
            WITH latest_per_thread AS (
                SELECT thread_id, MAX(id) AS max_id
                FROM history_message
                WHERE thread_id IS NOT NULL AND thread_id != ''
                GROUP BY thread_id
            ),
            unreplied_threads AS (
                SELECT l.thread_id
                FROM latest_per_thread l
                JOIN history_message h
                  ON h.thread_id = l.thread_id AND h.id = l.max_id
                WHERE LOWER(h.from_email) != ?
            )
            SELECT h.id, h.date, h.thread_id, h.from_name, h.from_email,
                   h.to_email, h.Cc, h.subject, h.message_id,
                   h.in_reply_to, h.references_ids, h.imap_uid
            FROM history_message h
            JOIN unreplied_threads u ON h.thread_id = u.thread_id
            WHERE 1=1
        """
        params.append(company)
        alias = "h."
    else:
        sql = """
            SELECT id, date, thread_id, from_name, from_email, to_email,
                   Cc, subject, message_id, in_reply_to, references_ids,
                   imap_uid
            FROM history_message
            WHERE 1=1
        """
        alias = ""

    if sender:
        sql += f" AND (LOWER({alias}from_email) LIKE ? OR LOWER({alias}from_name) LIKE ?)"
        params.extend([f"%{sender.lower()}%", f"%{sender.lower()}%"])
    if query:
        sql += f" AND LOWER({alias}subject) LIKE ?"
        params.append(f"%{query.lower()}%")
    if date_from:
        sql += f" AND {alias}date >= ?"
        params.append(date_from)

    sql += f" ORDER BY {alias}id DESC LIMIT ?"
    params.append(limit)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]
        total_count = conn.execute("SELECT COUNT(*) FROM history_message").fetchone()[0]
        outgoing_count = conn.execute(
            "SELECT COUNT(*) FROM history_message WHERE LOWER(from_email) = ?", (company,)
        ).fetchone()[0]
        incoming_count = total_count - outgoing_count
    finally:
        conn.close()

    return {
        "summary": {
            "total_in_db": total_count,
            "incoming": incoming_count,
            "outgoing": outgoing_count,
            "company_email": company or "(chưa cấu hình EMAIL_SMTP_FROM)",
        },
        "returned": len(rows),
        "filters": {
            "sender": sender or None,
            "query": query or None,
            "date_from": date_from or None,
            "only_unreplied": only_unreplied,
        },
        "records": rows,
    }


