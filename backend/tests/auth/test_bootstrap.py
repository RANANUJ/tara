import asyncio

from tara_api.auth.security import Argon2idPasswordHasher
from tara_api.persistence.auth_store import SqlAlchemyAuthenticationStore


async def test_bootstrap_normalizes_and_closes(client) -> None:
    assert client.get("/api/v1/auth/bootstrap/status").json() == {"bootstrap_required": True}
    response = client.post("/api/v1/auth/bootstrap", json={"email": " Owner@Example.COM ", "password": "correct horse battery staple"})
    assert response.status_code == 201
    assert response.json()["email"] == "owner@example.com"
    assert "password_hash" not in response.text
    assert client.get("/api/v1/auth/bootstrap/status").json() == {"bootstrap_required": False}
    assert client.post("/api/v1/auth/bootstrap", json={"email": "next@example.com", "password": "correct horse battery staple"}).status_code == 409


async def test_concurrent_bootstrap_creates_one_owner(database) -> None:
    store = SqlAlchemyAuthenticationStore(database)
    password_hash = Argon2idPasswordHasher(time_cost=1, memory_cost=8192).hash("correct horse battery staple")
    created = await asyncio.gather(store.bootstrap("a@example.com", password_hash), store.bootstrap("b@example.com", password_hash))
    assert sum(owner is not None for owner in created) == 1
