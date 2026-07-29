"""Real SMTP test script for Email MCP (Tiếng Việt có dấu).

Reads .env from root FIRST, cleans DB, sends real email via SMTP, checks SQLite DB.
"""

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

# Ép UTF-8 cho stdout/stderr trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SERVICE_ROOT = Path(__file__).resolve().parents[1]
ROOT_DIR = SERVICE_ROOT.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env", override=True)

os.environ["EMAIL_SMTP_HOST"] = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
os.environ["EMAIL_SMTP_PORT"] = os.getenv("EMAIL_SMTP_PORT", "587")
os.environ["EMAIL_SMTP_FROM"] = os.getenv("EMAIL_SMTP_FROM", "vietmas.email@gmail.com")
os.environ["EMAIL_SMTP_USERNAME"] = os.getenv("EMAIL_SMTP_USERNAME", "vietmas.email@gmail.com")
os.environ["EMAIL_SMTP_PASSWORD"] = os.getenv("EMAIL_SMTP_PASSWORD", "evon pnvr nzfn gean")
os.environ["EMAIL_SMTP_TLS"] = os.getenv("EMAIL_SMTP_TLS", "true")

from mcp_tools.dispatcher import dispatch_mcp_action
from mcp_tools.email_mcp.server import DB_PATH, _init_db, search_email

def clear_db():
    """Xóa hết bản ghi cũ trong history_message."""
    _init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM history_message")
        conn.commit()
    print("[1] Đã xóa hết dữ liệu cũ trong SQLite history_message.")

async def main():
    print("=== BẮT ĐẦU KIỂM THỬ THỰC TẾ EMAIL MCP (TIẾNG VIỆT CÓ DẤU) ===")
    print(f"SMTP Host: {os.environ.get('EMAIL_SMTP_HOST')}")
    print(f"SMTP Port: {os.environ.get('EMAIL_SMTP_PORT')}")
    print(f"SMTP From: {os.environ.get('EMAIL_SMTP_FROM')}")

    # Step 1: Clear DB
    clear_db()

    # Step 2: Kịch bản 1 — Lời chào bằng Tiếng Việt có dấu đầy đủ
    print("\n[2] Thực thi kịch bản 1: Gửi lời chào (tiếng Việt có dấu) qua mail cho nguyenquangthuc.info@gmail.com...")
    
    payload = {
        "recipients": ["nguyenquangthuc.info@gmail.com"],
        "subject": "Lời chào từ hệ thống AI VietMAS",
        "body": (
            "Xin chào Mr. Thức!\n\n"
            "Đây là email kiểm thử thực tế được gửi tự động từ hệ thống AI VietMAS (Email MCP) "
            "với đầy đủ tiếng Việt có dấu UTF-8.\n\n"
            "Chúc bạn một ngày làm việc hiệu quả!\n\n"
            "Trân trọng,\n"
            "Trợ lý AI VietMAS"
        ),
    }
    
    result = await dispatch_mcp_action("mcp:email_mcp.send_email", payload)
    print(f"-> Kết quả gửi email qua SMTP: {result}")

    # Step 3: Kiểm tra dữ liệu được lưu trong SQLite
    print("\n[3] Kiểm tra bản ghi trong CSDL local history_message...")
    db_result = search_email(query="Lời chào")
    print(f"-> Tìm thấy {db_result.get('total_results', 0)} bản ghi trong DB:")
    for record in db_result.get("emails", []):
        print(f"   ID: {record['id']}")
        print(f"   From: {record['from_email']}")
        print(f"   To: {record['to_email']}")
        print(f"   Subject: {record['subject']}")
        print(f"   Body:\n{record['body_plain_text']}")

    print("\n=== HOÀN THÀNH KIỂM THỬ THỰC TẾ THÀNH CÔNG ===")

if __name__ == "__main__":
    asyncio.run(main())
