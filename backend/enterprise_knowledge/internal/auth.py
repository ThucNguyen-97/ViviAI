import secrets

from fastapi import Header, HTTPException, status

from core.config import settings


async def require_internal_api_key(
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-Api-Key"),
) -> None:
    expected_key = settings.EK_INTERNAL_API_KEY.strip()
    provided_key = (x_internal_api_key or "").strip()

    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EK_INTERNAL_API_KEY is not configured.",
        )

    if not provided_key or not secrets.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key.",
        )
