from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "JobMatch"
    environment: str = "development"
    debug: bool = True

    # --- database -------------------------------------------------------
    # Postgres is the production target. When DATABASE_URL is unset we fall
    # back to a local SQLite file so the app is runnable without a server.
    database_url: str = ""

    # --- auth -----------------------------------------------------------
    secret_key: str = ""
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    bcrypt_rounds: int = 12

    # --- uploads --------------------------------------------------------
    upload_dir: Path = BACKEND_DIR / "var" / "uploads"
    max_upload_bytes: int = 10 * 1024 * 1024

    # --- frontend / CORS ------------------------------------------------
    frontend_origin: str = "http://localhost:3000"
    extra_cors_origins: str = ""

    # --- AI -------------------------------------------------------------
    # Any Anthropic-compatible key enables LLM structuring + explanations.
    # Without it the system uses deterministic fallbacks and says so.
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5"
    llm_timeout_seconds: float = 90.0
    llm_max_output_tokens: int = 4096

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    use_sentence_transformers: bool = True

    # --- job sources ----------------------------------------------------
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "in"
    jsearch_api_key: str = ""
    jsearch_host: str = "jsearch.p.rapidapi.com"
    source_timeout_seconds: float = 30.0
    source_concurrency: int = 4
    max_jobs_per_source_per_query: int = 50

    # --- background tasks ----------------------------------------------
    redis_url: str = ""
    task_worker_threads: int = 4

    # --- rate limiting --------------------------------------------------
    auth_rate_limit_per_minute: int = 20
    upload_rate_limit_per_minute: int = 10

    @field_validator("secret_key", mode="after")
    @classmethod
    def _ensure_secret(cls, v: str) -> str:
        # A generated key is fine for dev (tokens die on restart); production
        # must set SECRET_KEY explicitly or sessions break across replicas.
        return v or secrets.token_urlsafe(48)

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = BACKEND_DIR / "var" / "jobmatch.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+pysqlite:///{db_path.as_posix()}"

    @property
    def is_sqlite(self) -> bool:
        return self.resolved_database_url.startswith("sqlite")

    @property
    def cors_origins(self) -> list[str]:
        origins = [self.frontend_origin]
        origins += [o.strip() for o in self.extra_cors_origins.split(",") if o.strip()]
        return list(dict.fromkeys(origins))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def celery_enabled(self) -> bool:
        return bool(self.redis_url)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
