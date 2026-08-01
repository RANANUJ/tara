# Tara Architecture Decisions

## 1. Decision Record Policy

This file records decisions that constrain multiple parts of Tara or are expensive to reverse. Status values are `Proposed`, `Accepted`, `Superseded`, or `Rejected`. New decisions receive the next sequential ID and include consequences, not only rationale.

## ADR-001 — Responsive Web Application Instead of Flutter

- Status: Accepted
- Date: 2026-08-01
- Decision: "Tara will be implemented as a responsive web application using React + Next.js instead of Flutter."
- Context: The PRD describes Flutter mobile and desktop shells, but the approved product direction mandates one responsive application using React 19 and Next.js 15 App Router.
- Rationale: One web codebase maximizes component and design-system reuse, aligns all mobile and desktop screens, and removes Flutter from the project stack.
- Consequences: Mobile and desktop share routes, domain components, state management, and Guide Star tokens. Navigation and density adapt by layout. Standard browser/PWA constraints mean locked-screen wake listening, Android foreground services, direct calls/SMS, notification access, Accessibility Service automation, and desktop system-tray docking cannot be claimed as implemented. Those capabilities require a later, explicitly approved native bridge/host decision.

## ADR-002 — FastAPI Modular Monolith

- Status: Accepted
- Date: 2026-08-01
- Decision: Implement the Python backend as one modular monolith with explicit API, application, domain-policy, and infrastructure boundaries.
- Rationale: Tara is a single-user local deployment. A modular monolith keeps installation, transactions, debugging, and latency simpler than distributed services while preserving replaceable internal providers.
- Consequences: Routers remain thin; domain modules cannot reach across persistence/provider boundaries casually. Extraction into services requires measured isolation or scaling need.

## ADR-003 — Private Same-Origin Deployment Through Tailscale

- Status: Accepted
- Date: 2026-08-01
- Decision: Serve Next.js and FastAPI through one private HTTPS origin reachable over Tailscale, with no direct public or unauthenticated LAN exposure.
- Rationale: The PRD requires private encrypted transport while the browser requires a secure context for microphone APIs. Same-origin routing simplifies cookie security and CORS.
- Consequences: Tailscale is required for remote access but does not replace application authentication. Deployment must route `/api/v1` and `/ws/v1` to FastAPI and other paths to Next.js.

## ADR-004 — REST for Durable State, WebSocket for Live Assistant Sessions

- Status: Accepted
- Date: 2026-08-01
- Decision: Use versioned REST resources for durable data and commands, and one authenticated WebSocket for live voice/audio, transcript, state, confirmation, and tool progress.
- Rationale: Resource management benefits from conventional idempotency and caching; real-time voice needs low-overhead bidirectional streaming and cancellation.
- Consequences: Durable effects observed over WebSocket must also be queryable through REST. Reconnection refetches durable state and never resumes audio capture or confirmation implicitly.

## ADR-005 — SQLite Is Authoritative; ChromaDB Is Derived

- Status: Accepted
- Date: 2026-08-01
- Decision: Store authoritative memory, retention, provenance, and deletion state in SQLite; use ChromaDB only as a rebuildable semantic index.
- Rationale: Dual authoritative stores create irreconcilable partial failures and make hard delete unreliable.
- Consequences: Every semantic index change originates from a transactional SQLite outbox. Retrieval validates Chroma candidates against SQLite. Index rebuild and deletion verification are required operations.

## ADR-006 — Deterministic Confirmation Outside the LLM

- Status: Accepted
- Date: 2026-08-01
- Decision: Server-owned policy classifies action risk and controls a one-time confirmation state machine; model output cannot waive or satisfy confirmation.
- Rationale: The PRD identifies confirmation before action as the product's most important safety rule. Model judgment and wake/STT accuracy are insufficient controls.
- Consequences: Sending, calling, spending, deleting, sensitive export, and security broadening pause before execution. Challenges bind exact normalized arguments, owner session, capability, target version, and expiry.

## ADR-007 — Scoped Capability Grants

