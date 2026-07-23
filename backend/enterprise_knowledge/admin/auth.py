from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, status

from core.config import settings


@dataclass(frozen=True)
class AdminViewer:
    user_id: Optional[str]
    role: str


async def require_dashboard_viewer(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> AdminViewer:
    """
    Temporary authorization seam for Admin Dashboard APIs.

    Firebase token verification will replace the header fallback in phase 5. In
    development, missing headers default to admin so Swagger/manual tests remain
    usable before Firebase Auth is wired in.
    """
    role = (x_user_role or "").strip().lower()
    user_id = (x_user_id or "").strip() or None

    if not role and settings.APP_ENV == "development":
        return AdminViewer(user_id=user_id, role="admin")

    if role not in {"admin", "ceo"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ admin hoặc ceo được xem Admin Dashboard.",
        )

    return AdminViewer(user_id=user_id, role=role)


def visible_email_for(viewer: AdminViewer, *, target_user_id: str, target_role: str, email: str) -> Optional[str]:
    if viewer.role == "admin":
        return email
    if target_role == "ceo" and target_user_id != viewer.user_id:
        return None
    return email
