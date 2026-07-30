"""SMTP and IMAP-backed email MCP.

Provides tools:
- send_email: Refresh inbox, send plain text email via SMTP, then record outgoing
  email into history_message with from_email = EMAIL_SMTP_FROM.
- check_email: Refresh inbox, filter partner emails into SQLite, move non-partner
  emails to Other folder.
- search_email: Search stored email history in SQLite. Determines thread reply status
  by checking whether the latest email in the thread is from EMAIL_SMTP_FROM.
"""

import datetime as _dt
import email
import email.utils
from email.header import decode_header
from email.message import EmailMessage
from email.policy import SMTP
import imaplib
import json
import os
from pathlib import Path
import smtplib
import sqlite3
from typing import Any
import urllib.request

from core.config import settings


DB_PATH = Path(__file__).resolve().parent / "email_history.db"

_SENT_UID_BASE = -1


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history_message (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT,
                thread_id       TEXT,
                from_name       TEXT,
                from_email      TEXT,
                to_email        TEXT,
                Cc              TEXT,
                body_plain_text TEXT,
                subject         TEXT,
                message_id      TEXT UNIQUE,
                in_reply_to     TEXT,
                references_ids  TEXT,
                imap_uid        INTEGER,
                source_mailbox  TEXT
            )
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(history_message)").fetchall()}
        if "source_mailbox" not in columns:
            conn.execute("ALTER TABLE history_message ADD COLUMN source_mailbox TEXT")
        try:
            conn.execute("UPDATE history_message SET thread_id = message_id WHERE thread_id IS NULL OR thread_id = ''")
        except Exception:
            pass
        conn.commit()


_init_db()


def _company_email() -> str:
    return (os.getenv("EMAIL_SMTP_FROM") or settings.EMAIL_SMTP_FROM or "").strip().lower()


def _get_partner_whitelist() -> set[str]:
    whitelist: set[str] = set()

    env_whitelist = os.getenv("EMAIL_PARTNER_WHITELIST", "")
    if env_whitelist:
        for item in env_whitelist.split(","):
            val = item.strip().lower()
            if val:
                whitelist.add(val)

    ek_url = (os.getenv("EK_SERVICE_URL") or settings.EK_SERVICE_URL).rstrip("/")
    api_key = os.getenv("EK_INTERNAL_API_KEY") or settings.EK_INTERNAL_API_KEY
    if ek_url:
        try:
            req = urllib.request.Request(
                f"{ek_url}/internal/v1/business/partners",
                headers={"X-Internal-Api-Key": api_key},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    for partner in data.get("partners", []):
                        p_email = (partner.get("email") or "").strip().lower()
                        if p_email:
                            whitelist.add(p_email)
                            if "@" in p_email:
                                whitelist.add(p_email.split("@")[-1])
        except Exception:
            pass

    if not whitelist:
        whitelist.update([
            "nguyenquangthuc.info1@gmail.com",
            "nguyenquangthuc.info2@gmail.com",
            "nguyenquangthuc.info3@gmail.com",
            "anphat.com",
            "binhminh.com",
        ])

    return whitelist


def _decode_str(header_val: Any) -> str:
    if not header_val:
        return ""
    decoded_fragments = decode_header(str(header_val))
    parts = []
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(str(fragment))
    return "".join(parts)


def _insert_message(
    conn: sqlite3.Connection,
    *,
    date: str,
    thread_id: str,
    from_name: str,
    from_email: str,
    to_email: str,
    cc: str,
    body_plain_text: str,
    subject: str,
    message_id: str,
    in_reply_to: str,
    references_ids: str,
    imap_uid: int,
    source_mailbox: str = "",
) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO history_message
        (date, thread_id, from_name, from_email, to_email, Cc, body_plain_text,
         subject, message_id, in_reply_to, references_ids, imap_uid, source_mailbox)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            date,
            thread_id,
            from_name,
            from_email,
            to_email,
            cc,
            body_plain_text,
            subject,
            message_id,
            in_reply_to,
            references_ids,
            imap_uid,
            source_mailbox,
        ),
    )
    return cursor.rowcount > 0


