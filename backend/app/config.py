"""Application settings, loaded from environment variables (and an optional local .env file)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "dev-only-insecure-secret-change-me-0123456789"  # noqa: S105 - refused in production


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    environment: Literal["development", "test", "production"] = "development"
    secret_key: str = INSECURE_DEFAULT_SECRET
    database_url: str = "sqlite:///./accessiscan-dev.db"
    db_pool_size: int = 5
    db_max_overflow: int = 5

    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    trusted_proxy_headers: bool = False
    docs_enabled: bool = True
    registration_enabled: bool = True
    # Demo deployments without a persistent database (e.g. SQLite on an ephemeral disk). Shows a
    # permanent "data is temporary" banner in the UI and is the only way SQLite is allowed in production.
    ephemeral_demo: bool = False

    access_token_minutes: int = Field(default=30, ge=5, le=24 * 60)
    refresh_token_days: int = Field(default=7, ge=1, le=60)
    login_attempts_per_15min: int = 10

    # AI provider layer. "none" disables AI-only features; the app still runs.
    ai_provider: Literal["none", "openai", "anthropic", "gemini"] = "none"
    ai_model: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    ai_timeout_seconds: float = 45.0
    ai_max_output_tokens: int = Field(default=1800, ge=256, le=8000)
    ai_daily_request_limit: int = Field(default=40, ge=0)

    # Scanner limits (hard upper bounds are enforced in code as well).
    scan_max_pages: int = Field(default=10, ge=1, le=50)
    scan_max_depth: int = Field(default=2, ge=0, le=5)
    scan_timeout_seconds: int = Field(default=300, ge=30, le=1800)
    scan_page_timeout_seconds: int = Field(default=30, ge=5, le=120)
    scan_max_page_mb: float = Field(default=15.0, gt=0, le=100)
    scan_max_total_mb: float = Field(default=60.0, gt=0, le=500)
    scan_max_concurrency: int = Field(default=1, ge=1, le=4)
    scan_user_max_active: int = Field(default=2, ge=1, le=10)
    scan_user_hourly_limit: int = Field(default=12, ge=1, le=500)
    scan_crawl_delay_ms: int = Field(default=1000, ge=0, le=30000)
    scan_allowed_ports: str = "80,443,8080,8443"
    scan_max_redirects: int = Field(default=10, ge=0, le=20)
    # Development/test only: "host:port" pairs that may resolve to private addresses (local test sites).
    # Refused in production.
    scanner_allow_hosts: str = ""

    run_embedded_worker: bool = True
    worker_poll_seconds: float = 2.0
    worker_stale_minutes: int = 15
    scheduler_enabled: bool = True

    report_max_issues: int = Field(default=2000, ge=100, le=20000)

    @field_validator("database_url")
    @classmethod
    def normalise_db_url(cls, v: str) -> str:
        # Render/Heroku style URLs -> SQLAlchemy psycopg3 driver.
        if v.startswith("postgres://"):
            v = "postgresql+psycopg://" + v[len("postgres://") :]
        elif v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://") :]
        return v

    @model_validator(mode="after")
    def production_guards(self) -> Settings:
        if self.environment == "production":
            if self.secret_key == INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be set to a random value of at least 32 characters in production")
            if self.scanner_allow_hosts.strip():
                raise ValueError("SCANNER_ALLOW_HOSTS is a development/test setting and is refused in production")
            if "*" in self.cors_origin_list:
                raise ValueError("Wildcard CORS origins are not allowed in production")
            if self.is_sqlite and not self.ephemeral_demo:
                raise ValueError("SQLite is only allowed in production with EPHEMERAL_DEMO=true; use PostgreSQL")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_ports(self) -> set[int]:
        return {int(p) for p in self.scan_allowed_ports.split(",") if p.strip().isdigit()}

    @property
    def allow_hosts(self) -> set[str]:
        return {h.strip().lower() for h in self.scanner_allow_hosts.split(",") if h.strip()}

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def ai_api_key(self) -> str:
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
        }.get(self.ai_provider, "")

    @property
    def ai_enabled(self) -> bool:
        return self.ai_provider != "none" and bool(self.ai_api_key)

    @property
    def effective_ai_model(self) -> str:
        if self.ai_model:
            return self.ai_model
        return {
            "openai": "gpt-5-mini",
            "anthropic": "claude-sonnet-5-5",
            "gemini": "gemini-2.5-flash",
        }.get(self.ai_provider, "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
