"""Structured logging with conservative secret-redaction foundations."""

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import SecretStr

from tara_api.config.settings import Settings

REDACTED = "[REDACTED]"
SENSITIVE_KEY_PARTS = ("authorization", "cookie", "password", "secret", "token", "api_key", "database_url")


def _is_sensitive_key(key: object) -> bool:
    normalized_key = str(key).lower()
    return any(part in normalized_key for part in SENSITIVE_KEY_PARTS)


def _redact_string(value: str, secret_values: Sequence[str]) -> str:
    redacted_value = value
    for secret in secret_values:
        if secret:
            redacted_value = redacted_value.replace(secret, REDACTED)
    return redacted_value


def redact_log_value(value: object, secret_values: Sequence[str] = ()) -> object:
    """Recursively remove configured secrets and sensitive fields from log values."""
    if isinstance(value, SecretStr):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED
            if _is_sensitive_key(key)
            else redact_log_value(nested_value, secret_values)
            for key, nested_value in value.items()
        }
    if isinstance(value, str):
        return _redact_string(value, secret_values)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_log_value(item, secret_values) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Serialize safe structured log records as JSON."""

    def __init__(self, secret_values: Sequence[str] = ()) -> None:
        super().__init__()
        self._secret_values = tuple(secret_values)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_string(record.getMessage(), self._secret_values),
        }
        event_data = getattr(record, "event_data", None)
        if event_data is not None:
            payload["event"] = redact_log_value(event_data, self._secret_values)
        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(settings: Settings) -> None:
    """Configure the Tara logger with a single structured, redacting handler."""
    logger = logging.getLogger("tara_api")
    logger.setLevel(settings.log_level)
    logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(settings.secret_values()))
    logger.addHandler(handler)
    logger.propagate = False


def log_settings_loaded(settings: Settings) -> None:
    """Emit a safe bootstrap settings event without recording secret values."""
    logging.getLogger("tara_api").info(
        "settings_loaded",
        extra={"event_data": settings.logging_context()},
    )
