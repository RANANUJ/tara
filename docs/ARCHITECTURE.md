# Tara Architecture

## 1. Purpose

This document defines the target engineering architecture for Tara based on `Tara-PRD-v1.docx` and the approved stack override. It is an implementation blueprint, not application code.

Tara is a local-first, single-user, responsive web application backed by a Python AI service. The mobile layout should feel like a native assistant while active in a browser or installed PWA. The desktop layout should provide the PRD's persistent navigation and denser operational views. Both layouts use one Next.js application, one component system, and one set of Guide Star tokens.

## 2. Architectural Drivers

1. Voice latency is the primary UX constraint: target under 1.5 seconds from end of user speech to first local-response audio.
2. Consequential actions are safe by construction: the LLM cannot execute them without a deterministic confirmation gate.
3. Local-first operation minimizes recurring cost and limits exposure of personal data.
4. Speech, model, TTS, and automation providers remain swappable.
5. Memory must be durable, explainable, editable, exportable, and genuinely deletable.
6. The application is single-user in v1 and privately reachable through Tailscale; it is not a public SaaS.
7. The responsive web decision replaces the PRD's Flutter shells without changing the Guide Star product identity.

## 3. Capability Boundary

The responsive web application can provide microphone capture while active, streaming conversation, memory management, permissions, settings, PC-side tools, and installable PWA behavior where supported.

Standard browsers do not reliably provide continuous microphone access after the screen locks, Android foreground services, direct calls/SMS, notification listener access, Accessibility Service automation, or desktop system-tray integration. These PRD capabilities are not part of the web-only executable scope unless a later decision authorizes a minimal native device bridge. The architecture keeps device actions behind adapters so such a bridge can be added without changing the agent core, but no bridge is assumed here.

## 4. System Context

```text
User
  -> Next.js responsive web application
      -> HTTPS REST: resources, settings, history, mutations
      -> Authenticated WebSocket: voice, transcript, state, tool progress
          -> FastAPI modular monolith
              -> Agent and safety orchestration
              -> faster-whisper + Silero VAD
              -> Ollama local models
              -> ElevenLabs primary TTS / Piper fallback
              -> Tool adapters and APScheduler
              -> SQLAlchemy -> SQLite authoritative data
              -> ChromaDB rebuildable semantic index

Private ingress: Tailscale HTTPS only
External egress: ElevenLabs only when online voice is enabled
```

## 5. Deployment Topology

The recommended v1 deployment is a single trusted PC or home server:

- One Next.js 15 production process serves the responsive application.
- One FastAPI process serves `/api/v1` and `/ws/v1`. A single process avoids SQLite writer contention and duplicate scheduler execution.
- One Ollama runtime hosts the fast router model and the larger local reasoning model.
- One Piper runtime supplies offline speech.
- SQLite, ChromaDB, exports, and rotating logs live in separate least-privilege data directories.
- Tailscale provides private device reachability and HTTPS. No application port is exposed directly to the LAN or public internet.
- ElevenLabs is an optional outbound-only dependency. Local mode disables that egress and uses Piper.

Next.js and FastAPI should appear under one HTTPS origin. Same-origin routing reduces CORS complexity, allows secure cookie authentication, and keeps browser microphone access in a secure context.

## 6. Complete Target Folder Structure

The following is the planned structure; these paths should be created only in their implementation milestones.