- Status: Accepted
- Date: 2026-08-01
- Decision: Authorize tools through independent capabilities with default-deny grants rather than one general automation permission.
- Rationale: Reading files and sending messages have different consequences and revocation needs.
- Consequences: Every tool declares one or more precise capabilities. Permission changes are audited and invalidate affected pending confirmations.

## ADR-008 — Local-First, Replaceable AI Providers

- Status: Accepted
- Date: 2026-08-01
- Decision: Use Ollama for v1 language models, faster-whisper for STT, Silero VAD, ElevenLabs for primary online TTS, and Piper for offline TTS through provider interfaces.
- Rationale: This meets the approved stack and PRD goals for privacy, low recurring cost, quality voice, and vendor flexibility.
- Consequences: Provider health, timeouts, cancellation, format negotiation, and fallback are explicit. A cloud LLM is not configured in v1 and requires a separate privacy/architecture decision.

## ADR-009 — Two-Tier Local Model Routing

- Status: Accepted
- Date: 2026-08-01
- Decision: Route simple intents to a small fast Ollama model and reasoning-heavy work to a larger local Ollama model, with bounded deterministic/model-assisted classification.
- Rationale: Common commands must prioritize latency while complex tasks need stronger reasoning.
- Consequences: Routing decisions and timing are observable. Low confidence asks for clarification. Both models remain subject to identical tool, permission, and confirmation controls.

## ADR-010 — Server-Authoritative Voice Turn State

- Status: Accepted
- Date: 2026-08-01
- Decision: The FastAPI voice pipeline owns authoritative turn boundaries and assistant state; browser audio activity is a hint and visualization input.
- Rationale: Silero VAD and downstream cancellation need one consistent source of truth across reconnects and browser differences.
- Consequences: Client state follows versioned WebSocket events. Barge-in cancels the prior turn across model and TTS work. Browser suspension is surfaced as a capability limit.

## ADR-011 — TanStack Query and Zustand Have Non-Overlapping Ownership

- Status: Accepted
- Date: 2026-08-01
- Decision: TanStack Query owns server-derived data; Zustand owns ephemeral assistant-runtime and presentation state only.
- Rationale: Duplicating durable state in a client store creates stale, conflicting sources of truth.
- Consequences: WebSocket durable-change events update or invalidate query caches. URL state owns shareable filters. Local component state owns forms.

## ADR-012 — Single Scheduler Leader

- Status: Accepted
- Date: 2026-08-01
- Decision: Run APScheduler in exactly one designated FastAPI process for v1.
- Rationale: SQLite and an in-process scheduler do not safely support duplicate job leaders without additional coordination infrastructure.
- Consequences: v1 backend deployment uses one application process or separately designates a sole scheduler process. Scaling workers requires a new scheduler leadership decision.

## ADR-013 — No Raw Audio Retention by Default

- Status: Accepted
- Date: 2026-08-01
- Decision: Treat captured audio as transient and do not persist it unless the owner explicitly enables time-limited diagnostics.
- Rationale: Raw voice is highly sensitive and is not required for normal assistant operation.
- Consequences: Logging and tracing contain timing/format metadata only. Diagnostics mode requires visible consent, strict expiry, and separate deletion verification.

## ADR-014 — Web-Only Native Capability Status

- Status: Accepted
- Date: 2026-08-01
- Decision: Represent device-native PRD capabilities as `requires_native_bridge` until an approved bridge exists; do not simulate support through misleading UI or unsafe browser workarounds.
- Rationale: Browser APIs cannot satisfy the PRD's screen-off wake word and Android action requirements reliably or securely.
- Consequences: The Actions and Settings screens explain the limitation. Milestones test foreground web behavior independently. Any future bridge must reuse existing auth, capability, action, and confirmation contracts.

## ADR-015 — Explicit Migration and Backup Before Upgrade

- Status: Accepted
- Date: 2026-08-01
- Decision: Apply Alembic migrations as an explicit deployment step after a verified backup rather than silently during ordinary application startup.
- Rationale: Tara stores personal data and has no multi-node database safety net; failed data migrations must be recoverable.
- Consequences: Releases include migration compatibility checks and restore instructions. Destructive transforms require a documented rollback through backup restoration.
