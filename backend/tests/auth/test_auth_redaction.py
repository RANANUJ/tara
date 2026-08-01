import json


async def test_login_audits_exclude_credentials_and_tokens(client, database) -> None:
    password = "correct horse battery staple"
    response = client.post("/api/v1/auth/bootstrap", json={"email": "owner@example.com", "password": password})
    token = response.json()["token"]
    client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "wrong password here"})
    async with database.unit_of_work() as unit_of_work:
        events = await unit_of_work.audit_events.list()
    rendered = json.dumps([event.safe_metadata for event in events])
    assert password not in rendered and token not in rendered and "owner@example.com" not in rendered