```text
tara/
|-- AGENTS.md
|-- README.md
|-- docs/
|   |-- Tara-PRD-v1.docx
|   |-- ARCHITECTURE.md
|   |-- API_CONTRACT.md
|   |-- DESIGN_SYSTEM.md
|   |-- SECURITY_MODEL.md
|   |-- DECISIONS.md
|   |-- IMPLEMENTATION_PLAN.md
|   |-- IMPLEMENTATION_STATUS.md
|   |-- TEST_MATRIX.md
|   |-- MANUAL_TESTS.md
|   `-- RISKS.md
|-- frontend/
|   |-- app/
|   |   |-- (public)/
|   |   |   |-- page.tsx
|   |   |   `-- login/page.tsx
|   |   |-- (assistant)/
|   |   |   |-- layout.tsx
|   |   |   |-- listen/page.tsx
|   |   |   |-- memory/page.tsx
|   |   |   |-- actions/page.tsx
|   |   |   `-- settings/page.tsx
|   |   |-- api/health/route.ts
|   |   |-- error.tsx
|   |   |-- global-error.tsx
|   |   |-- layout.tsx
|   |   `-- not-found.tsx
|   |-- components/
|   |   |-- assistant/
|   |   |   |-- GuideStar.tsx
|   |   |   |-- LiveTranscript.tsx
|   |   |   |-- ConfirmationCard.tsx
|   |   |   `-- ServiceStatusChip.tsx
|   |   |-- layout/
|   |   |   |-- ResponsiveShell.tsx
|   |   |   |-- MobileShell.tsx
|   |   |   |-- DesktopShell.tsx
|   |   |   |-- BottomNavigation.tsx
|   |   |   `-- SidebarNavigation.tsx
|   |   |-- memory/
|   |   |-- actions/
|   |   |-- settings/
|   |   `-- ui/
|   |-- features/
|   |   |-- assistant/
|   |   |-- auth/
|   |   |-- memory/
|   |   |-- capabilities/
|   |   `-- settings/
|   |-- hooks/
|   |-- lib/
|   |   |-- api/
|   |   |-- audio/
|   |   |-- auth/
|   |   |-- validation/
|   |   `-- websocket/
|   |-- providers/
|   |-- stores/
|   |-- styles/
|   |   |-- globals.css
|   |   `-- tokens.css
|   |-- types/
|   |-- public/
|   |-- tests/
|   |   |-- unit/
|   |   |-- integration/
|   |   `-- e2e/
|   |-- next.config.ts
|   |-- package.json
|   `-- tsconfig.json
|-- backend/
|   |-- app/
|   |   |-- main.py
|   |   |-- api/
|   |   |   |-- dependencies.py
|   |   |   |-- errors.py
|   |   |   `-- v1/
|   |   |       |-- auth.py
|   |   |       |-- health.py
|   |   |       |-- conversations.py
|   |   |       |-- memories.py
|   |   |       |-- capabilities.py
|   |   |       |-- confirmations.py
|   |   |       |-- schedules.py
|   |   |       `-- settings.py
|   |   |-- websocket/
|   |   |   |-- assistant.py
|   |   |   |-- connection_manager.py
|   |   |   `-- protocol.py
|   |   |-- agent/
|   |   |   |-- orchestrator.py
|   |   |   |-- router.py
|   |   |   |-- context_builder.py
|   |   |   `-- cancellation.py
|   |   |-- safety/
|   |   |   |-- confirmation_service.py
|   |   |   |-- permission_service.py
|   |   |   `-- policy.py
|   |   |-- voice/
|   |   |   |-- pipeline.py
|   |   |   |-- vad.py
|   |   |   |-- stt.py
|   |   |   |-- tts.py
|   |   |   `-- audio_formats.py
|   |   |-- models/
|   |   |   |-- ollama.py
|   |   |   `-- protocols.py
|   |   |-- tools/
|   |   |   |-- registry.py
|   |   |   |-- protocols.py
|   |   |   |-- filesystem/
|   |   |   |-- desktop/
|   |   |   `-- personal_data/
|   |   |-- memory/
|   |   |   |-- service.py
|   |   |   |-- retrieval.py
|   |   |   |-- consolidation.py
|   |   |   |-- retention.py
|   |   |   `-- index_sync.py
|   |   |-- auth/
|   |   |   |-- service.py
|   |   |   |-- sessions.py
|   |   |   `-- websocket_tickets.py
|   |   |-- scheduler/
|   |   |   |-- service.py
|   |   |   `-- jobs.py
|   |   |-- persistence/
|   |   |   |-- database.py
|   |   |   |-- models/
|   |   |   |-- repositories/
|   |   |   `-- unit_of_work.py
|   |   |-- schemas/
|   |   |-- observability/
|   |   |   |-- logging.py
|   |   |   |-- metrics.py
|   |   |   `-- tracing.py
|   |   |-- config/
|   |   `-- common/
|   |-- migrations/
|   |   |-- versions/
|   |   `-- env.py
|   |-- tests/
|   |   |-- unit/
|   |   |-- integration/
|   |   |-- contract/
|   |   |-- performance/
|   |   `-- fixtures/
|   |-- alembic.ini
|   `-- pyproject.toml
|-- contracts/
|   |-- openapi/
|   |-- websocket/
|   `-- fixtures/
|-- scripts/
|   |-- backup/
|   |-- diagnostics/
|   `-- development/
|-- data/
|   |-- sqlite/
|   |-- chroma/
|   |-- exports/
|   `-- logs/
`-- deploy/
    |-- environment/
    |-- services/
    |-- tailscale/
    `-- backup/
```

