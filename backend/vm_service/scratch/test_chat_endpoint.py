"""Test script to invoke POST /v1/chat using FastAPI TestClient and capture full error traceback.
"""

import sys
import traceback
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

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_chat():
    print("=== BẮT ĐẦU TEST POST /v1/chat ===")
    headers = {
        "X-User-Id": "test-admin-001",
        "X-User-Role": "admin",
        "X-User-Email": "admin@vietmas.demo",
    }
    data = {
        "message": "Hãy kiểm tra hòm thư xem có thư nào mới không",
    }
    
    try:
        response = client.post("/v1/chat", headers=headers, data=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
    except Exception as exc:
        print("EXCEPTION CAUGHT:")
        traceback.print_exc()

if __name__ == "__main__":
    test_chat()
