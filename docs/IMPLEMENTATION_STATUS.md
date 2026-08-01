# Tara Implementation Status

## M9A Progress - Agent Domain Contracts, Fake LLM, and Ollama Provider Adapter

- Added framework-independent agent/model contracts, bounded request/response validation, typed provider failures, deterministic fake language-model behavior, final-only Ollama HTTP mapping, and a safe internal provider-health snapshot. No agent orchestration, persistence, WebSocket events, tools, semantic memory, TTS, or product UI was added.
- Added safe LLM settings and `.env.example` placeholders: disabled by default; production rejects fake; Ollama requires a credential-free URL and explicit existing model; streaming is rejected for M9A; no auto-pull or fallback exists. `httpx` was promoted from development-only to the minimal runtime dependency required for the async local Ollama HTTP adapter.
- Added 18 focused offline M9A tests covering contracts, validation, fake behavior, mocked Ollama mapping/failures, health snapshots, production fake-health rejection, and settings guards. Standard tests use no Ollama server, model pull, network access, or GPU.
- Validation passed: focused M9A tests (18), targeted M1-M8 regression set (99), full backend suite (117), Ruff, mypy (65 source files), frontend lint/typecheck/tests (8), clean frontend production build, and root `pnpm validate`. The only warning is the existing upstream FastAPI `StarletteDeprecationWarning` from `TestClient`; 0 skipped, 0 xfailed, and 0 failed tests.
- Known limitation: M9A is final-only and its health snapshot is not integrated into global readiness or `/api/v1/status`. The optional Ollama runtime/model must be provisioned explicitly. M9 remains in progress; do not mark M9 complete.
- Exact next sub-milestone: M9B - Intent Router, Prompt Builder, and Structured Context. Do not start M9B or M10.

## M8 Final Acceptance - Complete

M8 is complete. No M9 work was added.

### Blocker Resolution

- Reproduced the three original mypy errors: an untyped FastAPI request continuation, `Any` propagated as a response, and an untyped application-state access. `backend/src/tara_api/api/middleware.py` now uses `RequestResponseEndpoint`; `backend/src/tara_api/api/v1/auth.py` casts the state value at its typed boundary. Runtime behavior is unchanged.
- Bare `pnpm` is absent from this Windows shell, while `corepack pnpm --version` resolves the repository pin as `11.9.0`. `corepack enable` cannot write to the protected Node installation. A temporary local `pnpm.cmd` shim delegating only to `corepack pnpm` enabled the exact root `pnpm validate` command without changing package metadata or lockfiles.
- Exact successful Codex-shell invocation: `$env:PATH = 'C:\Users\anujr\.codex\visualizations\2026\08\01\019fbc6a-dc1c-7b72-819a-f6699384dfff\m8-pnpm-bin;D:\Tara\backend\.venv\Scripts;' + $env:PATH; pnpm validate`.
- The prior hanging build is isolated to `npm.cmd run build`. Two clean direct `corepack pnpm --dir frontend build` runs exited with code 0 after 60.53 seconds and 58.45 seconds. No new persistent Node child process remained.

### Final Evidence

| Command | Result |
|---|---|
| `python -m ruff check backend` | Passed |
| `python -m mypy backend/src` | Passed: 59 source files |
| `python -m pytest backend/tests/stt -q` | Passed: 25 tests; 0 skipped, 0 xfailed, 0 failed |
| `python -m pytest backend/tests/audio -q` | Passed: 29 tests; 0 skipped, 0 xfailed, 0 failed |
| `python -m pytest backend/tests -q` | Passed: 99 tests; 0 skipped, 0 xfailed, 0 failed |
| Frontend lint, typecheck, and tests | Passed; 8 frontend tests |
| Clean direct frontend build | Passed twice; normal exit code 0 |
| Root `pnpm validate` | Passed twice through the Corepack-delegating temporary shim; each run passed lint, typecheck, frontend tests/build, Ruff, mypy, and 99 backend tests |

The only remaining warning is FastAPI's upstream `StarletteDeprecationWarning` for `TestClient`. Standard validation downloaded no model, used no internet access, required no GPU, and contains no required xfail.

### Remaining Operational Notes

- The manual local-model checks in `docs/MANUAL_TESTS.md` remain pending and are not represented as passed.
- The STT registry remains intentionally process-local; multi-process deployment requires a reviewed shared queue.

### Exact Recommended Next Milestone

M9 - Local Text Agent Loop. Do not begin M9 as part of M8 acceptance.

## M8D2 Final-Acceptance Audit — Blocked on Pre-existing Validation Environment Issues

### Completed M8 Scope