Generated data under `data/`, secrets, model files, audio captures, logs, exports, build output, and virtual environments must not be committed.

## 7. Frontend Architecture

### 7.1 Rendering and Routing

- Use the Next.js 15 App Router.
- Use Server Components for route shells and initial durable data.
- Use Client Components for microphone capture, WebSocket lifecycle, Framer Motion, confirmation controls, local navigation behavior, and browser-only APIs.
- The four authenticated routes are `/listen`, `/memory`, `/actions`, and `/settings`.
- Public scope is limited to the front door, login/bootstrap, privacy explanation, and availability status. It must not expose private assistant data.
- Route-level `loading`, `error`, and empty states are required for every durable-data screen.

### 7.2 Responsive Shells

`ResponsiveShell` chooses layout presentation from CSS media/container queries while preserving the same route and component tree.

- Mobile: full-height Listen surface, safe-area padding, bottom navigation, transcript bottom sheet, large touch targets, and no hover dependency.
- Desktop: persistent left sidebar, centered content workspace, optional secondary detail panel, keyboard navigation, and denser tables/lists.
- Installed PWA behavior may remove browser chrome, but the application must remain fully usable in a normal browser tab.
- The web application does not claim native locked-screen, foreground-service, or system-tray behavior.

### 7.3 Component Hierarchy

```text
RootLayout
`-- ApplicationProviders
    |-- AuthenticationBoundary
    |-- QueryProvider
    |-- AssistantRuntimeProvider
    `-- ResponsiveShell
        |-- MobileShell
        |   |-- ActiveRoute
        |   `-- BottomNavigation
        `-- DesktopShell
            |-- SidebarNavigation
            |-- ActiveRoute
            `-- OptionalDetailPanel

