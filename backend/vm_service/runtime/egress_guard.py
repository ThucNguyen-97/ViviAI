import logging
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


def validate_egress_url(url: str) -> None:
    """
    Kiểm tra bảo mật kết nối đầu ra (Outbound Egress Guard).
    Cấm tuyệt đối VM Service gửi request đến các domain/IP lạ ngoài danh sách trắng.
    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        return

    if hostname not in ALLOWED_EGRESS_HOSTS:
        logger.error(f"SECURITY BLOCK: VM attempt to connect to untrusted egress domain: {hostname}")
        raise PermissionError(
            f"Egress Security Violation: Outbound connections to host '{hostname}' "
            f"are strictly forbidden by VM Security Policy."
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
