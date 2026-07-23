from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://vietmas:changeme@localhost:5432/vietmas_db"
    )
    REDIS_URL: str = Field(default="redis://:changeme@localhost:6379/0")
    EK_INTERNAL_API_KEY: str = ""

    # RAG / Embedding config
    EMBEDDING_MODEL_NAME: str = "gemini-embedding-2"
    EMBEDDING_DIMENSION: int = 768
    EMBEDDING_CONTEXT_TOKENS: int = 8192
    RAG_DEFAULT_TOP_K: int = 5
    RAG_DEFAULT_SCORE_THRESHOLD: float = 0.7

    # Tesseract OCR path, kept for future offline OCR work.
    TESSERACT_CMD: str = "/usr/bin/tesseract"

    # LLM provider credentials and models.
    GOOGLE_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_LLM_MODEL: str = "gemini-3.1-flash-lite"
    ANTHROPIC_LLM_MODEL: str = "claude-sonnet-5"
    USD_TO_VND_RATE: Decimal = Decimal("26200")

    @property
    def GEMINI_API_KEY(self) -> str:
        """Return the official Google/Gemini key used by RAG embedding."""
        return self.GOOGLE_API_KEY.strip()


settings = Settings()
