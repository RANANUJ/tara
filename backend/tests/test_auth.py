"""M4 owner bootstrap and opaque bearer-session tests."""

from fastapi.testclient import TestClient


def test_bootstrap_login_and_session_lifecycle(client: TestClient) -> None:
    assert client.get("/api/v1/auth/bootstrap/status").json() == {"bootstrap_required": True}
    bootstrap = client.post("/api/v1/auth/bootstrap", json={"email": " Owner@Example.COM ", "password": "correct horse battery staple"})
    assert bootstrap.status_code == 201
    body = bootstrap.json()
    assert body["email"] == "owner@example.com"
    assert body["token"]
    assert "password_hash" not in body
    assert client.get("/api/v1/auth/bootstrap/status").json() == {"bootstrap_required": False}
    assert client.post("/api/v1/auth/bootstrap", json={"email": "new@example.com", "password": "correct horse battery staple"}).status_code == 409
    missing = client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong password here"})
    wrong_password = client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "wrong password here"})
    assert missing.json() == wrong_password.json()
    headers = {"Authorization": f"Bearer {body['token']}"}
    assert client.get("/api/v1/auth/session", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/session", headers=headers).status_code == 401
