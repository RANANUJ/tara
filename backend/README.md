# Tara API

This Python 3.12 package provides Tara's authenticated transport, foreground audio boundary, and optional M8 local speech-to-text foundation. It does not implement an agent, tools, TTS, semantic memory, or product UI.

## M8 local STT (optional)

Standard development and CI do not install `faster-whisper`, download models, require a GPU, or access the internet. Install the optional adapter only when manually testing an explicitly provisioned local model:

```powershell
backend/.venv/Scripts/python.exe -m pip install -e "backend[stt]"
```

Set `TARA_STT_PROVIDER=faster_whisper` only after placing the model outside the repository and setting `TARA_STT_LOCAL_MODEL_DIRECTORY` to that directory. M8 never auto-downloads a model. Use CPU-first values `TARA_STT_DEVICE=cpu` and `TARA_STT_COMPUTE_TYPE=int8`; CUDA requires a compatible locally provisioned runtime. Real faster-whisper emits final-turn results only. The deterministic `fake` provider may emit partials for protocol tests and is rejected in production.

`TARA_STT_MAX_QUEUED_JOBS`, `TARA_STT_MAX_CONCURRENT_JOBS`, and `TARA_STT_TIMEOUT_SECONDS` bound the process-local registry. `TARA_STT_REQUIRED=false` lets an unavailable provider degrade status while readiness remains successful; setting it to `true` makes an unavailable provider fail readiness. Authenticated `GET /api/v1/status` exposes safe STT configuration, readiness, queue, and concurrency metadata only.

Real-model tests are opt-in only and use the `stt_integration` pytest marker after local provisioning. Standard tests mock the adapter and must not download a model.

From the repository root after activating `backend/.venv`:

```powershell
python -m uvicorn tara_api.main:app --app-dir backend/src --reload
python -m ruff check backend
python -m mypy backend/src
python -m pytest backend/tests
```