def _resolve_mailbox(imap: imaplib.IMAP4_SSL, desired: str) -> str:
    try:
        status, rows = imap.list()
        if status == "OK":
            desired_key = desired.strip().casefold()
            for row in rows or []:
                if not isinstance(row, bytes):
                    continue
                text = row.decode("utf-8", errors="replace").strip()
                if text.endswith('"') and '"' in text[:-1]:
                    mailbox_name = text.rsplit('"', 2)[-2]
                else:
                    mailbox_name = text.rsplit(" ", 1)[-1]
                if mailbox_name.strip().casefold() == desired_key:
                    return mailbox_name.strip()
    except Exception:
        pass
    return desired


def refresh_inbox() -> dict[str, Any]:
    _init_db()

    host = (os.getenv("EMAIL_IMAP_HOST") or settings.EMAIL_IMAP_HOST).strip()
    username = (os.getenv("EMAIL_IMAP_USERNAME") or settings.EMAIL_IMAP_USERNAME).strip()
    password = os.getenv("EMAIL_IMAP_PASSWORD") or settings.EMAIL_IMAP_PASSWORD
    port = int(os.getenv("EMAIL_IMAP_PORT") or settings.EMAIL_IMAP_PORT or 993)
    mailbox = (os.getenv("EMAIL_IMAP_MAILBOX") or settings.EMAIL_IMAP_MAILBOX or "INBOX").strip()
    partner_mailbox = (
        os.getenv("EMAIL_IMAP_PARTNER_MAILBOX")
        or settings.EMAIL_IMAP_PARTNER_MAILBOX
        or "Partner"
    ).strip()

    if not host or not username or not password:
        return {
            "status": "skipped",
            "reason": "Chưa cấu hình thông tin kết nối EMAIL_IMAP_HOST/USERNAME/PASSWORD",
            "imported_count": 0,
            "moved_other_count": 0,
            "moved_partner_count": 0,
        }

    whitelist = _get_partner_whitelist()
    company = _company_email()

    with _get_db() as conn:
        row = conn.execute("SELECT MAX(imap_uid) as max_uid FROM history_message WHERE imap_uid > 0").fetchone()
        max_uid = row["max_uid"] if row and row["max_uid"] is not None else 0

    imported_count = 0
    moved_count = 0
    moved_partner_count = 0

    try:
        imap = imaplib.IMAP4_SSL(host, port)
        imap.login(username, password)
        imap_status, _ = imap.select(mailbox)
        if imap_status != "OK":
            return {
                "status": "error",
                "reason": f"Không thể chọn mailbox {mailbox}",
                "imported_count": 0,
                "moved_other_count": 0,
                "moved_partner_count": 0,
            }

        search_criterion = f"UID {max_uid + 1}:*" if max_uid > 0 else "ALL"
        imap_status, data = imap.uid("search", None, search_criterion)
        if imap_status != "OK" or not data or not data[0]:
            imap.logout()
            sent_res = _refresh_sent_mail()
            return {
                "status": "partial" if sent_res.get("status") == "error" else "success",
                "imported_count": 0,
                "moved_other_count": 0,
                "moved_partner_count": 0,
                "imported_sent_count": sent_res.get("imported_count", 0),
                "sent_sync_status": sent_res.get("status"),
                "sent_sync_error": sent_res.get("error") or sent_res.get("reason"),
            }

        uids = [int(u) for u in data[0].split() if int(u) > max_uid]
        if not uids:
            imap.logout()
            sent_res = _refresh_sent_mail()
            return {
                "status": "partial" if sent_res.get("status") == "error" else "success",
                "imported_count": 0,
                "moved_other_count": 0,
                "moved_partner_count": 0,
                "imported_sent_count": sent_res.get("imported_count", 0),
                "sent_sync_status": sent_res.get("status"),
                "sent_sync_error": sent_res.get("error") or sent_res.get("reason"),
            }

        try:
            imap.create("Other")
        except Exception:
            pass
        partner_mailbox = _resolve_mailbox(imap, partner_mailbox)
        try:
            imap.create(partner_mailbox)
        except Exception:
            pass

        with _get_db() as conn:
            for uid in uids:
                imap_status, msg_data = imap.uid("fetch", str(uid), "(RFC822)")
                if imap_status != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                if not isinstance(raw_email, bytes):
                    continue
                msg = email.message_from_bytes(raw_email)

                from_header = _decode_str(msg.get("From", ""))
                from_name, from_email_addr = email.utils.parseaddr(from_header)
                from_email_addr = from_email_addr.lower().strip()
                from_domain = from_email_addr.split("@")[-1] if "@" in from_email_addr else ""

                is_partner = (from_email_addr in whitelist) or (from_domain in whitelist)

                if not is_partner:
                    try:
                        res = imap.uid("copy", str(uid), "Other")
                        if res[0] == "OK":
                            imap.uid("store", str(uid), "+FLAGS", "\\Deleted")
                            moved_count += 1
                    except Exception:
                        pass
                else:
                    try:
                        res = imap.uid("copy", str(uid), partner_mailbox)
                        if res[0] == "OK":
                            imap.uid("store", str(uid), "+FLAGS", "\\Deleted")
                            moved_partner_count += 1
                    except Exception:
                        pass
                    body_plain_text = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition", ""))
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    charset = part.get_content_charset() or "utf-8"
                                    body_plain_text += payload.decode(charset, errors="replace") + "\n"
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            charset = msg.get_content_charset() or "utf-8"
                            body_plain_text = payload.decode(charset, errors="replace")

                    parsed_msg_id = _decode_str(msg.get("Message-ID", f"generated-{uid}"))
                    parsed_thread_id = _decode_str(msg.get("X-GM-THRID", msg.get("Thread-Index", ""))) or parsed_msg_id

                    inserted = _insert_message(
                        conn,
                        date=_decode_str(msg.get("Date", "")),
                        thread_id=parsed_thread_id,
                        from_name=from_name,
                        from_email=from_email_addr,
                        to_email=_decode_str(msg.get("To", "")),
                        cc=_decode_str(msg.get("Cc", "")),
                        body_plain_text=body_plain_text.strip(),
                        subject=_decode_str(msg.get("Subject", "")),
                        message_id=parsed_msg_id,
                        in_reply_to=_decode_str(msg.get("In-Reply-To", "")),
                        references_ids=_decode_str(msg.get("References", "")),
                        imap_uid=uid,
                        source_mailbox=mailbox,
                    )
                    if inserted:
                        imported_count += 1

            conn.commit()

        imap.expunge()
        imap.logout()

    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "imported_count": imported_count,
            "moved_other_count": moved_count,
            "moved_partner_count": moved_partner_count,
        }

    sent_res = _refresh_sent_mail()
    return {
        "status": "partial" if sent_res.get("status") == "error" else "success",
        "imported_count": imported_count,
        "moved_other_count": moved_count,
        "moved_partner_count": moved_partner_count,
        "imported_sent_count": sent_res.get("imported_count", 0),
        "sent_sync_status": sent_res.get("status"),
        "sent_sync_error": sent_res.get("error") or sent_res.get("reason"),
    }


