"""Focused M5 health, error-envelope, correlation, and status tests."""

import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from tara_api.domain.health import DependencyName, HealthSeverity, HealthState
from tara_api.observability.health import CallableHealthCheck, DependencyHealthRegistry


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 1, tzinfo=UTC)


async def test_registry_contains_failures_and_optional_degradation() -> None:
    async def healthy() -> tuple[HealthState, str | None]:
        return HealthState.HEALTHY, None

    async def optional() -> tuple[HealthState, str | None]:
        return HealthState.DEGRADED, "Optional service is degraded."

    async def broken() -> tuple[HealthState, str | None]:
        raise RuntimeError("database URL secret should not escape")

    registry = DependencyHealthRegistry(
        (
            CallableHealthCheck(DependencyName.APPLICATION, HealthSeverity.REQUIRED, healthy),
            CallableHealthCheck(DependencyName.SCHEMA, HealthSeverity.OPTIONAL, optional),
            CallableHealthCheck(DependencyName.DATABASE, HealthSeverity.OPTIONAL, broken),
        ),
        FixedClock(),
        0.1,
    )
    readiness = await registry.readiness()

    assert readiness.ready is True
    assert readiness.state == HealthState.DEGRADED
    assert all(item.latency_ms >= 0 for item in readiness.dependencies)
    assert "secret" not in next(item for item in readiness.dependencies if item.name == DependencyName.DATABASE).diagnostic.lower()


async def test_registry_timeout_returns_safe_unavailable_result() -> None:
    async def slow() -> tuple[HealthState, str | None]:
        await asyncio.sleep(0.1)
        return HealthState.HEALTHY, None

    registry = DependencyHealthRegistry((CallableHealthCheck(DependencyName.DATABASE, HealthSeverity.REQUIRED, slow),), FixedClock(), 0.001)
    readiness = await registry.readiness()

    assert readiness.ready is False
    assert readiness.dependencies[0].state == HealthState.UNAVAILABLE
    assert readiness.dependencies[0].diagnostic == "Health check timed out."


def test_error_envelopes_and_correlation_ids_are_safe(client: TestClient) -> None:
    supplied = "client-request_123"
    response = client.get("/api/v1/auth/session", headers={"X-Correlation-ID": supplied})

    assert response.status_code == 401
    assert response.headers["X-Correlation-ID"] == supplied
    assert response.json()["error"] == {
        "code": "authentication_required",
        "message": "Authentication is required.",
        "correlation_id": supplied,
        "retryable": False,
    }

    invalid = client.get("/api/v1/does-not-exist", headers={"X-Correlation-ID": "x" * 65})
    assert invalid.status_code == 404
    assert invalid.json()["error"]["code"] == "resource_not_found"
    assert invalid.headers["X-Correlation-ID"] != "x" * 65


def test_validation_and_status_are_safe_and_authenticated(client: TestClient) -> None:
    validation = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert validation.status_code == 422
    assert validation.json()["error"]["code"] == "validation_failed"
    assert "details" in validation.json()["error"]
    assert client.get("/api/v1/status").status_code == 401

    login = client.post("/api/v1/auth/bootstrap", json={"email": "owner@example.test", "password": "correct-horse-battery-staple"})
    token = login.json()["token"]
    status = client.get("/api/v1/status", headers={"Authorization": f"Bearer {token}"})

    assert status.status_code == 200
    body = status.json()
    assert body["uptime_ms"] >= 0
    assert body["features"] == {
        "database_persistence": True,
        "owner_authentication": True,
        "session_management": True,
        "websocket_transport": True,
        "local_text_agent": True,
        "llm_final_response": True,
    }
    assert body["stt"]["stt_provider"] == "fake-development"
    assert body["stt"]["stt_queue_depth"] == 0
    assert body["stt"]["stt_active_jobs"] == 0
    assert body["llm"]["llm_configured"] is False
    assert body["agent"]["agent_available"] is False
    rendered = str(body).lower()
    assert "sqlite" not in rendered
    assert "token" not in rendered
