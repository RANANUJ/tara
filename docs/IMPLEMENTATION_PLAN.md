# Tara Implementation Plan

## 1. Planning Rules

- Deliver milestones in order unless a recorded architecture decision changes dependencies.
- Keep every milestone independently demonstrable and testable.
- Do not expose a capability in the UI before its authorization, error, audit, and recovery paths exist.
- No consequential tool ships before deterministic confirmation gating.
- Update `IMPLEMENTATION_STATUS.md`, `TEST_MATRIX.md`, and relevant risks with each milestone.
- Post-v1 vision, speaker identification, and any native bridge require separate approval.

## 2. Milestone Exit Standard

A milestone is complete only when:

1. Its scoped behavior is implemented without pulling later features forward.
2. Defined automated tests pass in a clean environment.
3. Applicable manual tests pass on supported mobile and desktop browsers.
4. Errors, logs, and status surfaces are present for the new behavior.
5. Documentation and status are updated.
6. No critical security or data-integrity defect remains open.

## 3. Milestones

### M0 — Engineering Documentation Baseline

Objective: establish the source-of-truth architecture before implementation.

Deliverables:

- All requested engineering documents.
- Responsive web decision and native capability boundary.
- API/WebSocket contract, security invariants, risk register, and test strategy.

Independent acceptance:

- Repository contains only the PRD and requested documentation artifacts.
- Every requested architecture topic is covered.
- No frontend, backend, API implementation, or UI artifact exists.

### M1 — Repository and Toolchain Foundation

Objective: create a reproducible empty application skeleton with no product feature.

Deliverables:

- `frontend` React 19/Next.js 15 TypeScript workspace.
- `backend` Python 3.12/FastAPI workspace.
- Formatting, linting, type-checking, unit-test runners, environment templates, and ignore rules.
- Shared contract directories and basic CI workflow.

Independent acceptance:

- Fresh checkout installs using documented commands.
- Frontend type-check/lint/test and backend type-check/lint/test commands pass.
- No business endpoint or product screen exists beyond framework health scaffolding.

Primary tests: `FND-001` through `FND-004`.

### M2 — Backend Persistence Foundation

Objective: establish safe local persistence and migration behavior.

Deliverables:

- SQLAlchemy session/unit-of-work setup.
- Initial SQLite schema for owner, sessions, settings, audit events, and migration metadata.
- Alembic baseline and explicit migration command.
- Configuration validation and data-directory permissions checks.

Independent acceptance:

- Empty database migrates to current schema.
- Re-running migrations is safe.
- Transaction rollback leaves no partial records.
- Startup fails clearly when data paths or required secrets are invalid.

Primary tests: `DB-001` through `DB-005`, `SEC-016`.

### M3 — Shared Design Foundation and Responsive Shell

Objective: prove one component system can serve compact and expanded layouts.

Deliverables:

- PRD color/type/motion tokens and shadcn/ui adaptation.
- Responsive shell, compact bottom navigation, expanded sidebar navigation.
- Static route placeholders for Listen, Memory, Actions, and Settings.
- Guide Star component with controlled showcase states and reduced-motion mode.

Independent acceptance:

- All four routes work at compact, medium, and expanded widths.
- Mobile safe areas, keyboard navigation, focus visibility, zoom, and reduced motion pass.
- Visual snapshots cover every Guide Star state in both shells.

Primary tests: `UI-001` through `UI-010`, `A11Y-001` through `A11Y-006`.

### M4 — Owner Bootstrap and Session Authentication

Objective: protect every private route and backend operation.

Deliverables:

- One-time local bootstrap.
- Owner login, refresh rotation, logout, session list, and revocation.
- Secure cookies, CSRF protection, origin validation, and frontend auth boundary.
- Audit events for bootstrap, login failures, refresh, logout, and revocation.

Independent acceptance:

- Unauthenticated users cannot access private routes or APIs.
- Bootstrap closes permanently after owner creation.
- CSRF, stolen/replayed refresh, revoked sessions, and cross-origin requests fail.
- Secrets and credentials are absent from logs.

Primary tests: `AUTH-001` through `AUTH-012`, `SEC-001` through `SEC-004`.

### M5 — Health, Status, and Error Framework

Objective: make service availability and failures explicit before AI features.

Deliverables:

- Liveness, readiness, and authenticated detailed status endpoints.
- Shared problem response and frontend error mapping.
- Correlation IDs and structured JSON logging.
- Settings service-status card and global offline/degraded treatment.

Independent acceptance:

- Individual dependency failures appear as degraded or unavailable without leaking internals.
- Frontend distinguishes backend offline, optional-provider degraded, and validation errors.
- Correlation IDs connect UI-reported errors to safe log events.

Primary tests: `API-001` through `API-005`, `OBS-001` through `OBS-006`.

### M6 — Authenticated WebSocket Transport

Objective: validate the real-time protocol without audio or AI complexity.

Deliverables:

