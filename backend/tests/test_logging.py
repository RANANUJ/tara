"""Tests for structured logging redaction."""

import logging

from tara_api.config.settings import Settings
from tara_api.observability.logging import REDACTED, JsonFormatter


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