def _refresh_sent_mail() -> dict[str, Any]:
    host = (os.getenv("EMAIL_IMAP_HOST") or settings.EMAIL_IMAP_HOST).strip()
    username = (os.getenv("EMAIL_IMAP_USERNAME") or settings.EMAIL_IMAP_USERNAME).strip()
    password = os.getenv("EMAIL_IMAP_PASSWORD") or settings.EMAIL_IMAP_PASSWORD
    port = int(os.getenv("EMAIL_IMAP_PORT") or settings.EMAIL_IMAP_PORT or 993)
    desired_mailbox = (
        os.getenv("EMAIL_IMAP_SENT_MAILBOX")
        or settings.EMAIL_IMAP_SENT_MAILBOX
        or "[Gmail]/Sent Mail"
    ).strip()
    company = _company_email()

    if not host or not username or not password:
        return {
            "status": "skipped",
            "reason": "Chưa cấu hình thông tin kết nối IMAP để đồng bộ Sent Mail",
            "imported_count": 0,
        }

    imported_count = 0
    try:
        imap = imaplib.IMAP4_SSL(host, port)
        imap.login(username, password)
        mailbox = _resolve_mailbox(imap, desired_mailbox)
        imap_status, _ = imap.select(f'"{mailbox}"', readonly=True)
        if imap_status != "OK":
            imap.logout()
            return {
                "status": "error",
                "reason": f"Không thể chọn Sent mailbox {desired_mailbox}",
                "imported_count": 0,
            }

        with _get_db() as conn:
            row = conn.execute(
                "SELECT MAX(imap_uid) AS max_uid FROM history_message "
                "WHERE imap_uid > 0 AND source_mailbox = ?",
                (mailbox,),
            ).fetchone()
            max_uid = row["max_uid"] if row and row["max_uid"] is not None else 0

        search_criterion = f"UID {max_uid + 1}:*" if max_uid > 0 else "ALL"
        imap_status, data = imap.uid("search", None, search_criterion)
        if imap_status != "OK" or not data or not data[0]:
            imap.logout()
            return {"status": "success", "imported_count": 0, "mailbox": mailbox}

        with _get_db() as conn:
            for uid in (int(value) for value in data[0].split()):
                if uid <= max_uid:
                    continue
                fetch_status, msg_data = imap.uid("fetch", str(uid), "(RFC822)")
                if fetch_status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_email = msg_data[0][1]
                if not isinstance(raw_email, bytes):
                    continue
                msg = email.message_from_bytes(raw_email)
                from_header = _decode_str(msg.get("From", ""))
                from_name, from_email_addr = email.utils.parseaddr(from_header)
                from_email_addr = from_email_addr.lower().strip()
                if from_email_addr != company:
                    continue

                body_plain_text = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition", ""))
                        if content_type == "text/plain" and "attachment" not in content_disposition:
                            payload = part.get_payload(decode=True)
                            if payload:
                                charset = part.get_content_charset() or "utf-8"
                                body_plain_text += payload.decode(charset, errors="replace") + "\n"
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or "utf-8"
                        body_plain_text = payload.decode(charset, errors="replace")

                message_id = _decode_str(msg.get("Message-ID", f"generated-sent-{uid}"))
                inserted = _insert_message(
                    conn,
                    date=_decode_str(msg.get("Date", "")),
                    thread_id=_decode_str(msg.get("X-GM-THRID", msg.get("Thread-Index", ""))) or message_id,
                    from_name=from_name,
                    from_email=from_email_addr,
                    to_email=_decode_str(msg.get("To", "")),
                    cc=_decode_str(msg.get("Cc", "")),
                    body_plain_text=body_plain_text.strip(),
                    subject=_decode_str(msg.get("Subject", "")),
                    message_id=message_id,
                    in_reply_to=_decode_str(msg.get("In-Reply-To", "")),
                    references_ids=_decode_str(msg.get("References", "")),
                    imap_uid=uid,
                    source_mailbox=mailbox,
                )
                if inserted:
                    imported_count += 1
            conn.commit()
        imap.logout()
    except Exception as exc:
        return {"status": "error", "error": str(exc), "imported_count": imported_count}

    return {"status": "success", "imported_count": imported_count, "mailbox": mailbox}


