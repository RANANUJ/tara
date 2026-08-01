"""Shared test fixtures for the Tara API bootstrap."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tara_api.config.settings import Settings
from tara_api.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Provide deterministic bootstrap settings without reading a local .env file."""
    return Settings(_env_file=None, environment="test", service_secret="test-secret")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """Create an isolated FastAPI application for each test."""
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a synchronous client for health endpoint tests."""
    with TestClient(app) as test_client:
        yield test_client
