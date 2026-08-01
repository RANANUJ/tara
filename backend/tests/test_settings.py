"""Tests for environment-backed bootstrap settings."""

import pytest

from tara_api.config.settings import Settings


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARA_ENVIRONMENT", "test")
    monkeypatch.setenv("TARA_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("TARA_PORT", "8123")
    monkeypatch.setenv("TARA_SERVICE_SECRET", "configured-secret")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.port == 8123
    assert settings.service_secret.get_secret_value() == "configured-secret"