def _refresh_for_tool() -> dict[str, Any]:
    return refresh_inbox()


def get_tools() -> list[dict[str, str]]:
    return [
        {
            "name": "send_email",
            "description": (
                "Gửi email văn bản đến một hoặc nhiều người nhận qua SMTP; "
                "cần subject, body và danh sách recipients."
            ),
            "input_description": (
                "Danh sách recipients, subject và body dạng văn bản thuần. "
                "Tham số tùy chọn: in_reply_to (Message-ID của mail cần trả lời), "
                "thread_id (để ghép vào luồng hội thoại đúng), references (chuỗi Message-ID tham chiếu)."
            ),
            "output_description": "Trạng thái gửi email và số lượng người nhận.",
        },
        {
            "name": "check_email",
            "description": (
                "Kiểm tra hòm thư inbox, tự động di chuyển email không thuộc đối tác sang thư mục Other "
                "và cập nhật các email đối tác mới vào cơ sở dữ liệu lịch sử."
            ),
            "input_description": "Không yêu cầu tham số bắt buộc. Tự động đồng bộ inbox.",
            "output_description": "Trạng thái thực thi, số lượng mail đối tác mới và mail đã chuyển sang Other.",
        },
        {
            "name": "search_email",
            "description": (
                "Tìm kiếm lịch sử email trong cơ sở dữ liệu dựa trên từ khóa, người gửi, "
                "khoảng thời gian hoặc lọc các thread mà công ty CHƯA phản hồi "
                "(thư mới nhất trong thread không phải do EMAIL_SMTP_FROM gửi)."
            ),
            "input_description": (
                "Các tham số tùy chọn: query (từ khóa trong tiêu đề/nội dung), "
                "sender (email người gửi), "
                "date_from (lọc thư từ thời điểm ISO 8601, ví dụ '2026-07-01'), "
                "only_unreplied=true (chỉ lấy thread chưa phản hồi), limit (mặc định 10)."
            ),
            "output_description": "Danh sách bản ghi email khớp điều kiện tìm kiếm.",
        },
    ]


