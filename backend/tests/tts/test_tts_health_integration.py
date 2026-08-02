from fastapi.testclient import TestClient

from tara_api.config.settings import Settings
from tara_api.main import create_app


def test_tts_required_unavailable_affects_readiness(database, database_url: str) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        service_secret="test-secret",
        database_url=database_url,
        tts_provider="piper",
        tts_required=True,
        tts_voice_identifier="local-voice",
        tts_piper_executable="missing-piper",
        tts_piper_voice_model_path="missing-model.onnx",
    )
    with TestClient(create_app(settings, database)) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert next(item for item in response.json()["dependencies"] if item["name"] == "tts")["state"] == "unavailable"


def test_authenticated_status_has_safe_live_tts_fields(client: TestClient) -> None:
    login = client.post("/api/v1/auth/bootstrap", json={"email": "owner@example.test", "password": "correct-horse-battery-staple"}).json()
    response = client.get("/api/v1/status", headers={"Authorization": f"Bearer {login['token']}"})

    assert response.status_code == 200
    tts = response.json()["tts"]
    assert tts["tts_provider"] == "disabled"
    assert tts["tts_retained_audio_bytes"] == 0
    assert "path" not in str(tts).lower()
