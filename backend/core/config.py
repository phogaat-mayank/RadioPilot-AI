"""Environment-driven application settings."""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration."""

    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")
    app_name: str = "RadioPilot AI"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./radiopilot.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    admin_email: str = "admin@radiopilot.local"
    admin_password: str = "ChangeThisImmediately123!"
    cors_origins: str = "http://localhost:3000"
    media_directory: str = "media"
    groq_api_key: str = ""
    litellm_model: str = ""
    litellm_api_key: str = ""
    youtube_api_key: str = ""
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    audio_engine: str = "null"
    vlc_output: str = ""
    liquidsoap_host: str = "liquidsoap"
    liquidsoap_port: int = 1234
    liquidsoap_media_prefix: str = "/media"

    @property
    def cors_origin_list(self) -> list[str]:
        """Return the configured CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def media_path(self) -> Path:
        """Return the resolved media storage directory."""
        return Path(self.media_directory).resolve()


@lru_cache
def get_settings() -> Settings:
    """Create one settings instance for the process."""
    return Settings()


settings = get_settings()