- Audited and corrected M8's live-registry lifecycle: the app now owns one bounded STT registry, status reads its real queued/active counts, transcript publication rechecks owner/session/connection identity, and disconnect/session invalidation cancel matching jobs.
- Corrected optional STT readiness to degrade status without failing readiness; required unavailable STT remains unavailable.
- Corrected terminal provider-without-final behavior to emit only a sanitized `provider_failure` event, and prune terminal records on later submission to preserve bounded in-memory state.
- Added M8 contract, security, offline-test policy, local setup, configuration, and pending manual-test documentation. Faster-whisper remains optional, explicit-local-model-only, no-auto-download, and final-only; the deterministic fake provider remains development/test-only.

### Files Changed

- Runtime and safety: `backend/src/tara_api/main.py`, `backend/src/tara_api/api/v1/websocket.py`, `backend/src/tara_api/stt/health.py`, and `backend/src/tara_api/stt/service.py`.
- M8 evidence: `backend/tests/stt/test_stt_health.py`, `backend/tests/stt/test_transcription_cleanup.py`, `backend/tests/stt/test_transcription_queue.py`, `backend/tests/stt/test_transcription_websocket.py`, and `backend/tests/test_m5_framework.py`.
- Documentation and setup: `backend/.env.example`, `backend/README.md`, `docs/API_CONTRACT.md`, `docs/SECURITY_MODEL.md`, `docs/TEST_MATRIX.md`, `docs/MANUAL_TESTS.md`, and this status document.

### Commands and Results

| Command | Result |
|---|---|
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/stt -q` | Passed: 25 tests; one existing FastAPI/Starlette warning |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/audio -q` | Passed: 29 tests; one existing FastAPI/Starlette warning |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_websocket_transport.py backend/tests/test_m5_framework.py backend/tests/test_health.py backend/tests/test_readiness.py backend/tests/auth backend/tests/test_migrations.py -q` | Passed: 27 tests; one existing FastAPI/Starlette warning |
| `backend/.venv/Scripts/python.exe -m ruff check backend` | Passed |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests -q --basetemp <writable Codex temp> -p no:cacheprovider` | Passed: 99 tests; 0 skipped, 0 xfailed, 0 failed; one existing FastAPI/Starlette warning |
| `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run test` in `frontend` | Passed; 8 frontend tests |
| `npm.cmd run build` in `frontend` | Produced `.next` build artifacts but did not exit within 240 seconds; no compiler error emitted |
| `backend/.venv/Scripts/python.exe -m mypy backend/src` | Blocked by 3 pre-existing M5 errors in `backend/src/tara_api/api/middleware.py` and `backend/src/tara_api/api/v1/auth.py`; M8's import error was fixed |
| `pnpm validate` | Not runnable: `pnpm` is not installed in this shell |

No M8 test downloaded a model, accessed the internet, required GPU hardware, or used a real faster-whisper model. No M9 files or behavior were added.

### Remaining Blockers

- M8 cannot honestly be marked Complete until the unrelated M5 mypy baseline errors are resolved or explicitly waived and the frontend production build exits successfully in this environment. The initial elevated full-test run also left the system pytest Temp directory inaccessible; the final 99-test run succeeded with a writable isolated base directory.
- Manual M8 local-model checks in `docs/MANUAL_TESTS.md` remain pending. The registry is intentionally process-local and requires a separately reviewed shared queue for multi-process deployment.

### Exact Recommended Next Milestone

Resolve the recorded validation-environment and baseline typing blockers, rerun M8D2 final acceptance, and only then begin M9 — Local Text Agent Loop. Do not begin M9 now.

## M8D1 Progress — STT Health, Readiness, and Authenticated Status

- Added safe STT health snapshots and registered STT as an M5 dependency with required/optional severity. Readiness performs no model load, inference, download, or network operation.
- Authenticated `/api/v1/status` now returns safe configured/provider/state/readiness/model-loaded/language/partial/queue-limit fields. Disabled STT and unavailable optional STT preserve overall readiness; required unavailable STT fails readiness.
- Validation: M5/STT focused regression set passed (25 tests); Ruff and mypy passed (59 source files); full backend passed (92 tests, one existing upstream warning). No model download or internet access occurred.
- Remaining work: M8D2 — M8 Documentation, Security Audit, and Final Acceptance. Do not begin M8D2 or M9.

## M8C Progress — WebSocket Transcript Events

- Added bounded job-runner publication for `transcript.started`, ordered provider-backed `transcript.partial`, one terminal `transcript.final`, `transcript.canceled`, and safe `transcript.error` codes through the existing authenticated connection publisher seam.
- Fake STT can now emit deterministic partials; faster-whisper remains final-only. Job cancellation suppresses final delivery and event payloads never contain PCM or session credentials.
- Added focused lifecycle and privacy tests. Validation: 18 STT tests, Ruff, mypy (58 source files), and the full backend suite (92 passed, one existing upstream warning) passed. No model download or internet access occurred.
- M8 remains incomplete. Health/status and final M8 acceptance are deferred. Exact next sub-milestone: M8D — STT Health Integration, Documentation, and Final Acceptance. Do not begin it as part of M8C.

