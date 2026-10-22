"""Application configuration loaded from environment variables / .env."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "FixFlow"
    DATABASE_URL: str = "postgresql+psycopg2://fixflow:fixflow@localhost:5432/fixflow"

    SECRET_KEY: str = "dev-only-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    FRONTEND_URL: str = "http://localhost:5173"

    ADMIN_EMAIL: str = "admin@fixflow.dev"
    ADMIN_PASSWORD: str = "Admin@123"

    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    MODEL_DIR: Path = BASE_DIR / "ml_models"
    BACKUP_DIR: Path = BASE_DIR / "backups"
    LOG_DIR: Path = BASE_DIR / "logs"
    MAX_UPLOAD_MB: int = 8

    SMTP_ENABLED: bool = False
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "FixFlow <no-reply@fixflow.local>"

    SCHEDULER_ENABLED: bool = True
    SLA_CHECK_INTERVAL_MINUTES: int = 5

    PG_DUMP_PATH: str = "pg_dump"
    PSQL_PATH: str = "psql"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()

for _d in (settings.UPLOAD_DIR, settings.MODEL_DIR, settings.BACKUP_DIR, settings.LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)
