"""Application settings, read from environment variables or backend/.env."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Placeholder values that must never be used outside development.
_DEV_SECRET = "local-development-only-secret-do-not-use-in-production"
_UNSAFE_SECRETS = {"", "change-me", _DEV_SECRET}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'smartspend.db').as_posix()}"

    jwt_secret_key: str = _DEV_SECRET
    jwt_access_token_expire_minutes: int = Field(default=30, ge=1, le=24 * 60)
    session_max_days: int = Field(default=7, ge=1, le=90)

    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # auto: Claude when an API key is configured, otherwise the offline demo provider.
    ai_provider: str = "auto"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    ai_timeout_seconds: float = Field(default=20.0, gt=0, le=120)

    # Budget alert thresholds, in percent. "exceeded" fires when spending goes over 100%.
    alert_thresholds: tuple[int, ...] = (75, 90)

    # Request limits (per client IP, per window).
    login_attempts_per_15_min: int = 10
    registrations_per_hour: int = 10
    ai_requests_per_10_min: int = 40

    @field_validator("database_url")
    @classmethod
    def _driver(cls, v: str) -> str:
        """Hosts like Neon and Render hand out postgres:// URLs; SQLAlchemy needs the psycopg driver named."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def check(self) -> None:
        """Refuse to start in production with a placeholder secret."""
        if self.is_production and (self.jwt_secret_key in _UNSAFE_SECRETS or len(self.jwt_secret_key) < 32):
            raise RuntimeError("Set JWT_SECRET_KEY to a long random value before running in production.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
