# Tara API

This Python 3.12 package is the M1 FastAPI bootstrap. It exposes only liveness and readiness endpoints and contains no authentication, persistence, AI, voice, WebSocket, or product services.

From the repository root after activating `backend/.venv`:

```powershell
python -m uvicorn tara_api.main:app --app-dir backend/src --reload
python -m ruff check backend
python -m mypy backend/src
python -m pytest backend/tests
```
