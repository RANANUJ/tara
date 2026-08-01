def test_sessions_support_multiple_login_logout_and_safe_listing(client) -> None:
    first = client.post("/api/v1/auth/bootstrap", json={"email": "owner@example.com", "password": "correct horse battery staple"}).json()
    second = client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "correct horse battery staple"}).json()
    headers = {"Authorization": f"Bearer {first['token']}"}
    listed = client.get("/api/v1/auth/sessions", headers=headers)
    assert listed.status_code == 200 and len(listed.json()) == 2
    assert "token_hash" not in listed.text and "token" not in listed.text
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/session", headers=headers).status_code == 401
    assert client.get("/api/v1/auth/session", headers={"Authorization": f"Bearer {second['token']}"}).status_code == 200
