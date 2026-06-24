from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = (
    BACKEND_DIR.parent
    if (BACKEND_DIR.parent / "frontend").exists()
    else BACKEND_DIR
)
STORAGE_DIR = PROJECT_ROOT / "storage"


def normalize_database_url(url: str) -> str:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url

    path_part = url[len(prefix) :]
    if path_part.startswith("./"):
        resolved = (PROJECT_ROOT / path_part[2:]).resolve()
        return f"{prefix}{resolved}"
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24 * 7
    jwt_algorithm: str = "HS256"
    database_url: str = f"sqlite:///{STORAGE_DIR / 'aitf.db'}"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:4173",
    ]
    # Docker: map localhost/127.0.0.1 in resolved request URLs to the host machine
    runner_host_alias: str | None = None
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_fallback_model: str = "gpt-4o-mini"
    ai_request_timeout_seconds: float = 60.0
    report_base_url: str = "http://localhost:8000/reports"
    report_retention_days: int = 30
    allure_cli: str = "allure"
    feishu_webhook_timeout_seconds: float = 10.0
    scheduler_timezone: str = "Asia/Shanghai"

    @field_validator("database_url", mode="before")
    @classmethod
    def resolve_database_url(cls, value: str) -> str:
        return normalize_database_url(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