## M8B Progress — Transcription Job Queue, Lifecycle, and Cancellation

- Added a bounded, process-local STT registry with immutable request identity, duplicate completed-turn suppression, explicit transitions, global/per-connection/per-session limits, timeout state, cancellation, session/connection invalidation seams, accurate active/queued counters, and terminal cleanup.
- Added focused job, queue, cancellation-isolation, and cleanup tests. No WebSocket transcript delivery, health/status work, or M8C behavior was added.
- Validation: focused M8B coverage passed; STT/audio/auth/health/transport/migration regression set passed (71 tests); full backend passed (89 tests, one existing upstream warning); frontend lint/typecheck/tests/build passed (8 frontend tests). No model download or internet access occurred.
- Known limitation: the registry is intentionally process-local and is not a distributed worker/queue. M8 remains incomplete.
- Exact next sub-milestone: M8C — WebSocket Transcript Events. Do not begin it as part of M8B.

## M8A Progress — Faster-Whisper Provider Adapter

- Added optional lazy faster-whisper loading that requires an explicitly provisioned local directory; automatic download is rejected and imports remain absent from normal startup.
- Model load and final-turn inference use `asyncio.to_thread`; mocked tests cover missing dependency, concurrent single-load behavior, local configuration, result mapping, and safe failures.
- Validation: 5 adapter tests passed, 11 STT tests passed, Ruff and mypy passed, and the full backend suite passed with 85 tests.
- M8 remains in progress. Queue lifecycle, WebSocket transcript coverage, health/status, and M8 documentation completion are deferred. Do not begin M8B or M9.

## 1. Status Summary

Status date: 2026-08-01

Current phase: M6 — Authenticated WebSocket Transport complete.

Product implementation has not started. M1 provides the monorepo/tooling foundation and static shell. M2 adds internal SQLite persistence. M3 adds framework-independent domain contracts and deterministic safety gating. M4 adds single-owner authentication and session-bound internal confirmations. M5 adds safe health/error observability. M6 adds authenticated JSON-only WebSocket transport. No semantic retrieval, AI, voice, product screen, real tool, reminder, or device action has been implemented.

## 2. Milestone Status

| Milestone | Status | Evidence / Exit condition |
|---|---|---|
| M0 — Engineering Documentation Baseline | Complete | Requested documents created; architecture and constraints recorded |
| M1 — Repository and Toolchain Foundation | Complete | Monorepo, frontend/backend tooling, health scaffolding, CI, and bootstrap tests pass; see M1 evidence below |
| M2 — Backend Persistence Foundation | Complete | Async SQLAlchemy persistence, the reproducible initial Alembic migration, isolated SQLite tests, and database-aware readiness pass; see M2 evidence below |
| M3 — Core Domain and Safety Foundation | Complete | Framework-independent domain contracts, default-deny permissions, deterministic confirmation, central tool gating, persistence adapter, and safety tests pass; see M3 evidence below |
| M4 — Owner Bootstrap and Session Authentication | Complete | Single-owner authentication, revocable opaque sessions, and owner/session-bound one-time confirmations pass; see M4 evidence below |
| M5 — Health, Status, and Error Framework | Complete | Bounded dependency registry, authenticated safe status, standardized correlated errors, and structured request logging pass; see M5 evidence below |
| M6 — Authenticated WebSocket Transport | Complete | Hash-only single-use tickets, strict v1 JSON session transport, bounded lifecycle, and regression tests pass; see M6 evidence below |
| M7 — Foreground Audio Capture and VAD | Complete | Foreground-only canonical PCM framing, one audio session per connection, deterministic VAD events, and tests pass |
| M8 — Streaming Speech-to-Text | In final acceptance | Implementation and focused/full tests pass; final completion is blocked only by recorded baseline/environment validation issues |
| M9 — Local Text Agent Loop | Not started | Ollama not integrated |
| M10 — Streaming TTS and Barge-In | Not started | ElevenLabs/Piper not integrated |
| M11 — Structured and Semantic Memory | Not started | SQLite/ChromaDB memory not implemented |
| M12 — Retention, Consolidation, Export, and Hard Delete | Not started | No lifecycle jobs exist |
| M13 — Capability Registry and Read-Only Tools | Not started | No tools exist |
| M14 — Confirmation Gate and Consequential Tool Harness | Not started | No safety state machine exists |
| M15 — Two-Tier Routing and Multi-Step Agent | Not started | No agent loop exists |
| M16 — Proactive Reminders and Briefings | Not started | APScheduler not integrated |
| M17 — Production Hardening and Private Deployment | Not started | No deployable application exists |
| M18 — Native Capability Decision Gate | Deferred | Post-v1 decision only |

