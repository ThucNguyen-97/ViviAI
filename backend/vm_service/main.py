from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from llm.adapters import LlmProviderError
from llm.router import llm_router
from llm.schemas import LlmGenerateRequest, LlmGenerateResponse, RouterStatusResponse
from orchestrator.chat import router as chat_router
from runtime.egress_guard import ContentSecurityPolicyMiddleware

# Security schemes cho Swagger UI — hiển thị nút Authorize với 3 user-identity headers
_user_id_header = APIKeyHeader(name="X-User-Id", auto_error=False, description="ID người dùng (bắt buộc)")
_user_email_header = APIKeyHeader(name="X-User-Email", auto_error=False, description="Email người dùng")
_user_role_header = APIKeyHeader(name="X-User-Role", auto_error=False, description="Role: admin | ceo | manager")

app = FastAPI(
    title="VietMAS VM Service",
    version="0.3.0",
    dependencies=[
        Depends(_user_id_header),
        Depends(_user_email_header),
        Depends(_user_role_header),
    ],
)

# CSP & Security Headers Middleware (phải đăng ký trước CORS)
app.add_middleware(ContentSecurityPolicyMiddleware)

# CORS: Thu hẹp chỉ cho phép giao tiếp nội bộ (localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-User-Id", "X-User-Email", "X-User-Role"],
)

app.include_router(chat_router)




@app.get("/health")
async def health():
    return {"status": "ok", "service": "vm-service", "phase": 3}


@app.get("/llm/status", response_model=RouterStatusResponse)
async def llm_status():
    return llm_router.status()


@app.post("/llm/generate", response_model=LlmGenerateResponse)
async def llm_generate(request: LlmGenerateRequest):
    try:
        return await llm_router.generate(request)
    except LlmProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "provider": exc.provider,
                "error_type": exc.error_type,
                "message": str(exc),
                "retryable": exc.retryable,
            },
        ) from exc
