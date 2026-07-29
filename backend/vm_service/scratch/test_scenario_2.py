"""Real IMAP test script for Email MCP (Kịch bản 2).

Scenario: User says "Hãy kiểm tra hòm thư xem có thư nào mới không"
"""

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

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

# Ghi đè vào os.environ
os.environ["EMAIL_IMAP_HOST"] = os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
os.environ["EMAIL_IMAP_PORT"] = os.getenv("EMAIL_IMAP_PORT", "993")
os.environ["EMAIL_IMAP_MAILBOX"] = os.getenv("EMAIL_IMAP_MAILBOX", "INBOX")
os.environ["EMAIL_IMAP_USERNAME"] = os.getenv("EMAIL_IMAP_USERNAME", "vietmas.email@gmail.com")
os.environ["EMAIL_IMAP_PASSWORD"] = os.getenv("EMAIL_IMAP_PASSWORD", "evon pnvr nzfn gean")

from mcp_tools.dispatcher import dispatch_mcp_action
from mcp_tools.email_mcp.server import DB_PATH, _init_db, search_email

async def main():
    print("=== BẮT ĐẦU KIỂM THỬ THỰC TẾ KỊCH BẢN 2 ===")
    print(f"IMAP Host: {os.environ.get('EMAIL_IMAP_HOST')}:{os.environ.get('EMAIL_IMAP_PORT')}")
    print(f"IMAP Username: {os.environ.get('EMAIL_IMAP_USERNAME')}")

    print("\n[1] Thực thi MCP Tool check_email (Kiểm tra hòm thư)...")
    result = await dispatch_mcp_action("mcp:email_mcp.check_email", {})
    print(f"-> Kết quả check_email: {result}")

    print("\n[2] Kiểm tra kết quả trong SQLite history_message...")
    db_result = search_email()
    print(f"-> Tổng số bản ghi partner trong DB: {db_result.get('total_results', 0)}")
    for record in db_result.get("emails", []):
        print(f"   ID: {record['id']} | Date: {record['date']} | From: {record['from_email']} | Subject: {record['subject']}")

    print("\n=== HOÀN THÀNH KIỂM THỬ KỊCH BẢN 2 ===")

if __name__ == "__main__":
    asyncio.run(main())
