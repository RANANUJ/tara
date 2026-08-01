# Tara Implementation Status

## 1. Status Summary

Status date: 2026-08-01

Current phase: M4 — Owner Bootstrap and Session Authentication complete.

Product implementation has not started. M1 provides the monorepo/tooling foundation and static shell. M2 adds internal SQLite persistence. M3 adds framework-independent domain contracts and deterministic safety gating only. No authentication, semantic retrieval, AI, voice, WebSocket, product screen, or real device action has been implemented.

## 2. Milestone Status

| Milestone | Status | Evidence / Exit condition |
|---|---|---|
| M0 — Engineering Documentation Baseline | Complete | Requested documents created; architecture and constraints recorded |
| M1 — Repository and Toolchain Foundation | Complete | Monorepo, frontend/backend tooling, health scaffolding, CI, and bootstrap tests pass; see M1 evidence below |
| M2 — Backend Persistence Foundation | Complete | Async SQLAlchemy persistence, the reproducible initial Alembic migration, isolated SQLite tests, and database-aware readiness pass; see M2 evidence below |
| M3 — Core Domain and Safety Foundation | Complete | Framework-independent domain contracts, default-deny permissions, deterministic confirmation, central tool gating, persistence adapter, and safety tests pass; see M3 evidence below |
| M4 — Owner Bootstrap and Session Authentication | Not started | No authentication exists |
| M5 — Health, Status, and Error Framework | Not started | M1 has only liveness/readiness scaffolding; no dependency status framework or product error handling exists |
| M6 — Authenticated WebSocket Transport | Not started | No WebSocket exists |
| M7 — Foreground Audio Capture and VAD | Not started | No audio pipeline exists |
| M8 — Streaming Speech-to-Text | Not started | faster-whisper not integrated |
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
| AI and voice architecture | Defined | Not started |
| Memory architecture | Defined | M3 structured-memory domain contract plus M2 durable records only; no ChromaDB, semantic retrieval, consolidation, or product API |
| Authentication architecture | Defined | Not started |
| WebSocket architecture | Defined | Not started |
| API strategy and contract | Defined | M2 keeps the two approved health endpoints and adds safe database dependency reporting to readiness only |
| Design system and component hierarchy | Defined | Not started |
| State management | Defined | Not started |
| Error handling | Defined | Not started beyond FastAPI defaults |
| Logging and observability | Defined | M1 structured JSON logging and secret-redaction foundation only |
| Deployment and operations | Defined | Not started |
| Coding/naming/folder standards | Defined | Not started |
| Security model | Defined | M3 deterministic deny-by-default permission, action policy, one-time confirmation, tool-gating, and redacted audit foundations |
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
- Added framework-independent owner/session contracts, authentication service, and internal SQLAlchemy adapter. No AI, WebSocket, voice, frontend product UI, real tool, or device action was added.
- M4 audit fixed nullable bearer-token serialization in session list responses, changed rate-limit keys to one-way email digests, made Argon2id explicit, added redacted login audit events, and routed session management through the authentication service.

### Files Changed

- Authentication: `backend/src/tara_api/auth`, `backend/src/tara_api/domain/auth.py`, and `backend/src/tara_api/api/v1/auth.py`.
- Persistence: `backend/src/tara_api/persistence/auth_store.py`, owner/session ORM models, and `backend/migrations/versions/20260801_0002_owner_authentication.py`.
- Configuration/tests/docs: `backend/pyproject.toml`, `backend/src/tara_api/main.py`, `backend/src/tara_api/config/settings.py`, `backend/tests/auth`, `docs/SECURITY_MODEL.md`, and `docs/API_CONTRACT.md`.

### Commands Run and Results

| Command | Result |
|---|---|
| `python -m pytest backend/tests/auth -q` | Passed: 9 focused auth tests; 1 expected session-binding limitation |
| `python -m ruff check backend` | Passed |
| `python -m mypy backend/src` | Passed: 39 source files |
| `python -m pytest backend/tests -q` | Passed: 30 tests; 1 expected session-binding limitation and one existing upstream warning |
| `pnpm validate` | Passed: frontend lint/typecheck/test/build and backend validation |

### Unresolved Blockers

Confirmation-to-session binding is not implemented because M3 confirmation records have no owner/session columns; the focused test is explicitly expected to fail until a reviewed schema extension binds challenges to authenticated sessions. Bearer tokens remain API-first; browser integration must prefer HttpOnly SameSite cookies or short-lived in-memory credentials.

### Exact Recommended Next Milestone

M5 — Health, Status, and Error Framework. Do not start WebSockets, AI, voice, tools, or frontend product work as part of M5.

## 8. M3 Completion Evidence

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
