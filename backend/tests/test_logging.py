"""Tests for structured logging redaction."""

import logging

from tara_api.config.settings import Settings
from tara_api.observability.logging import REDACTED, JsonFormatter, redact_log_value


def test_sensitive_settings_are_redacted_from_structured_logs() -> None:
    secret = "super-secret-value"
    settings = Settings(_env_file=None, environment="test", service_secret=secret)
    record = logging.LogRecord(
        name="tara_api",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="settings_loaded",
        args=(),
        exc_info=None,
    )
    record.event_data = settings.logging_context()

    rendered = JsonFormatter(settings.secret_values()).format(record)

    assert secret not in rendered
    assert REDACTED in rendered


def test_nested_database_urls_and_tokens_are_redacted() -> None:
    rendered = redact_log_value({"database_url": "sqlite:///private.db", "nested": {"access_token": "opaque-token"}})

    assert rendered == {"database_url": REDACTED, "nested": {"access_token": REDACTED}}
