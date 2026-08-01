def test_login_failures_are_generic_and_success_returns_token(client) -> None:
    client.post("/api/v1/auth/bootstrap", json={"email": "owner@example.com", "password": "correct horse battery staple"})
    unknown = client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong password here"})
    wrong = client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "wrong password here"})
    assert unknown.status_code == wrong.status_code == 401
    assert {key: value for key, value in unknown.json()["error"].items() if key != "correlation_id"} == {
        key: value for key, value in wrong.json()["error"].items() if key != "correlation_id"
    }
    success = client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "correct horse battery staple"})
    assert success.status_code == 200 and success.json()["token"]
