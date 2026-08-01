# Tara Repository Instructions

## Authority and Scope

- `docs/Tara-PRD-v1.docx` is the product source of truth.
- The approved engineering stack and architecture decisions in `docs/DECISIONS.md` refine the PRD where the PRD still references Flutter or native mobile clients.
- The explicit project decision is: "Tara will be implemented as a responsive web application using React + Next.js instead of Flutter."
- Read `docs/ARCHITECTURE.md`, `docs/SECURITY_MODEL.md`, `docs/API_CONTRACT.md`, and `docs/IMPLEMENTATION_STATUS.md` before making implementation changes.
- This documentation phase contains no application implementation. Do not add feature code unless a later user request explicitly authorizes implementation.

## Non-Negotiable Product Rules

- Keep Tara local-first, single-user, private by default, and reachable only through an authenticated private network deployment.
- Require deterministic confirmation outside the LLM for every action that sends data, places a call, spends money, or deletes data.
- Never represent browser-limited capabilities as supported. Locked-screen wake listening, Android calls/SMS, notification access, Accessibility Service automation, and system-tray behavior require a separately approved native bridge or host.
- Treat SQLite as the authoritative memory store and ChromaDB as a rebuildable semantic index.
- Keep AI, speech, TTS, and tool providers behind replaceable interfaces.
- Preserve the Guide Star states and shared design tokens across mobile and desktop layouts.

## Approved Stack

- Frontend: React 19, Next.js 15 App Router, TypeScript, Tailwind CSS v4, Framer Motion, shadcn/ui, Zustand, TanStack Query.
- Backend: Python 3.12, FastAPI, WebSockets, SQLAlchemy, Alembic, APScheduler.
- AI: Ollama, faster-whisper, Silero VAD, ElevenLabs, Piper.
- Memory: SQLite and ChromaDB.
- Do not introduce Flutter.

## Architecture Rules

- Keep the backend a modular monolith until measured scale or fault isolation requires extraction.
- Keep HTTP routers and WebSocket handlers thin; business rules belong in application services.
- Keep SQLAlchemy models inside persistence code; expose domain entities or response schemas at boundaries.
- Validate all tool arguments server-side. The model may propose a tool call but may not bypass authorization, permission checks, path policy, or confirmation.
- Use REST for durable resources and commands; use WebSockets for live assistant state, transcript, audio, and tool progress.
- Use TanStack Query for server-owned state and Zustand only for ephemeral client/runtime state.
- Default Next.js components to Server Components; use Client Components only where browser APIs, animation, or local interactivity require them.
- Run APScheduler in exactly one backend process. Do not create multiple scheduler leaders against the same SQLite database.

## Coding and Naming Standards

- TypeScript must use strict mode. Avoid `any`; validate all untrusted runtime data.
- Python must be fully type-annotated at public boundaries and use async I/O only for genuinely asynchronous work.
- Use `kebab-case` for route folders and non-component frontend files, `PascalCase` for React components and Python classes, `camelCase` for TypeScript values, and `snake_case` for Python values and database identifiers.
- Name REST resources with plural nouns under `/api/v1`; name WebSocket events as lowercase dotted domains such as `transcript.partial`.
- Use UTC ISO 8601 timestamps at all API boundaries and UUID strings for public identifiers.
- Never log access tokens, raw audio, full prompts, full transcripts, memory contents, or secrets by default.

## Change Discipline

- Implement in the independently testable milestone order defined in `docs/IMPLEMENTATION_PLAN.md`.
- Update `docs/IMPLEMENTATION_STATUS.md` in the same change as implementation progress.
- Add or update tests according to `docs/TEST_MATRIX.md`; run the narrowest relevant checks first.
- Record lasting architecture changes in `docs/DECISIONS.md` and newly discovered delivery threats in `docs/RISKS.md`.
- Do not silently expand scope into post-v1 vision, speaker identification, or a native companion.

## Security Review Triggers

Require explicit security review before changing authentication, confirmation gating, filesystem access, memory deletion/export, tool permissions, WebSocket authorization, secret storage, network exposure, or prompt/tool isolation.
