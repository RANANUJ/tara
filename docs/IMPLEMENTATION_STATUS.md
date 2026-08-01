# Tara Implementation Status

## 1. Status Summary

Status date: 2026-08-01

Current phase: M1 — Repository and Toolchain Foundation complete.

Product implementation has not started. M1 provides only the monorepo/tooling foundation, a static Next.js shell, a FastAPI application factory, and the two explicitly approved health endpoints. No authentication, memory, AI, voice, WebSocket, database schema, product screen, or automation capability has been implemented.

## 2. Milestone Status

| Milestone | Status | Evidence / Exit condition |
|---|---|---|
| M0 — Engineering Documentation Baseline | Complete | Requested documents created; architecture and constraints recorded |
| M1 — Repository and Toolchain Foundation | Complete | Monorepo, frontend/backend tooling, health scaffolding, CI, and bootstrap tests pass; see M1 evidence below |
| M2 — Backend Persistence Foundation | Not started | No schema or migration exists |
| M3 — Shared Design Foundation and Responsive Shell | Not started | Static M1 shell exists; no responsive shell, product route, token, or Guide Star work exists |
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
| Backend architecture | Defined | M1 FastAPI factory and health router only |
| AI and voice architecture | Defined | Not started |
| Memory architecture | Defined | Not started |
| Authentication architecture | Defined | Not started |
| WebSocket architecture | Defined | Not started |
| API strategy and contract | Defined | M1 implements only approved `/api/v1/health/live` and `/api/v1/health/ready` scaffolding |
| Design system and component hierarchy | Defined | Not started |
| State management | Defined | Not started |
| Error handling | Defined | Not started beyond FastAPI defaults |
| Logging and observability | Defined | M1 structured JSON logging and secret-redaction foundation only |
| Deployment and operations | Defined | Not started |
| Coding/naming/folder standards | Defined | Not started |
| Security model | Defined | Not started |
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

## 7. M1 Completion Evidence

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