## 3. Architecture Readiness

| Area | Documentation status | Implementation status |
|---|---|---|
| Complete target folder structure | Defined | M1 root, frontend, backend, contracts, scripts, and CI paths created; later domain paths deferred |
| Frontend architecture | Defined | M1 static Next.js App Router shell only |
| Backend architecture | Defined | M3 framework-independent domain/safety services plus M2 persistence adapter; no product API or real tools |
| AI and voice architecture | Defined | M7 foreground-only PCM/VAD transport foundation; no STT, TTS, agent, or background capture |
| Memory architecture | Defined | M3 structured-memory domain contract plus M2 durable records only; no ChromaDB, semantic retrieval, consolidation, or product API |
| Authentication architecture | Defined | M4 single-owner bootstrap, opaque sessions, revocation, and session-bound internal confirmation contracts |
| WebSocket architecture | Defined | M6 authenticated ticket exchange, JSON-only v1 handshake/ping/close/ack, process-local connection registry, and bounded lifecycle |
| API strategy and contract | Defined | M6 adds authenticated ticket creation and versioned JSON WebSocket transport alongside M5 HTTP health/status/error contracts |
| Design system and component hierarchy | Defined | Not started |
| State management | Defined | Not started |
| Error handling | Defined | M5 typed application errors, safe FastAPI/Pydantic mappings, and correlated response envelopes |
| Logging and observability | Defined | M5 structured request completion logging, correlation IDs, health latency, and secret-redaction foundations |
| Deployment and operations | Defined | Not started |
| Coding/naming/folder standards | Defined | Not started |
| Security model | Defined | M6 adds single-use owner/session-bound WebSocket tickets, lifecycle limits, and redacted transport logging |
| Testing strategy and matrices | Defined | M1 frontend render test and backend health/settings/logging tests created and run |

## 4. Product Requirement Disposition

| PRD capability | Planned disposition |
|---|---|
| Natural low-latency voice | Foreground web session using WebSocket, Silero VAD, faster-whisper, Ollama, ElevenLabs/Piper |
| Wake phrase while application is active | Feasibility may be evaluated within foreground browser limits after core voice loop |
| Screen-off/locked-phone continuous listening | Not supportable by standard responsive web app; `requires_native_bridge` |
| Barge-in | Planned in M10 |
| Calls/SMS/notification access | Not supportable directly by standard browser; `requires_native_bridge` |
| WhatsApp Accessibility automation | Not supportable directly by standard browser; `requires_native_bridge` and high maintenance risk |
| PC file/desktop actions | Planned behind scoped server-side tool adapters and confirmation policy |
| Durable structured/semantic memory | Planned in M11–M12 |
| Proactive reminders/briefings | Planned in M16; web delivery depends on active/allowed browser notification behavior |
| Guide Star and four core screens | Planned in M3 and feature milestones |
| Desktop system-tray docking | Not supportable by normal browser; `requires_native_bridge` |
| Vision | Post-v1; architecture-compatible, not planned for v1 implementation |
| Speaker identification | Stretch/post-v1; not planned for v1 implementation |

## 5. Current Decision Gates and Blockers

These items do not block documentation completion. They block claims or implementation of specific capabilities:

1. Web-only mobile boundary: locked-screen continuous audio and Android privileged actions require a native bridge decision.
2. Wake-word provider: the approved stack does not name a wake-word engine, and browser background limits remain. Selection is deferred until capability scope is revisited.
3. SQLCipher integration details: the Python driver and key-storage mechanism must be selected before sensitive production data.
4. Ollama model identifiers and hardware budget: model sizes must be chosen against the deployment host and latency tests.
5. ElevenLabs voice identity, current model, pricing, and data settings: re-verify at milestone kickoff as directed by the PRD.
6. Piper voice model quality and licensing: validate before offline-voice release.
7. Browser support matrix: microphone capture, AudioWorklet, PWA, autoplay, and suspension behavior require device testing.

## 6. Status Update Protocol

When implementation is authorized:

- Change only the active milestone to `In progress`.
- Mark a milestone `Complete` only after its independent acceptance and referenced tests pass.
- Record commands/results or CI evidence in the milestone evidence field.
- Add `Blocked` only with a concrete blocker and owner; do not use it for unstarted work.
- Update requirement disposition when a capability becomes supported, remains unsupported, or is descoped through an accepted ADR.
- Keep this document factual; planned work belongs in `IMPLEMENTATION_PLAN.md`.

## 7. M4 Completion Evidence

### Completed Scope

