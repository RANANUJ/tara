# Tara API

This Python 3.12 package provides Tara's authenticated transport, foreground audio boundary, optional local STT, final-only local text-agent loop, and an internal bounded final-response TTS service. It does not implement tools, confirmations, TTS WebSocket delivery, browser playback, barge-in, semantic memory, or product UI.

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

## M9A local text model (optional)

M9A adds framework-independent language-model contracts plus final-only provider adapters. It does not add an agent loop, conversation persistence, tools, WebSocket agent events, memory retrieval, or TTS.

Ollama is an optional local runtime. Tara never runs `ollama pull`, auto-creates a model, or falls back to a cloud or fake provider. Provision a model yourself, then configure only a credential-free local URL and an existing model identifier:

```powershell
$env:TARA_LLM_PROVIDER = "ollama"
$env:TARA_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:TARA_OLLAMA_MODEL = "your-provisioned-model"
$env:TARA_LLM_CONTEXT_TOKEN_BUDGET = "4096"
$env:TARA_LLM_OUTPUT_TOKEN_BUDGET = "512"
$env:TARA_LLM_TEMPERATURE = "0.2"
```

M9A supports final-only generation. `TARA_LLM_STREAMING` must remain `false`; no agent deltas are exposed. `TARA_LLM_REQUIRED=false` keeps the provider optional for later health integration. The deterministic `fake` provider is for development/test only and production settings reject it. Standard tests use mocked HTTP and do not require Ollama, a model download, network access, or GPU hardware.

## M10A TTS provider foundation

M10A provides framework-independent, final-only PCM synthesis contracts plus deterministic fake, explicit-local Piper, and optional ElevenLabs adapters. It does not add WebSocket TTS events, browser playback, streaming delivery, barge-in, microphone interruption, or UI.

TTS is disabled by default. Piper requires a manually installed executable and explicit local voice model (and optional config) outside this repository. Tara never downloads a voice/model, interpolates a shell command, uses a fake fallback, or sends audio/text to a cloud provider unless the ElevenLabs provider is explicitly configured with a server-only key.

Use the TARA_TTS_PROVIDER, TARA_TTS_VOICE_IDENTIFIER, TARA_TTS_PIPER_EXECUTABLE, and TARA_TTS_PIPER_VOICE_MODEL_PATH settings only after local provisioning. M10A accepts normalized plain text only—no SSML, client paths, provider arguments, or identity fields. The supported output baseline is final-only mono PCM signed 16-bit little-endian at 16 kHz, 22.05 kHz, or 24 kHz.

Piper uses a bounded subprocess with sanitized errors and child reaping on cancellation; standard tests mock that boundary. The tts_integration marker is reserved for manual real-provider checks and is excluded from ordinary validation.

## M10B TTS service queue and retention

M10B accepts only a server-resolved completed final agent response. It binds a synthesis request to its owner, authenticated session, optional connection, conversation, source agent request, optional assistant turn, configured provider, voice, language, format, and a hashed derived idempotency identity. It accepts no caller-supplied synthesis text or identity.

The process-local FIFO registry uses `TARA_TTS_MAX_QUEUED_REQUESTS`, `TARA_TTS_MAX_CONCURRENT_REQUESTS`, and the connection/session/owner pending limits. `TARA_TTS_MAX_CHUNK_BYTES` splits only validated final raw PCM after synthesis; this is post-synthesis transport preparation, not real-time streaming, and it never creates standalone WAV fragments.

Generated audio remains in bounded process memory only, governed by `TARA_TTS_MAX_RETAINED_AUDIO_BYTES`. It is released after consumption, cancellation, timeout, terminal expiry, eviction, or shutdown. No text, audio bytes, temporary audio files, provider stderr, model paths, or credentials are persisted in SQLite or logged. M10B has no WebSocket delivery, playback, barge-in, or UI integration.

## M9D agent transport and readiness

The authenticated v1 WebSocket accepts direct `agent.request` text with an idempotency key and optional conversation UUID, plus owner/session/connection-bound `agent.cancel`. It publishes final-only `agent.started`, `agent.state`, `agent.response`, `agent.canceled`, and sanitized `agent.error` events. There is no REST agent endpoint, token streaming, TTS, tool execution, confirmation, or device action in M9.

Only a successful server-generated `transcript.final` starts an agent request; partial, canceled, timed-out, and failed transcripts never do. `GET /api/v1/health/ready` includes bounded LLM dependency health, while authenticated `GET /api/v1/status` exposes only safe LLM and agent availability/counter fields. Neither endpoint generates text or pulls a model.