- Single-use ticket issuance and `/ws/v1/assistant` handshake.
- Versioned event envelope, sequence validation, heartbeat, limits, and reconnect handling.
- Zustand runtime store and frontend connection lifecycle.
- Scripted echo/state fixture for deterministic testing only.

Independent acceptance:

- Valid session connects and exchanges ordered events.
- Expired/replayed tickets, wrong origins, oversized frames, and invalid state sequences fail.
- Reconnect returns to Idle and does not replay prior control events.

Primary tests: `WS-001` through `WS-012`, `SEC-005` through `SEC-007`.

### M7 — Foreground Audio Capture and VAD

Objective: create a bounded, observable audio input path for an active web session.

Deliverables:

- Browser microphone permission/device handling and audio format negotiation.
- Binary audio WebSocket flow with backpressure.
- Server-side Silero VAD and configurable end-of-turn silence.
- Listening/Thinking Guide Star transitions driven by authoritative events.

Independent acceptance:

- Approved microphone streams bounded audio and produces deterministic speech start/end events from fixtures.
- Denied permission, device removal, hidden/suspended page, unsupported format, and buffer overflow recover clearly.
- The application states that locked-screen/background listening is unsupported.

Primary tests: `VOICE-001` through `VOICE-009`, `MAN-V01` through `MAN-V05`.

### M8 — Streaming Speech-to-Text

Objective: add local partial and final transcription without an LLM.

Deliverables:

- faster-whisper provider adapter and bounded worker execution.
- Partial/final transcript events and transcript UI.
- Locale/model configuration, cancellation, timeout, and health reporting.

Independent acceptance:

- Approved audio fixtures produce expected final transcripts within tolerance.
- Partial transcript replacement and finalization order are correct.
- Cancellation and provider failure return the session to a recoverable state.

Primary tests: `STT-001` through `STT-008`, `PERF-001`.

### M9 — Local Text Agent Loop

Objective: produce safe, streamed text responses through Ollama with no real tools.

Deliverables:

- Ollama provider interface, fast model configuration, streaming text, and cancellation.
- Conversation/turn persistence and bounded recent context.
- Text-mode endpoint and live WebSocket turn handling.
- Clarification fallback for low confidence and model-unavailable response.

Independent acceptance:

- Text and transcribed turns stream and persist in correct order.
- Ollama timeout/OOM does not hang the WebSocket or event loop.
- A cancelled turn cannot append stale text after cancellation.

Primary tests: `AI-001` through `AI-008`, `CONV-001` through `CONV-005`.

### M10 — Streaming TTS and Barge-In

Objective: complete a natural foreground voice conversation loop.

Deliverables:

- ElevenLabs streaming adapter and server-only secret handling.
- Piper offline fallback.
- Sentence chunking, output audio events, playback, cancellation, and Guide Star speaking state.
- Barge-in that cancels model/TTS/output for the previous turn.

Independent acceptance:

- First stable response sentence begins synthesis before the full response completes.
- Local mode makes no ElevenLabs request and speaks through Piper.
- ElevenLabs pre-stream failure falls back once without duplicate speech.
- Barge-in stops stale playback and starts a new turn.

Primary tests: `TTS-001` through `TTS-009`, `VOICE-010` through `VOICE-014`, `PERF-002`.

### M11 — Structured and Semantic Memory

Objective: implement explainable, user-controlled memory with rebuildable semantic search.

Deliverables:

- SQLite memory entities, provenance, categories, pinning, task status, and expiry.
- ChromaDB index adapter and transactional outbox.
- Memory browse/search/edit screen and context retrieval.
- Index repair/rebuild diagnostics.

Independent acceptance:

- CRUD remains correct when ChromaDB is unavailable.
- Semantic results resolve only to current authorized SQLite rows.
- Rebuild recreates equivalent searchable records from SQLite.
- Conversation context respects configured bounds and pinned priority.

Primary tests: `MEM-001` through `MEM-012`, `DB-006` through `DB-009`.

### M12 — Retention, Consolidation, Export, and Hard Delete

Objective: complete the PRD's memory lifecycle controls.

Deliverables:

- APScheduler retention and consolidation jobs.
- Preference/task/casual/pinned retention rules.
- Full memory export with expiry.
- Confirmed hard deletion across SQLite, ChromaDB, caches, and staging artifacts.

Independent acceptance:

- Time-controlled tests prove 30-day casual expiry and pinned exemptions.
- Consolidation preserves provenance and does not create duplicate durable facts.
- Hard delete leaves no active SQLite or Chroma reference.
- Export contains expected records, no secrets, and disappears on expiry.

Primary tests: `MEM-013` through `MEM-024`, `JOB-001` through `JOB-005`, `SEC-013`.

### M13 — Capability Registry and Read-Only Tools

Objective: establish tool safety before consequential integrations.

Deliverables:

- Typed tool registry, schema validation, scoped capabilities, timeouts, and audit summaries.
- Actions screen with available/degraded/unavailable/native-bridge states.
- At least one constrained read-only local tool for end-to-end proof.
- Filesystem canonicalization and allowlisted-root policy where applicable.

Independent acceptance:

- Disabled or unsupported capabilities cannot execute.
- Invalid arguments, traversal, and out-of-scope targets fail before provider invocation.
- Tool content is treated as untrusted model context.
- The read-only tool can complete without exposing raw sensitive content in logs.

Primary tests: `TOOL-001` through `TOOL-012`, `SEC-008` through `SEC-010`.

### M14 — Confirmation Gate and Consequential Tool Harness

Objective: prove the non-negotiable safety rule before any real outward action.

Deliverables:

- Confirmation state machine, exact action binding, expiry, approval/rejection, and idempotency.
- Confirmation card and voice response handling.
- A non-production fake consequential tool that records execution without external side effects.
- Uncertain-outcome and reconciliation behavior.

Independent acceptance:

- The fake tool cannot run before valid confirmation.
- Generic “yes,” disconnect, replay, expired challenge, changed arguments, changed permission, and duplicate approval cannot execute it.
- Approved action executes exactly once; audit events show proposal, decision, and result.

Primary tests: `CONF-001` through `CONF-015`, `SEC-011` through `SEC-012`.

### M15 — Two-Tier Routing and Multi-Step Agent

Objective: add bounded intelligence after safety controls exist.

Deliverables:

- Fast/large Ollama routing with observable rationale codes.
- Bounded call-tool → observe → decide loop.
- Context budgeting, tool-result isolation, confidence/clarification behavior.
- Cancellation across multi-step turns.

Independent acceptance:

- Simple fixture intents remain on the fast model.
- Reasoning fixtures route to the larger model.
- Multi-step fixtures complete in order within the iteration limit.
- Prompt-injected tool output cannot bypass capability or confirmation policy.

Primary tests: `AI-009` through `AI-018`, `SEC-014` through `SEC-015`.

### M16 — Proactive Reminders and Briefings

Objective: support local scheduled initiation without pre-authorizing side effects.

Deliverables:

- Schedule CRUD, timezone and missed-run policy.
- Reminder and briefing notifications inside the active web application.
- Job status in Settings and structured scheduler logging.
- Consequential follow-up proposals routed through ordinary confirmation.

Independent acceptance:

- Deterministic clock tests cover schedule, timezone, restart, and missed-run behavior.
- One scheduler leader executes each occurrence once.
- A proactive job cannot directly execute a consequential tool.

Primary tests: `JOB-006` through `JOB-014`, `CONF-016`.

### M17 — Production Hardening and Private Deployment

Objective: make the supported web experience safely operable on the owner network.

Deliverables:

- Tailscale same-origin HTTPS routing and production process definitions.
- SQLCipher activation and separate secret management.
- Backup, restore, migration, retention, and redacted diagnostics procedures.
- Performance, browser compatibility, accessibility, security, and recovery release gates.

Independent acceptance:

- A fresh private host installs and passes smoke tests.
- Remote authenticated mobile and desktop browsers work over Tailscale HTTPS.
- Public/LAN unauthenticated access is absent.
- Backup restores SQLite and rebuilds or restores ChromaDB.
- Release test matrix passes with no critical open risk.

Primary tests: `DEP-001` through `DEP-010`, all release-gate suites.

### M18 — Native Capability Decision Gate (Post-v1)

Objective: decide whether the remaining PRD-native capabilities justify a minimal companion.

Scope of decision only:

- Locked-screen/screen-off wake word and background audio.
- Android calls, SMS, notification access, and WhatsApp Accessibility Service automation.
- Desktop system-tray/menu-bar host.
- Speaker verification.

Independent acceptance:

- A written ADR compares feasibility, permissions, security, maintenance, distribution, and test burden.
- The decision either keeps capabilities unsupported or authorizes a narrow bridge contract that reuses Tara authentication, scoped capabilities, and confirmation gating.
- No native implementation starts inside this decision milestone.

## 4. Release Slices

| Slice | Milestones | Demonstrable outcome |
|---|---|---|
| Documentation | M0 | Reviewed implementation blueprint |
| Foundation | M1–M6 | Authenticated responsive shell with observable real-time connection |
| Voice Assistant | M7–M10 | Foreground browser voice conversation with offline speech fallback |
| Memory and Safety | M11–M14 | User-controlled memory and structurally safe tool execution |
| Intelligence and Proactivity | M15–M16 | Bounded multi-step reasoning and local proactive reminders |
| Private v1 | M17 | Hardened single-user deployment over Tailscale |
| Post-v1 decision | M18 | Explicit disposition of native-only PRD capabilities |

## 5. Dependency Gates

- No microphone milestone starts before secure-context deployment assumptions and auth transport are proven.
- No external or destructive tool implementation starts before M14 passes.
- No sensitive production memory starts before SQLCipher and backup procedures are enabled in M17; development uses non-sensitive fixtures only.
- No cloud TTS is enabled without visible privacy disclosure and server-only secret handling.
- No multi-worker backend deployment occurs while APScheduler and SQLite use a single-leader design.
- No native capability is presented as available before M18 produces an accepted architecture decision and implementation is separately authorized.