- Added single-owner bootstrap, normalized email/password validation, Argon2id password hashing, opaque bearer sessions, generic login failures, local rate-limiting seam, and authenticated session/logout/revocation routes.
- Added M4 migration `20260801_0002_owner_authentication.py` with singleton owner constraint, password-hash-only storage, token-hash-only sessions, and lookup/expiry indexes.
- Added M4 migration `20260801_0003_confirmation_session_binding.py` with nullable compatibility columns, foreign keys, and owner/session/status/expiry lookup index for authenticated confirmation binding.
- Added framework-independent owner/session contracts, authentication service, and internal SQLAlchemy adapter. No AI, WebSocket, voice, frontend product UI, real tool, or device action was added.
- M4 audit fixed nullable bearer-token serialization in session list responses, changed rate-limit keys to one-way email digests, made Argon2id explicit, added redacted login audit events, and routed session management through the authentication service.
- Bound authenticated confirmation creation, response, and one-time consumption to the originating owner/session; cross-session, revoked, expired, modified, replayed, and reused requests are denied and safely audited. The M3 unbound path remains an explicitly named internal test seam only.

### Files Changed

- Authentication: `backend/src/tara_api/auth`, `backend/src/tara_api/domain/auth.py`, and `backend/src/tara_api/api/v1/auth.py`.
- Persistence and safety: `backend/src/tara_api/persistence/auth_store.py`, `backend/src/tara_api/persistence/safety_store.py`, confirmation repository contracts/implementation/types, owner/session ORM models, `backend/src/tara_api/safety/confirmations.py`, `backend/src/tara_api/safety/store.py`, and `backend/migrations/versions/20260801_0003_confirmation_session_binding.py`.
- Domain/tests/docs: `backend/src/tara_api/domain/auth.py`, `backend/src/tara_api/domain/models.py`, `backend/tests/auth/test_confirmation_session_binding.py`, `docs/SECURITY_MODEL.md`, and `docs/API_CONTRACT.md`.

### Commands Run and Results

| Command | Result |
|---|---|
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/auth/test_confirmation_session_binding.py backend/tests/test_safety.py -q` | Passed: 13 focused confirmation/safety tests |
| `python -m ruff check backend` | Passed |
| `python -m mypy backend/src` | Passed: 39 source files |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` | Passed: 33 tests; one existing upstream warning |
| `pnpm validate` | Passed: frontend lint/typecheck/test/build and backend validation |

### Unresolved Blockers

None for M4. Bearer tokens remain API-first; a future browser integration must prefer HttpOnly SameSite cookies or a short-lived in-memory credential strategy.

### Exact Recommended Next Milestone

M5 — Health, Status, and Error Framework. Do not start WebSockets, AI, voice, tools, or frontend product work as part of M5.

## 7. M5 Completion Evidence

### Completed Scope

- Added framework-independent health states, dependency results, readiness/status snapshots, and typed application errors.
- Added bounded concurrent checks for only the implemented application, database, authentication persistence, and schema revision dependencies; failures and timeouts return safe typed results without exposing exception text.
- Extended liveness/readiness and added authenticated `GET /api/v1/status` with safe version, environment, uptime, dependency, and implemented-feature data only.
- Added strict `X-Correlation-ID` handling, structured request-completion logging, standardized API/Pydantic/not-found/authentication error envelopes, and generic production internal errors.
- Added a reusable cancellation-safe timeout helper. No WebSocket, AI, voice, ChromaDB, product screen, real tool, scheduler, or device action was added.

### Files Changed

- Domain/observability/API: `backend/src/tara_api/domain/health.py`, `backend/src/tara_api/domain/errors.py`, `backend/src/tara_api/observability`, `backend/src/tara_api/api/errors.py`, `backend/src/tara_api/api/middleware.py`, `backend/src/tara_api/api/v1/health.py`, `backend/src/tara_api/api/v1/status.py`, and `backend/src/tara_api/main.py`.
- Compatibility/tests/docs: `backend/src/tara_api/api/v1/auth.py`, `backend/src/tara_api/config/settings.py`, `backend/tests/test_health.py`, `backend/tests/test_readiness.py`, `backend/tests/test_m5_framework.py`, `backend/tests/auth/test_login.py`, `docs/API_CONTRACT.md`, `docs/SECURITY_MODEL.md`, and this status document.

### Commands Run and Results

| Command | Result |
|---|---|
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_m5_framework.py backend/tests/test_health.py backend/tests/test_readiness.py backend/tests/auth backend/tests/test_safety.py backend/tests/test_migrations.py -q` | Passed: 30 tests |
| `backend/.venv/Scripts/python.exe -m ruff check backend` | Passed |
| `backend/.venv/Scripts/python.exe -m mypy backend/src` | Passed: 46 source files |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` | Passed: 38 tests; one existing upstream warning |
| `pnpm validate` | Passed: frontend lint/typecheck/test/build and backend Ruff/mypy/pytest validation |

### Unresolved Blockers

None. The existing FastAPI/Starlette deprecation warning remains non-blocking.

### Exact Recommended Next Milestone

