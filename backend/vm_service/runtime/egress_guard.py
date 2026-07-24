import logging
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Outbound Whitelist: Chỉ cho phép VM kết nối tới EK Service và Official LLM APIs
ALLOWED_EGRESS_HOSTS = {
    "localhost",
    "127.0.0.1",
    "host.docker.internal",   # Docker Desktop trên Windows/macOS giao tiếp qua host này
    "ek-service",
    "vietmas-ek-service",
    "ek",
    "generativelanguage.googleapis.com",
    "api.anthropic.com",
}

# Đường dẫn file cảnh báo bảo mật dành cho Admin
SECURITY_ALERT_LOG = Path("/app/logs/security_alerts.log")


def _alert_admin_security_violation(blocked_host: str, full_url: str) -> None:
    """
    Ghi cảnh báo bảo mật nghiêm trọng (CRITICAL) vào file log riêng biệt dành cho Admin.
    File này tách biệt khỏi application log thông thường để Admin dễ phát hiện và giám sát.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"

    alert_lines = [
        "=" * 72,
        f"[SECURITY ALERT] EGRESS VIOLATION DETECTED — {timestamp}",
        "=" * 72,
        f"  Service         : VietMAS VM Service",
        f"  Host Machine    : {hostname}",
        f"  Environment     : {os.getenv('APP_ENV', 'unknown')}",
        f"  Blocked Host    : {blocked_host}",
        f"  Full URL        : {full_url}",
        f"  Policy          : VM_EGRESS_WHITELIST",
        f"  Action Taken    : Service startup blocked — PermissionError raised",
        "-" * 72,
        "  [ACTION REQUIRED] Kiểm tra biến môi trường EK_SERVICE_URL trong file .env.",
        "  Nếu đây là tấn công, hãy cô lập container VM Service ngay lập tức.",
        "=" * 72,
        "",
    ]

    alert_text = "\n".join(alert_lines)

    # Ghi vào application log ở cấp CRITICAL để hiện thị rõ trong stdout/container logs
    logger.critical("\n" + alert_text)

    # Ghi vào file security_alerts.log riêng biệt để Admin tra cứu
    try:
        SECURITY_ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SECURITY_ALERT_LOG.open("a", encoding="utf-8") as f:
            f.write(alert_text)
    except Exception as write_err:
        logger.error(f"Could not write security alert to file: {write_err}")


def validate_egress_url(url: str) -> None:
    """
    Kiểm tra bảo mật kết nối đầu ra (Outbound Egress Guard).
    Cấm tuyệt đối VM Service gửi request đến các domain/IP lạ ngoài danh sách trắng.
    Nếu phát hiện vi phạm, ghi cảnh báo CRITICAL gửi Admin và từ chối khởi động.
    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        return

    if hostname not in ALLOWED_EGRESS_HOSTS:
        _alert_admin_security_violation(blocked_host=hostname, full_url=url)
        raise PermissionError(
            f"[SECURITY] Egress Violation: VM Service bị chặn kết nối đến '{hostname}'. "
            f"Chi tiết đã được ghi vào {SECURITY_ALERT_LOG}. "
            f"Vui lòng kiểm tra biến môi trường EK_SERVICE_URL."
        )



class ContentSecurityPolicyMiddleware(BaseHTTPMiddleware):
    """Middleware thiết lập Content Security Policy (CSP) và các Header bảo mật nghiêm ngặt."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        
        # CSP Policy: Chỉ cho phép kết nối nội bộ EK và API LLM chính thức
        csp_policy = (
            "default-src 'none'; "
            "script-src 'self'; "
            "connect-src 'self' http://localhost:8000 http://localhost:8001 https://generativelanguage.googleapis.com https://api.anthropic.com; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline';"
        )
        
        response.headers["Content-Security-Policy"] = csp_policy
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