def send_email(
    *,
    recipients: list[str],
    subject: str,
    body: str,
    user_id: str | None = None,
    reply_uid: int | str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    sync_result = _refresh_for_tool()
    if sync_result.get("status") == "error":
        raise RuntimeError(f"Không thể đồng bộ email trước khi gửi: {sync_result.get('error') or sync_result.get('reason')}")

    host = (os.getenv("EMAIL_SMTP_HOST") or settings.EMAIL_SMTP_HOST).strip()
    sender = _company_email()
    if not host or not sender:
        raise RuntimeError("Email MCP chưa được cấu hình EMAIL_SMTP_HOST/EMAIL_SMTP_FROM")
    if not recipients:
        raise ValueError("Email cần ít nhất một người nhận")

    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    sent_message_id = f"sent-{now_iso.replace(':', '-')}@vietmas.local"
    sent_uid = _SENT_UID_BASE - int(_dt.datetime.now(_dt.timezone.utc).timestamp() * 1000)

    message = EmailMessage(policy=SMTP)
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message["Message-ID"] = sent_message_id
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references
    message.set_content(body, subtype="plain", charset="utf-8")

    port = int(os.getenv("EMAIL_SMTP_PORT") or settings.EMAIL_SMTP_PORT)
    username = (os.getenv("EMAIL_SMTP_USERNAME") or settings.EMAIL_SMTP_USERNAME).strip()
    password = os.getenv("EMAIL_SMTP_PASSWORD") or settings.EMAIL_SMTP_PASSWORD
    use_tls = (os.getenv("EMAIL_SMTP_TLS") or str(settings.EMAIL_SMTP_TLS)).lower() == "true"
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        if use_tls:
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)

    resolved_thread_id = thread_id or ""
    if not resolved_thread_id and in_reply_to:
        with _get_db() as conn:
            row = conn.execute(
                "SELECT thread_id FROM history_message WHERE message_id = ? LIMIT 1",
                (in_reply_to,),
            ).fetchone()
            if row and row["thread_id"]:
                resolved_thread_id = row["thread_id"]

    try:
        with _get_db() as conn:
            _insert_message(
                conn,
                date=now_iso,
                thread_id=resolved_thread_id,
                from_name="",
                from_email=sender,
                to_email=", ".join(recipients),
                cc="",
                body_plain_text=body,
                subject=subject,
                message_id=sent_message_id,
                in_reply_to=in_reply_to or "",
                references_ids=references or "",
                imap_uid=sent_uid,
                source_mailbox="SMTP",
            )
            conn.commit()
    except Exception:
        pass

    result: dict[str, Any] = {
        "status": "sent",
        "recipients": str(len(recipients)),
        "sync_status": sync_result.get("status", "success"),
    }
    if user_id:
        result["sent_by"] = user_id
    if reply_uid is not None:
        result["replied_uid"] = str(reply_uid)
    return result