M6 — Authenticated WebSocket Transport. Do not begin M6 as part of this milestone.

## 8. M6 Completion Evidence

### Completed Scope

- Added `POST /api/v1/ws/tickets`, authenticated with the existing opaque owner session, and `WS /api/v1/ws/session?ticket=...`. Tickets are cryptographically random, short-lived, single-use, SHA-256-hashed, and owner/session-bound in bounded in-memory state; bearer tokens are never accepted in a URL or logged.
- Added framework-independent ticket/connection contracts, concurrency-safe process-local connection registry, strict Pydantic protocol-v1 envelopes, `session.hello`, `session.ping`, `session.close`, `client.ack`, and matching transport-only server events.
- Added bounded hello, idle, session-validity, JSON-size, event-rate, and per-session connection-limit enforcement. Each received event rechecks owner-session validity; close/error reasons are safe and no future product event is emitted.
- No audio, VAD, STT, Ollama, agent, TTS, memory retrieval, tools, reminders, frontend product screen, or device action was added.

### Files Changed

- Transport/API: `backend/src/tara_api/domain/transport.py`, `backend/src/tara_api/transport`, `backend/src/tara_api/api/v1/websocket.py`, `backend/src/tara_api/main.py`, and `backend/src/tara_api/config/settings.py`.
- Authentication/status/tests/docs: `backend/src/tara_api/auth/service.py`, `backend/src/tara_api/api/middleware.py`, `backend/src/tara_api/observability/application.py`, `backend/tests/test_websocket_transport.py`, `backend/tests/test_m5_framework.py`, `docs/API_CONTRACT.md`, `docs/SECURITY_MODEL.md`, `docs/TEST_MATRIX.md`, and this status document.

### Commands Run and Results

| Command | Result |
|---|---|
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_websocket_transport.py backend/tests/test_m5_framework.py backend/tests/auth backend/tests/test_safety.py backend/tests/test_migrations.py -q` | Passed: 33 tests |
| `backend/.venv/Scripts/python.exe -m ruff check backend` | Passed |
| `backend/.venv/Scripts/python.exe -m mypy backend/src` | Passed: 52 source files |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` | Passed: 44 tests; one existing upstream warning |
| `pnpm validate` | Passed: frontend lint/typecheck/test/build and backend Ruff/mypy/pytest validation |

### Unresolved Blockers

The M6 registry and ticket store are intentionally process-local. Multi-process deployment requires a reviewed shared transport backend in a later deployment-hardening milestone; this does not block the single-process M6 scope.

### Exact Recommended Next Milestone

M7 — Foreground Audio Capture and VAD. Do not begin M7 as part of M6.

## 9. M3 Completion Evidence

### Completed Scope

- Added pure domain models and protocol ports for conversations, turns, assistant state, intents, tools, permissions, risks, confirmations, memories, retention, audits, latency, clocks, and execution.
- Added deterministic default-deny permission checks and central action policy. Messages, calls, destructive actions, financial actions, and all outward-facing writes require explicit confirmation.
- Added canonical request hashing, safe confirmation prompts, affirmative/negative/ambiguous response handling, expiry, argument invalidation, atomic one-time authorization consumption, and replay prevention without any LLM involvement.
- Added central tool execution that rejects unknown tools and invalid arguments, checks permission before every call, requires authorization for consequential tools, and emits content-minimized audit events.
- Added a SQLAlchemy safety-store adapter that persists confirmations, status transitions, one-time consumption, and redacted audit records without exposing ORM entities to the domain.
- No provider, authentication, WebSocket, voice, ChromaDB, frontend product screen, or real side-effecting device action was added.

### Files Changed

- Domain and safety: `backend/src/tara_api/domain`, `backend/src/tara_api/safety`, and `backend/src/tara_api/persistence/safety_store.py`.
- Persistence integration: `backend/src/tara_api/persistence/repositories/interfaces.py` and `backend/src/tara_api/persistence/repositories/sqlalchemy.py`.
- Tests: `backend/tests/test_safety.py`.
- Documentation: `docs/SECURITY_MODEL.md`, `docs/API_CONTRACT.md`, and `docs/IMPLEMENTATION_STATUS.md`.

### Commands Run and Results

| Command | Result |
|---|---|
| `python -m pytest backend/tests/test_safety.py -q` | Passed: 10 M3 safety tests |
| `python -m ruff check backend` | Passed |
| `python -m mypy backend/src` | Passed: 32 source files, no issues |
| `python -m pytest backend/tests -q` | Passed: 21 tests; one upstream FastAPI/Starlette deprecation warning only |
| `pnpm validate` | Passed: frontend lint/typecheck/test/build and backend Ruff/mypy/pytest all passed |

### Unresolved Blockers

None. The existing upstream `StarletteDeprecationWarning` from FastAPI's current `TestClient` remains non-blocking.

