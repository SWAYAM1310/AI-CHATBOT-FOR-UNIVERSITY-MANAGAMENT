"""Application settings, loaded from the repo-root .env (see .env.example)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://uniassist:uniassist@localhost:5432/uniassist"

    embedding_dim: int = 1024
    embedding_model: str = "jinaai/jina-embeddings-v5-omni-small"

    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model_router: str = "openai/gpt-oss-20b"
    llm_model_main: str = "openai/gpt-oss-120b"

    # Free-tier survival (plan.md §4). Groq limits are per ORGANISATION, not per
    # user, so these are deliberately below the published ceiling: an evaluator
    # opening the app mid-demo shares it.
    llm_tpm: int = 6000  # tokens/minute the limiter will hand out
    llm_rpm: int = 25  # requests/minute
    llm_max_retries: int = 4  # attempts after a 429 before giving up
    llm_backoff_base: float = 1.0  # seconds; doubles each attempt
    llm_backoff_cap: float = 30.0

    frontend_origin: str = "http://localhost:5173"

    # Auth
    jwt_secret: str = "dev-insecure-change-me-please-0000000000"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 12 * 60

    # Academic context (matches scripts/academic_data.py)
    current_term: str = "2026-27-ODD"


settings = Settings()
