# Tara API

This Python 3.12 package is the M1 FastAPI bootstrap. It exposes only liveness and readiness endpoints and contains no authentication, persistence, AI, voice, WebSocket, or product services.

## M8 local STT (optional)

Standard development and CI do not install `faster-whisper` or download any model. Install the optional local adapter only when manually testing a provisioned model:

```powershell
backend/.venv/Scripts/python.exe -m pip install -e "backend[stt]"
```

Set `TARA_STT_PROVIDER=faster_whisper` only after explicitly provisioning the model outside the repository. M8 does not auto-download models and real faster-whisper currently performs final-turn transcription only; deterministic partial events exist solely for fake-provider protocol tests. CPU-first settings are `TARA_STT_DEVICE=cpu` and `TARA_STT_COMPUTE_TYPE=int8`.

From the repository root after activating `backend/.venv`:

```powershell
python -m uvicorn tara_api.main:app --app-dir backend/src --reload
python -m ruff check backend
python -m mypy backend/src
python -m pytest backend/tests
```
