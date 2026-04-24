from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://contextos:contextos@localhost:5432/contextos"
    redis_url: str = "redis://localhost:6379"

    # Extraction
    extraction_provider: Literal["anthropic", "openai", "mock"] = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    anthropic_extraction_model: str = "claude-haiku-4-5-20251001"
    openai_extraction_model: str = "gpt-4o-mini"

    # Embeddings
    # embedding_provider: local | openai
    # local uses sentence-transformers (all-MiniLM-L6-v2, 384 dims, no API key needed)
    # openai uses text-embedding-3-small (1536 dims, requires OPENAI_API_KEY)
    embedding_provider: Literal["local", "openai"] = "local"
    embedding_model: str = "all-MiniLM-L6-v2"   # overridden to text-embedding-3-small when provider=openai
    embedding_dimensions: int = 384               # 384 for local, 1536 for openai

    # Admin
    admin_api_key: str = ""  # Required for app management endpoints. Set via ADMIN_API_KEY env var.

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Retrieval defaults
    default_top_k: int = 10
    min_score_threshold: float = 0.0


settings = Settings()
