"""Tests cho email MCP — kiểm thử offline (không kết nối Gmail/IMAP thật).

3 kịch bản thực tế:
  1. Gửi lời chào qua mail (send_email ghi mail đi vào history với from_email = EMAIL_SMTP_FROM)
  2. Kiểm tra thư partner CHƯA PHẢN HỒI
     (dựa vào CTE: email mới nhất trong thread không phải do EMAIL_SMTP_FROM gửi)
  3. Tìm mail theo ngày và từ khóa
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVICE_ROOT not in sys.path:
    sys.path.insert(0, SERVICE_ROOT)

from mcp_tools.dispatcher import dispatch_mcp_action  # noqa: E402
from mcp_tools.email_mcp.server import (  # noqa: E402
    DB_PATH,
    _get_db,
    _init_db,
    _insert_message,
)
from mcp_tools.mcp_catalog import catalog_as_rows  # noqa: E402


# ─── Fake SMTP ────────────────────────────────────────────────────────────────

class FakeSMTP:
    sent_messages: list = []

    def __init__(self, host, port, timeout):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def starttls(self):
        pass

    def login(self, username, password):
        pass

    def send_message(self, message):
        FakeSMTP.sent_messages.append(message)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _seed(
    *,
    from_email: str,
    from_name: str = "",
    subject: str = "Test subject",
    body: str = "Test body",
    imap_uid: int,
    message_id: str,
    thread_id: str = "thread-A",
    in_reply_to: str = "",
    date: str = "Tue, 28 Jul 2026 10:00:00 +0700",
) -> None:
    _init_db()
    with _get_db() as conn:
        _insert_message(
            conn,
            date=date,
            thread_id=thread_id,
            from_name=from_name,
            from_email=from_email,
            to_email="company@vietmas.demo",
            cc="",
            body_plain_text=body,
            subject=subject,
            message_id=message_id,
            in_reply_to=in_reply_to,
            references_ids="",
            imap_uid=imap_uid,
        )
        conn.commit()


SMTP_ENV = {
    "EMAIL_SMTP_HOST": "smtp.gmail.com",
    "EMAIL_SMTP_PORT": "587",
    "EMAIL_SMTP_FROM": "company@vietmas.demo",
    "EMAIL_SMTP_USERNAME": "company@vietmas.demo",
    "EMAIL_SMTP_PASSWORD": "test-password",
    "EMAIL_SMTP_TLS": "true",
    "EMAIL_IMAP_HOST": "",
    "EMAIL_IMAP_USERNAME": "",
    "EMAIL_IMAP_PASSWORD": "",
}


# ─── Catalog test ─────────────────────────────────────────────────────────────

class TestCatalog(unittest.TestCase):
    def test_all_three_tools_registered_with_correct_names(self):
        rows = catalog_as_rows()
        email_tools = {r["tool_name"] for r in rows if r["mcp_name"] == "email_mcp"}
        self.assertIn("send_email", email_tools)
        self.assertIn("check_email", email_tools)
        self.assertIn("search_email", email_tools)
        self.assertNotIn("search_mail", email_tools, "Tên cũ search_mail không còn tồn tại")


# ─── Kịch bản 1: Gửi lời chào ─────────────────────────────────────────────────

class TestCase1_SendGreeting(unittest.TestCase):
    """
    Người dùng: "Hãy gửi một lời chào qua mail cho nguyenquangthuc.info@gmail.com"
    Kỳ vọng:
    - SMTP nhận đúng địa chỉ, tiêu đề
    - Mail đi được ghi vào history_message với from_email = EMAIL_SMTP_FROM
    """

    def setUp(self):
        _init_db()
        FakeSMTP.sent_messages.clear()

    def test_send_email_recorded_in_history_with_company_email(self):
        with patch.dict(os.environ, SMTP_ENV, clear=False), \
             patch("mcp_tools.email_mcp.server.smtplib.SMTP", FakeSMTP), \
             patch("mcp_tools.email_mcp.server.refresh_inbox",
                   return_value={"status": "skipped", "imported_count": 0, "moved_other_count": 0}):

            result = asyncio.run(dispatch_mcp_action(
                "mcp:email_mcp.send_email",
                {
                    "recipients": ["nguyenquangthuc.info@gmail.com"],
                    "subject": "Lời chào từ VietMAS",
                    "body": "Xin chào! Đây là lời chào từ hệ thống VietMAS.",
                },
            ))

        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["recipients"], "1")
        msg = FakeSMTP.sent_messages[-1]
        self.assertEqual(msg["To"], "nguyenquangthuc.info@gmail.com")
        self.assertIn("Xin chào", msg.get_content())

        # Kiểm tra mail đi được ghi vào history_message với from_email của công ty
        with _get_db() as conn:
            row = conn.execute(
                "SELECT * FROM history_message WHERE LOWER(from_email)='company@vietmas.demo' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(row, "Mail đi phải được ghi vào history_message với from_email của công ty")
        self.assertEqual(row["from_email"], "company@vietmas.demo")
        self.assertIn("Lời chào", row["subject"])


# ─── Kịch bản 2: Thread chưa phản hồi ────────────────────────────────────────

class TestCase2_UnrepliedThreads(unittest.TestCase):
    """
    Người dùng: "Kiểm tra hòm thư xem có thư mới nào mà CÔNG TY TA CHƯA PHẢN HỒI không?"

    Thiết lập 2 thread:
      - Thread A: partner gửi đến (id=1), công ty chưa reply → CHƯA PHẢN HỒI
      - Thread B: partner gửi (id=2), công ty reply (id=3, from_email=company) → ĐÃ PHẢN HỒI

    Kỳ vọng only_unreplied=True chỉ trả về Thread A.
    """

    def setUp(self):
        _init_db()
        # Thread A — chưa phản hồi
        _seed(from_email="partner@anphat.com", subject="Yêu cầu báo giá",
              imap_uid=100, message_id="msg-100@anphat.com", thread_id="thread-A")
        # Thread B — partner gửi, công ty đã reply
        _seed(from_email="supplier@binhminh.com", subject="Xác nhận đơn hàng",
              imap_uid=200, message_id="msg-200@binhminh.com", thread_id="thread-B")
        _seed(from_email="company@vietmas.demo", subject="Re: Xác nhận đơn hàng",
              imap_uid=-10, message_id="msg-201@vietmas.local", thread_id="thread-B",
              in_reply_to="msg-200@binhminh.com")

    def test_only_unreplied_returns_only_thread_a(self):
        with patch("mcp_tools.email_mcp.server.refresh_inbox",
                   return_value={"status": "success", "imported_count": 0, "moved_other_count": 0}), \
             patch.dict(os.environ, {"EMAIL_SMTP_FROM": "company@vietmas.demo"}, clear=False):

            result = asyncio.run(dispatch_mcp_action(
                "mcp:email_mcp.search_email",
                {"only_unreplied": True, "limit": 20},
            ))

        self.assertEqual(result["status"], "success")
        subjects = [e["subject"] for e in result["emails"]]
        # Thread A phải xuất hiện
        self.assertIn("Yêu cầu báo giá", subjects)
        # Thread B KHÔNG được xuất hiện (đã phản hồi)
        self.assertNotIn("Xác nhận đơn hàng", subjects)
        self.assertNotIn("Re: Xác nhận đơn hàng", subjects)

    def test_insert_or_ignore_preserves_existing_records(self):
        """INSERT OR IGNORE: chèn lại cùng message_id phải bị bỏ qua, không tăng ID."""
        with _get_db() as conn:
            id_before = conn.execute(
                "SELECT id FROM history_message WHERE message_id='msg-100@anphat.com'"
            ).fetchone()["id"]
            # Cố tình insert lại cùng message_id
            _insert_message(
                conn,
                date="Wed, 29 Jul 2026 10:00:00 +0700",
                thread_id="thread-A",
                from_name="Different Name",
                from_email="partner@anphat.com",
                to_email="company@vietmas.demo",
                cc="",
                body_plain_text="Duplicate attempt",
                subject="Yêu cầu báo giá",
                message_id="msg-100@anphat.com",
                in_reply_to="",
                references_ids="",
                imap_uid=999,
            )
            conn.commit()
            id_after = conn.execute(
                "SELECT id FROM history_message WHERE message_id='msg-100@anphat.com'"
            ).fetchone()["id"]

        self.assertEqual(id_before, id_after, "ID không được thay đổi khi INSERT OR IGNORE")


# ─── Kịch bản 3: Tìm mail theo ngày và từ khóa ───────────────────────────────

class TestCase3_SearchByDateAndKeyword(unittest.TestCase):
    """
    Người dùng: "tìm cho tôi mail nào gửi lúc 2026-07-28"
    """

    def setUp(self):
        _init_db()
        _seed(from_email="partner@anphat.com", subject="Họp review ngày 28",
              body="Chúng tôi muốn họp vào ngày 28 tháng 7.",
              imap_uid=300, message_id="msg-300@anphat.com", thread_id="thread-C",
              date="Tue, 28 Jul 2026 08:30:00 +0700")
        _seed(from_email="partner@anphat.com", subject="Họp định kỳ ngày 10",
              body="Họp định kỳ tháng 7.",
              imap_uid=301, message_id="msg-301@anphat.com", thread_id="thread-D",
              date="Thu, 10 Jul 2026 14:00:00 +0700")

    def test_date_from_filter_excludes_older_emails(self):
        with patch("mcp_tools.email_mcp.server.refresh_inbox",
                   return_value={"status": "success", "imported_count": 0, "moved_other_count": 0}):
            result = asyncio.run(dispatch_mcp_action(
                "mcp:email_mcp.search_email",
                {"date_from": "Tue, 28 Jul 2026", "limit": 10},
            ))

        subjects = [e["subject"] for e in result["emails"]]
        self.assertIn("Họp review ngày 28", subjects)
        self.assertNotIn("Họp định kỳ ngày 10", subjects)

    def test_keyword_search_in_subject_and_body(self):
        with patch("mcp_tools.email_mcp.server.refresh_inbox",
                   return_value={"status": "success", "imported_count": 0, "moved_other_count": 0}):
            result = asyncio.run(dispatch_mcp_action(
                "mcp:email_mcp.search_email",
                {"query": "họp", "limit": 10},
            ))

        self.assertGreaterEqual(result["total_results"], 1)
        for e in result["emails"]:
            combined = (e.get("subject", "") + " " + e.get("body_plain_text", "")).lower()
            self.assertIn("họp", combined)

    def test_check_email_when_imap_not_configured(self):
        with patch.dict(
            os.environ,
            {"EMAIL_IMAP_HOST": "", "EMAIL_IMAP_USERNAME": "", "EMAIL_IMAP_PASSWORD": ""},
            clear=False,
        ):
            result = asyncio.run(dispatch_mcp_action("mcp:email_mcp.check_email", {}))
        self.assertIn(result["status"], {"skipped", "success", "error"})
        self.assertIn("imported_partner_emails", result)


if __name__ == "__main__":
    unittest.main()
