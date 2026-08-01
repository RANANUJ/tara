"""Tests for the minimal health endpoints."""

from fastapi.testclient import TestClient


def test_liveness_returns_http_200(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_typed_dependency_status(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["ready"] is True
    assert {item["name"] for item in body["dependencies"]} == {"application", "database", "authentication", "schema", "stt"}
    assert all(item["latency_ms"] >= 0 for item in body["dependencies"])
