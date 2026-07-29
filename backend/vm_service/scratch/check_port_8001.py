"""Test calling running Uvicorn server at http://localhost:8001/v1/chat
"""

import sys
from pathlib import Path
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def check_live_server():
    print("=== TESTING LIVE UVICORN SERVER ON PORT 8001 ===")
    url = "http://localhost:8001/v1/chat"
    headers = {
        "X-User-Id": "test-admin-001",
        "X-User-Role": "admin",
        "accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "message": "Hãy kiểm tra hòm thư xem có thư nào mới không",
        "conversation_id": "string",
    }
    try:
        response = httpx.post(url, headers=headers, data=data, timeout=10.0)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
    except Exception as exc:
        print(f"Failed to connect to live server on port 8001: {exc}")

if __name__ == "__main__":
    check_live_server()
