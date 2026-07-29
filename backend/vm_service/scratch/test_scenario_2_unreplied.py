"""Test search_email(only_unreplied=True) after real IMAP sync.
"""

import asyncio
import os
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

from mcp_tools.email_mcp.server import search_email

def main():
    print("=== TÌM KIẾM CÁC THƯ ĐẾN CỦA PARTNER MÀ CÔNG TY CHƯA PHẢN HỒI ===")
    
    # search_email với only_unreplied=True
    result = search_email(only_unreplied=True)
    
    print(f"-> Số bản ghi chưa phản hồi: {result.get('total_results', 0)}")
    for record in result.get("emails", []):
        print(f"   ID: {record['id']}")
        print(f"   From: {record['from_email']} ({record['from_name']})")
        print(f"   Subject: {record['subject']}")
        print(f"   Date: {record['date']}")
        print("-" * 50)

if __name__ == "__main__":
    main()
