from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
SERVICE_DIR = Path(__file__).resolve().parents[1]

# Nạp .env vào os.environ cho toàn bộ VM service
load_dotenv(ROOT_DIR / ".env", override=True)
load_dotenv(SERVICE_DIR / ".env", override=True)

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", SERVICE_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    REDIS_URL: str = Field(default="redis://:changeme@localhost:6380/0")
    EK_SERVICE_URL: str = Field(default="http://localhost:8000")
    EK_INTERNAL_API_KEY: str = ""

    GOOGLE_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_LLM_MODEL: str = "gemini-3.1-flash-lite"
    ANTHROPIC_LLM_MODEL: str = "claude-sonnet-5"

    LLM_REQUEST_TIMEOUT_SECONDS: float = 45.0
    LLM_MAX_RETRIES: int = 1
    LLM_DEFAULT_MAX_OUTPUT_TOKENS: int = 2048
    LLM_DEFAULT_TEMPERATURE: float = 0.2
    LLM_ENABLE_CROSS_PROVIDER_FALLBACK: bool = True

    CHAT_CONCURRENCY_LIMIT: int = 10
    CHAT_RUNTIME_STATE_TTL_SECONDS: int = 3600
    UPLOAD_DIR: str = "storage/uploads"
    MAX_FILES_PER_REQUEST: int = 2
    MAX_MD_BYTES: int = 2 * 1024 * 1024
    MAX_PNG_BYTES: int = 10 * 1024 * 1024
    RAG_CATALOG_CACHE_TTL_SECONDS: float = 300.0

    EMAIL_SMTP_HOST: str = ""
    EMAIL_SMTP_PORT: int = 587
    EMAIL_SMTP_FROM: str = ""
    EMAIL_SMTP_USERNAME: str = ""
    EMAIL_SMTP_PASSWORD: str = ""
    EMAIL_SMTP_TLS: bool = True
    EMAIL_IMAP_HOST: str = "imap.gmail.com"
    EMAIL_IMAP_PORT: int = 993
    EMAIL_IMAP_MAILBOX: str = "INBOX"
    EMAIL_IMAP_PARTNER_MAILBOX: str = "Partner"
    EMAIL_IMAP_SENT_MAILBOX: str = "[Gmail]/Sent Mail"
    EMAIL_IMAP_USERNAME: str = ""
    EMAIL_IMAP_PASSWORD: str = ""

    # USD per 1M tokens for the configured Phase 2 models.
    GOOGLE_INPUT_USD_PER_MTOK: float = 0.25
    GOOGLE_OUTPUT_USD_PER_MTOK: float = 1.50
    ANTHROPIC_INPUT_USD_PER_MTOK: float = 3.00
    ANTHROPIC_OUTPUT_USD_PER_MTOK: float = 15.00


settings = Settings()