def check_email(*, user_id: str | None = None) -> dict[str, Any]:
    res = _refresh_for_tool()
    _init_db()
    with _get_db() as conn:
        history_count = conn.execute("SELECT COUNT(*) FROM history_message").fetchone()[0]
    return {
        "status": res.get("status", "success"),
        "imported_partner_emails": res.get("imported_count", 0),
        "moved_partner_emails": res.get("moved_partner_count", 0),
        "moved_other_emails": res.get("moved_other_count", 0),
        "imported_sent_emails": res.get("imported_sent_count", 0),
        "sent_sync_status": res.get("sent_sync_status"),
        "history_count": history_count,
        "details": res.get("reason") or res.get("error") or "Đã làm mới inbox thành công.",
    }


def search_email(
    *,
    query: str = "",
    sender: str = "",
    date_from: str = "",
    only_unreplied: bool = False,
    limit: int = 10,
    user_id: str | None = None,
) -> dict[str, Any]:
    sync_result = _refresh_for_tool()
    _init_db()

    company = _company_email()

    if only_unreplied:
        base_sql = """
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
                   h.to_email, h.Cc, h.body_plain_text, h.subject,
                   h.message_id, h.in_reply_to, h.references_ids, h.imap_uid
            FROM history_message h
            JOIN unreplied_threads u ON h.thread_id = u.thread_id
            WHERE 1=1
        """
        params: list[Any] = [company]
    else:
        base_sql = """
            SELECT id, date, thread_id, from_name, from_email, to_email, Cc,
                   body_plain_text, subject, message_id, in_reply_to,
                   references_ids, imap_uid
            FROM history_message
            WHERE 1=1
        """
        params = []

    if sender:
        base_sql += " AND (LOWER(h.from_email) LIKE ? OR LOWER(h.from_name) LIKE ?)" if only_unreplied else \
                    " AND (LOWER(from_email) LIKE ? OR LOWER(from_name) LIKE ?)"
        params.extend([f"%{sender.lower()}%", f"%{sender.lower()}%"])

    if query:
        base_sql += " AND (LOWER(h.subject) LIKE ? OR LOWER(h.body_plain_text) LIKE ?)" if only_unreplied else \
                    " AND (LOWER(subject) LIKE ? OR LOWER(body_plain_text) LIKE ?)"
        params.extend([f"%{query.lower()}%", f"%{query.lower()}%"])

    if date_from:
        base_sql += " AND h.date >= ?" if only_unreplied else " AND date >= ?"
        params.append(date_from)

    base_sql += " ORDER BY h.id DESC LIMIT ?" if only_unreplied else " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    emails = []
    with _get_db() as conn:
        cursor = conn.execute(base_sql, params)
        for row in cursor.fetchall():
            emails.append(dict(row))

    return {
        "status": "partial" if sync_result.get("status") == "error" else "success",
        "sync_status": sync_result.get("status", "success"),
        "sync_error": sync_result.get("error") or sync_result.get("reason"),
        "total_results": len(emails),
        "emails": emails,
    }