### Exact Recommended Next Milestone

M4 — Owner Bootstrap and Session Authentication. Implement authentication only after M3 acceptance, then bind future confirmation challenges to the authenticated owner session. Do not add real tools, AI, voice, WebSockets, or device actions as part of M4.

## 8. M2 Completion Evidence

### Completed Scope

- Added SQLAlchemy 2 async engine/session lifecycle, SQLite foreign-key enforcement, UTC timestamp normalization, and explicit unit-of-work commit/rollback boundaries.
- Added internal ORM models and record-returning repository interfaces for conversations, turns, structured memories, permission settings, pending confirmations and consumption records, audit events, scheduler job metadata, and non-secret service configuration metadata.
- Added `20260801_0001` as the reproducible initial Alembic migration. It upgrades empty SQLite databases only; the FastAPI application never creates schema automatically.
- Extended readiness to report database availability safely and honestly. No product API, authentication, ChromaDB, AI, voice, WebSocket, raw audio, SQLCipher, or scheduler execution was added.
- Added isolated temporary SQLite tests for migration, foreign keys, CRUD, rollback, one-time confirmation consumption, expiry, hard delete, retention/export records, and unavailable database readiness.

### Files Changed

- Backend dependencies/configuration: `backend/pyproject.toml`, `backend/.env.example`, `backend/alembic.ini`, and `backend/migrations`.
- Persistence implementation: `backend/src/tara_api/persistence`, `backend/src/tara_api/main.py`, and `backend/src/tara_api/api/v1/health.py`.
- Tests: `backend/tests/conftest.py`, `backend/tests/test_health.py`, `backend/tests/test_settings.py`, `backend/tests/test_migrations.py`, `backend/tests/test_persistence.py`, and `backend/tests/test_readiness.py`.
- Documentation: `README.md`, `docs/API_CONTRACT.md`, and `docs/IMPLEMENTATION_STATUS.md`.

### Migration Created

- `backend/migrations/versions/20260801_0001_persistence_foundation.py` creates the M2 persistence foundation from an empty SQLite database.

### Commands Run and Results

| Command | Result |
|---|---|
| `python -m pytest backend/tests/test_migrations.py backend/tests/test_persistence.py backend/tests/test_readiness.py -q` | Passed: 6 tests |
| `python -m ruff check backend` | Passed |
| `python -m mypy backend/src` | Passed: 19 source files, no issues |
| `python -m pytest backend/tests -q` | Passed: 11 tests; one upstream FastAPI/Starlette deprecation warning only |
| `pnpm validate` | Passed: frontend lint/typecheck/test/build and backend Ruff/mypy/pytest all passed |

### Unresolved Blockers

None. The upstream `StarletteDeprecationWarning` emitted by FastAPI's current `TestClient` remains non-blocking and does not require an M2 code change.

### Exact Recommended Next Milestone

M3 — Shared Design Foundation and Responsive Shell. Begin shared tokens, accessible responsive layout primitives, desktop/mobile navigation shells, and the Guide Star visual foundation only after accepting M2. Do not begin authentication, AI, voice, WebSocket, or product workflows as part of M3 bootstrap work.

## 9. M1 Completion Evidence

### Completed Scope

- Created the initial pnpm monorepo root, secure ignore rules, root setup/run/validation guide, development launchers, and GitHub Actions validation workflow.
- Created `frontend` as a strict TypeScript Next.js 15 App Router project using React 19, Tailwind CSS v4, ESLint, Vitest, React Testing Library, and user-event.
- Added only a static development shell, a frontend health placeholder, and one frontend render test. No Guide Star or product routes/screens were added.
- Created `backend` as a Python 3.12 `pyproject.toml` project with a `src/tara_api` layout, FastAPI application factory, Pydantic environment settings, Ruff, mypy, pytest, pytest-asyncio, structured JSON logging, and secret-redaction foundations.
- Implemented only `GET /api/v1/health/live` and `GET /api/v1/health/ready`, with typed readiness dependency status.

### Files Changed

- Root: `.gitignore`, `README.md`, `package.json`, `pnpm-workspace.yaml`, and `pnpm-lock.yaml`.
- Status: `docs/IMPLEMENTATION_STATUS.md`.
- Automation and scripts: `.github/workflows/validate.yml`, `scripts/development/start-frontend.ps1`, and `scripts/development/start-backend.ps1`.
- Shared structure: `contracts/.gitkeep`.
- Frontend: `frontend/package.json`, configuration files, App Router bootstrap files, and `frontend/tests`.
- Backend: `backend/pyproject.toml`, `backend/.env.example`, `backend/src/tara_api`, and `backend/tests`.

### Commands Run and Results

