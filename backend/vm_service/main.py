from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from llm.adapters import LlmProviderError
from llm.router import llm_router
from llm.schemas import LlmGenerateRequest, LlmGenerateResponse, RouterStatusResponse
from orchestrator.chat import router as chat_router

app = FastAPI(title="VietMAS VM Service", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
