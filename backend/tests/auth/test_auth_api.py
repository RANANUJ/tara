def test_session_routes_default_deny_and_bearer_parsing_is_strict(client) -> None:
    for path in ("/api/v1/auth/session", "/api/v1/auth/sessions", "/api/v1/auth/logout", "/api/v1/auth/logout-all"):
        assert client.request("POST" if "logout" in path else "GET", path).status_code == 401
    assert client.get("/api/v1/auth/session", headers={"Authorization": "Basic value"}).status_code == 401
    assert client.get("/api/v1/auth/session", headers={"Authorization": "Bearer malformed token"}).status_code == 401