| Command | Result |
|---|---|
| `pnpm install` | Passed; generated `pnpm-lock.yaml` and executed only approved tooling build scripts |
| `pnpm install --frozen-lockfile` | Passed; lockfile is reproducible for CI |
| `python -m venv backend/.venv` | Passed using Python 3.12.13 |
| `python -m pip install -e "backend[dev]"` | Passed in the local backend virtual environment |
| `pnpm lint:frontend` | Passed with no warnings after configuration fix |
| `pnpm typecheck:frontend` | Passed |
| `pnpm test:frontend` | Passed: 1 test |
| `pnpm build:frontend` | Passed: Next.js 15.5.22 production build |
| `python -m ruff check backend` | Passed |
| `python -m mypy backend/src` | Passed: 9 source files, no issues |
| `python -m pytest backend/tests` | Passed: 4 tests; one upstream FastAPI/Starlette deprecation warning only |
| `pnpm validate` | Passed with the backend virtual environment and pnpm available on `PATH` |

### Unresolved Blockers

None. The upstream `StarletteDeprecationWarning` emitted by FastAPI's current `TestClient` is non-blocking and does not require an M1 code change.

### Exact Recommended Next Milestone

M2 — Backend Persistence Foundation. Start with SQLAlchemy session/unit-of-work setup, the initial Alembic baseline, temporary SQLite migration tests, and configuration/data-directory validation. Do not begin M3 or any product feature before M2 exits successfully.

## M7 Completion Evidence

### Completed Scope

- Added canonical transient PCM framing, one negotiated audio session per authenticated WebSocket connection, deterministic VAD transitions, end-of-turn silence handling, duration limits, strict sequence/session binding, and smoothed/throttled audio-level events.
- Audited and hardened M7 lifecycle handling: frames require an active owner session and negotiated stream; stop, cancel, flush, disconnect, timeout, invalidation, and failures clear the transient session; no raw audio buffering, files, database records, logs, or error payloads are introduced.
- Added typed frontend PCM conversion, downmixing, explicit 16 kHz resampling, little-endian framing, and user-invoked foreground microphone permission/cleanup helpers. No microphone UI, browser AudioWorklet pipeline, background capture, STT, TTS, model, memory, tools, or persistence was added.

### Files Changed

- `backend/src/tara_api/domain/audio.py`, `backend/src/tara_api/transport/audio.py`, `backend/src/tara_api/api/v1/websocket.py`, and `backend/tests/test_websocket_transport.py`.
- `backend/tests/audio/test_audio_format.py`, `test_audio_framing.py`, `test_audio_session_state.py`, `test_audio_buffering.py`, `test_vad.py`, `test_audio_levels.py`, `test_audio_websocket.py`, `test_audio_security.py`, and `test_audio_cleanup.py`.
- `frontend/lib/audio.ts`, `frontend/lib/microphone.ts`, and `frontend/tests/unit/audio-format.test.ts`, `audio-resampler.test.ts`, `audio-framing.test.ts`, `microphone-lifecycle.test.ts`, and `microphone-permissions.test.ts`.
- `docs/API_CONTRACT.md`, `docs/SECURITY_MODEL.md`, `docs/TEST_MATRIX.md`, `docs/MANUAL_TESTS.md`, and `docs/IMPLEMENTATION_STATUS.md`.

### Commands Run and Results

| Command | Result |
|---|---|
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/audio backend/tests/test_websocket_transport.py -q` | Passed: 35 focused audio/transport tests |
| `corepack pnpm --dir frontend test -- tests/unit/audio-format.test.ts tests/unit/audio-resampler.test.ts tests/unit/audio-framing.test.ts tests/unit/microphone-lifecycle.test.ts tests/unit/microphone-permissions.test.ts` | Passed: 8 frontend tests total |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_websocket_transport.py backend/tests/auth backend/tests/test_health.py backend/tests/test_readiness.py backend/tests/test_m5_framework.py -q` | Passed: 26 M4/M5/M6 regression tests |
| `backend/.venv/Scripts/python.exe -m ruff check backend` | Passed |
| `backend/.venv/Scripts/python.exe -m mypy backend/src` | Passed: 54 source files |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` | Passed: 74 tests; one existing upstream warning |
| `corepack pnpm --dir frontend lint && corepack pnpm --dir frontend typecheck && corepack pnpm --dir frontend test && corepack pnpm --dir frontend build` | Passed: lint, typecheck, 8 tests, and production build |
| `pnpm validate` | Passed: root validation completed through a temporary Corepack shim removed after execution |

### Unresolved Blockers

Silero remains an optional future adapter; M7 uses deterministic VAD only and does not download models. Browser AudioWorklet streaming, device-change integration, and final Listen UI are not implemented; foreground capture starts only from an explicit public method and stops on the helper's page-hide lifecycle signal.

### Exact Recommended Next Milestone

M8 — Streaming Speech-to-Text. Do not begin M8 as part of M7.
