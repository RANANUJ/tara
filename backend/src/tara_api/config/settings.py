"""Environment-backed settings for the Tara backend bootstrap."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Load non-product configuration from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TARA_",
        extra="ignore",
    )

    app_name: str = "Tara API"
    app_version: str = "0.1.0"
    build_revision: str | None = None
    environment: Environment = "development"
    log_level: LogLevel = "INFO"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "sqlite+aiosqlite:///./data/tara.db"
    service_secret: SecretStr = SecretStr("")
    session_absolute_minutes: int = Field(default=1440, ge=5, le=10080)
    session_idle_minutes: int = Field(default=60, ge=5, le=1440)
    health_check_timeout_ms: int = Field(default=1000, ge=10, le=10000)
    websocket_ticket_seconds: int = Field(default=60, ge=10, le=300)
    websocket_hello_seconds: int = Field(default=10, ge=1, le=60)
    websocket_idle_seconds: int = Field(default=120, ge=10, le=3600)
    websocket_session_check_seconds: int = Field(default=15, ge=1, le=300)
    websocket_max_message_bytes: int = Field(default=16384, ge=512, le=1048576)
    websocket_max_connections_per_session: int = Field(default=3, ge=1, le=20)
    websocket_max_events_per_second: int = Field(default=30, ge=1, le=300)
    websocket_max_outgoing_queue: int = Field(default=32, ge=1, le=256)

    def secret_values(self) -> tuple[str, ...]:
        """Return configured secrets for log redaction without exposing them to callers."""
        secret = self.service_secret.get_secret_value()
        return (secret,) if secret else ()

    def logging_context(self) -> dict[str, object]:
        """Return settings suitable for structured logging after formatter redaction."""
        return {
            "app_name": self.app_name,
            "environment": self.environment,
            "log_level": self.log_level,
            "host": self.host,
            "port": self.port,
            "database_url": self.database_url,
            "service_secret": self.service_secret,
        }


@lru_cache
def get_settings() -> Settings:
    """Return cached process settings loaded from the environment."""
    return Settings()