ListenPage
|-- ServiceStatusChip
|-- GuideStar
|-- VoiceSessionControls
|-- LiveTranscript
`-- ConfirmationCard

MemoryPage
|-- MemorySearch
|-- CategoryFilters
|-- MemoryList
|   `-- MemoryItem
`-- ExportMemoryAction

ActionsPage
|-- CapabilityList
|   `-- CapabilityPermissionRow
`-- ConfirmationPolicySummary

SettingsPage
|-- ServiceStatusCard
|-- VoiceSettings
|-- PrivacySettings
|-- ConnectionSettings
`-- DataManagement
```

### 7.4 State Management

- TanStack Query owns all server state: authentication session, memories, capability grants, settings, schedules, conversation history, and service status.
- Zustand owns only ephemeral runtime state: WebSocket phase, current assistant state, partial transcript, audio level, active playback, selected bottom-sheet snap point, and local reconnect counters.
- URL search parameters own shareable filters and selected durable records.
- Component state owns short-lived form/input behavior.
- Never copy a TanStack Query result into Zustand. WebSocket events update the query cache when they affect durable resources.

### 7.5 Frontend Boundaries

- `components/ui` contains shadcn/ui primitives adapted to Tara tokens.
- `components/<domain>` contains reusable visual compositions with no direct transport calls.
- `features/<domain>` owns use cases, query keys, mutations, and view models.
- `lib/api` and `lib/websocket` are the only network transport layers.
- `lib/audio` owns permission checks, device selection, capture, codec negotiation, playback, and interruption.
- Domain errors are mapped to user-safe messages at feature boundaries.

### 7.6 Design System Architecture

- `styles/tokens.css` is the frontend source for semantic color, typography, spacing, radius, elevation, and motion tokens defined in `DESIGN_SYSTEM.md`.
- Tailwind CSS v4 consumes those semantic roles; feature components do not introduce isolated raw product colors.
- shadcn/ui provides accessible primitives, while Tara-owned domain components provide Guide Star semantics, confirmation behavior, service state, and responsive compositions.
- The Guide Star accepts a closed semantic state and bounded audio-envelope data. It does not infer agent state from local animation or timer state.
- MobileShell and DesktopShell change navigation and information density while reusing the same feature and domain components.
- Visual regression fixtures cover all Guide Star states, async screen states, both shells, and reduced-motion output.

## 8. Backend Architecture

### 8.1 Modular Monolith

FastAPI hosts a modular monolith with explicit domain boundaries. This minimizes local deployment complexity while preserving replaceable modules.

- API layer: authentication, validation, serialization, correlation IDs, and protocol status codes.
- Application services: use-case orchestration and transaction boundaries.
- Domain/policy layer: confirmation, capability permission, retention, and action classification rules.
- Infrastructure: SQLAlchemy, ChromaDB, Ollama, faster-whisper, ElevenLabs, Piper, filesystem, and OS adapters.
- Background layer: APScheduler jobs for reminders, retention, consolidation, index repair, and backup prompts.

Routers must not call SQLAlchemy, ChromaDB, model providers, or tool implementations directly.

### 8.2 Concurrency Model

- FastAPI handles network I/O asynchronously.
- CPU/GPU-heavy STT, VAD, local inference, and synthesis work executes through bounded workers or provider-owned runtimes so it cannot block the event loop.
- Each voice session has a cancellation scope. Barge-in cancels pending LLM generation, TTS generation, and playback events for the superseded turn.
- Per-session turn processing is serialized; unrelated sessions are not expected in v1 but remain isolated.
- Backpressure limits queued audio and outbound events. When exceeded, the server emits an explicit recoverable error instead of growing memory without bound.

### 8.3 Service Boundaries

- `AgentOrchestrator`: owns the turn state machine and tool loop.
- `ModelRouter`: selects fast or reasoning model based on deterministic thresholds and model classification.
- `ContextBuilder`: retrieves bounded memories and recent turns.
- `ConfirmationService`: binds a proposed consequential action to a short-lived, one-time challenge.
- `PermissionService`: checks the user-controlled capability grant before any tool starts.
- `ToolRegistry`: exposes typed tool metadata and dispatches validated calls.
- `VoicePipeline`: joins VAD, STT, response segmentation, and TTS streams.
- `MemoryService`: controls structured writes, semantic indexing, retention, export, and hard delete.
- `SchedulerService`: owns approved proactive jobs and never bypasses confirmation policy.

## 9. AI and Voice Architecture

### 9.1 End-to-End Turn

1. The active web client obtains microphone permission and opens an authenticated WebSocket.
2. Audio chunks are streamed while the page remains active.
3. Silero VAD detects speech boundaries; the client may also send local activity hints, but the server makes the authoritative turn decision.
4. faster-whisper emits partial and final transcripts.
5. The model router sends simple requests to a fast Ollama model and reasoning-heavy requests to a larger Ollama model.
6. The context builder retrieves recent conversation plus a small, relevance-ranked memory set.
7. The agent may propose typed tool calls. Every call is validated, permission-checked, risk-classified, and logged.
8. Consequential calls pause in `awaiting_confirmation`; only the confirmation service can release them.
9. Safe results return to the model for zero or more bounded tool-loop iterations.
10. Sentences are streamed to ElevenLabs or Piper as soon as stable, and audio is streamed to the client.
11. Barge-in cancels the active response and starts a new listening turn.

### 9.2 Provider Interfaces

The core depends on capabilities rather than vendor-specific classes:

- STT: transcribe stream, cancel, health, supported audio formats.
- LLM: stream completion, structured tool proposal, cancel, token/context limits, health.
- TTS: stream synthesis, cancel, voice availability, health.
- VAD: frame classification and turn-boundary events.
- Tool: typed input/output, risk class, required capability, timeout, idempotency policy.

ElevenLabs is primary when explicitly enabled and reachable. Piper is the offline fallback. Ollama is the only configured v1 LLM runtime; a future cloud reasoning adapter may be added only through an architecture decision and privacy review.

### 9.3 Agent Safety Limits

- Maximum tool-loop iterations, model time, output size, and retrieved context are configured bounds.
- The model cannot choose whether confirmation is required; policy derives that from the registered tool and action arguments.
- Tool output is untrusted data and is delimited before returning to the model.
- Prompt text cannot grant capabilities, expand filesystem roots, change network policy, or alter confirmation requirements.
- Ambiguous low-confidence commands result in clarification, not execution.

## 10. Memory Architecture

### 10.1 Ownership

SQLite is the system of record. ChromaDB is a derived semantic index and must be rebuildable from SQLite.

Planned SQLite domains include users, auth sessions, conversations, turns, memory items, tasks, capability grants, action requests, confirmation challenges, scheduled jobs, audit events, and semantic-index outbox records.

ChromaDB collections contain embeddings and bounded text for semantic retrieval, with metadata that references SQLite record IDs, category, timestamps, and retention class. ChromaDB never owns deletion state or authoritative content.

### 10.2 Write and Index Flow

1. A validated memory change and an index-outbox row commit in one SQLite transaction.
2. An index worker applies the upsert/delete to ChromaDB.
3. The outbox row records success or retry metadata.
4. Retrieval filters Chroma candidates against current SQLite records before returning them.
5. An index repair job can rebuild all embeddings from SQLite.

This prevents partial Chroma failures from losing durable memory or resurrecting deleted records.

### 10.3 Retention and Consolidation

- Preferences: retained until explicitly changed or deleted.
- Tasks: retained until completion, then archived or expired by configured policy.
- Casual conversation: expires after 30 days unless pinned.
- Pinned content: excluded from automatic deletion.
- Consolidation: scheduled summarization proposes durable facts with provenance; deduplication prevents repeated facts.
- Hard delete: removes the SQLite record, related embeddings, cached excerpts, and export staging files, then records only a content-free audit marker.
- Export: creates a user-requested, time-limited archive and never uploads it automatically.

## 11. Authentication and Authorization Architecture

Tara uses a single owner identity but still authenticates every request.

- First-run bootstrap is available only when no owner exists and only from the local host or an explicit one-time bootstrap secret.
- The owner passphrase is stored as a memory-hard password hash; plaintext credentials are never stored.
- The browser receives short-lived, signed, `HttpOnly`, `Secure`, `SameSite=Strict` access and refresh cookies.
- State-changing HTTP requests require CSRF protection and origin validation.
- WebSocket connections use a short-lived, single-use ticket minted by an authenticated HTTPS request. Long-lived tokens never appear in WebSocket URLs or logs.
- Sessions are device-labeled, rotatable, revocable, and invalidated when security settings change.
- Capability grants are separate from authentication. An authenticated user still cannot invoke a disabled tool.
- Tailscale is a network boundary, not a substitute for application authentication.

## 12. WebSocket Architecture

REST owns durable state; one assistant WebSocket owns the live voice session.

- Endpoint: `/ws/v1/assistant`.
- Text frames carry versioned JSON control events.
- Binary frames carry negotiated audio for the single active input or output stream identified by surrounding control events.
- Every JSON event includes protocol version, event ID, session ID, sequence number, type, timestamp, and payload.
- The server emits authoritative assistant states and transcript events.
- Heartbeats detect dead peers. Reconnect creates a new socket and may resume durable conversation context, but never silently resumes microphone streaming or a pending confirmation.
- Confirmation challenges expire on disconnect unless explicitly marked resumable by policy; v1 defaults to non-resumable.
- Unknown event types, invalid sequencing, oversized frames, and unsupported codecs fail with explicit protocol errors.

The complete message catalog is defined in `API_CONTRACT.md`.

## 13. API Strategy

- Version all HTTP resources under `/api/v1` and WebSocket protocols under `/ws/v1`.
- Use REST resources for auth, conversations, memories, capabilities, confirmations, schedules, settings, diagnostics, and exports.
- Use cursor pagination for histories and memories.
- Require idempotency keys for mutation requests that could be retried.
- Use a single structured problem response with stable machine codes and correlation IDs.
- Generate and review OpenAPI from FastAPI, then use the checked contract to generate or validate frontend types. Generated artifacts never replace source review.
- Avoid generic remote-code or unrestricted tool endpoints.

## 14. Error Handling

Errors are categorized as validation, authentication, authorization, confirmation required, dependency unavailable, timeout, conflict, rate/backpressure, and unexpected internal error.

- User messages are calm, specific, and actionable.
- Client retries only idempotent requests and transient failures, using capped exponential backoff with jitter.
- LLM, STT, and TTS timeouts cancel downstream work and return the assistant to a recoverable state.
- If ElevenLabs fails before audio starts, switch to Piper when local fallback is enabled. If failure occurs mid-utterance, stop cleanly and announce the fallback rather than overlapping voices.
- ChromaDB failure degrades semantic recall but does not block structured memory CRUD.
- SQLite write failure prevents the associated side effect from being reported as durable success.
- Unknown tool outcomes after timeout are reported as uncertain and must not be automatically retried unless the tool is idempotent.

## 15. Logging and Observability

All backend logs are structured JSON with UTC time, severity, service, event name, correlation ID, session ID, conversation ID, turn ID, tool/action ID, duration, outcome, and safe error code where applicable.

- Redact secrets, cookies, authorization values, prompts, transcripts, memory content, raw audio, file contents, and third-party payload bodies by default.
- Audit events separately record authentication changes, capability changes, confirmation decisions, tool starts/results, exports, hard deletes, and security policy failures.
- Metrics include end-of-speech to first-audio latency, STT latency, model first-token latency, TTS first-byte latency, WebSocket reconnects, VAD turn errors, tool success, confirmation rejection/expiry, index lag, scheduler job outcomes, and dependency health.
- Health surfaces distinguish liveness, readiness, and optional-dependency degradation.
- Log retention is bounded and configurable; diagnostics export requires explicit user action and redaction.

## 16. Deployment and Operations

- Run schema migrations as an explicit pre-start step with a verified backup; do not run destructive migrations silently on application startup.
- Keep the FastAPI scheduler in one designated process.
- Store secrets outside source control with OS-level file permissions or an OS credential facility.
- Back up SQLite with its online backup mechanism and capture a consistent Chroma snapshot or rebuild marker.
- Test restore, not only backup creation.
- Pin model identifiers and record model metadata so behavior changes are traceable.
- Provide authenticated service status for Next.js, FastAPI, SQLite, ChromaDB, Ollama, faster-whisper, ElevenLabs, Piper, scheduler, microphone support, and last successful voice turn.
- Make local mode explicit and visibly indicate when cloud TTS is enabled.

## 17. Coding Standards and Folder Conventions

### Frontend

- Strict TypeScript; no implicit `any`.
- Components are small and accessibility-first; domain logic does not live in JSX.
- Files exporting React components use `PascalCase.tsx`; hooks use `useX.ts`; stores use `<domain>Store.ts`; route folders use kebab-case.
- Network calls go through typed feature clients. Components do not construct URLs.
- Prefer composition over variant-heavy universal components.
- All animation honors reduced-motion preferences.

### Backend

- Python 3.12 with complete public type annotations.
- Modules and functions use `snake_case`; classes and schemas use `PascalCase`; constants use `UPPER_SNAKE_CASE`.
- Routers validate and delegate. Services orchestrate. Repositories persist. Providers integrate.
- Avoid import-time model loading, database connections, or scheduler startup.
- Use explicit dependency injection at composition boundaries.
- Database migrations are forward-only, reviewed, and reversible through backup/restore when data transforms are destructive.

### Cross-Cutting

- Public IDs are opaque UUIDs; database keys and user content are never encoded in URLs.
- Use UTC internally and localize only in the presentation layer.
- Stable event names and error codes are lowercase dotted strings.
- Every consequential tool declares its capability, risk class, confirmation policy, timeout, and idempotency behavior.

### Naming Conventions

- REST collection paths use plural kebab-case nouns; path parameters use `snake_case` names in contract documentation.
- WebSocket event names use lowercase dotted domains, with the resource first and lifecycle second, such as `audio.input.start`.
- React components and Python classes use `PascalCase`; TypeScript values use `camelCase`; Python values and database identifiers use `snake_case`.
- Test IDs use the uppercase domain prefix and three-digit sequence defined in `TEST_MATRIX.md`.
- Configuration keys are explicit and domain-prefixed; avoid ambiguous names such as `mode`, `path`, or `enabled` without context.

## 18. Testing Strategy

- Frontend unit/component tests: pure view models, state transitions, responsive component behavior, accessibility, and error states.
- Backend unit tests: policy, routing, memory retention, confirmation binding, permissions, and provider fallbacks.
- Integration tests: FastAPI with temporary SQLite and Chroma, Alembic migrations, WebSocket protocol, scheduler leadership, and provider fakes.
- Contract tests: generated OpenAPI compatibility and versioned WebSocket event fixtures.
- End-to-end tests: login, four core screens, live text-mode turn, voice fixture turn, confirmation flow, memory lifecycle, reconnect, and offline fallback.
- Security tests: CSRF, origin checks, session revocation, WebSocket ticket replay, capability denial, path traversal, prompt injection, and log redaction.
- Performance tests: latency budgets, long conversation memory bounds, audio backpressure, and Ollama timeout recovery.
- Manual device tests: mobile browser/PWA and desktop browser behavior, microphone permissions, sleep/lock capability boundary, accessibility, and Tailscale deployment.

Detailed cases and release gates are maintained in `TEST_MATRIX.md` and `MANUAL_TESTS.md`.

## 19. Architecture Invariants

1. No consequential side effect executes without capability permission and a valid confirmation decision.
2. The model never directly controls credentials, authorization, filesystem roots, or confirmation policy.
3. SQLite remains authoritative; ChromaDB can be destroyed and rebuilt without losing durable memory.
4. The browser never receives ElevenLabs credentials or backend service secrets.
5. WebSocket reconnect never resumes recording or confirms an action implicitly.
6. Mobile and desktop layouts share routes, domain components, semantic tokens, and Guide Star states.
7. Unsupported native-device behavior is exposed honestly in product status and planning.
