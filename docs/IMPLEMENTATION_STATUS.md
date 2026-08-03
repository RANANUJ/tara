# Tara Implementation Status

## M16 In Progress - Proactive Reminders and Briefings

- Completed scope: introduced framework-neutral one-time/bounded recurring schedule validation, the initial owner-scoped `scheduled_tasks` persistence schema, and an initial owner-scoped creation/list/pause service with SHA-256 idempotency identity. `ScheduledTaskService.create` now accepts only an authenticated owner/session context plus `ScheduledTaskCreateCommand`, resolves the canonical capability registry, validates its arguments, derives risk through the shared action policy, and persists only a generic target label plus SHA-256 target, parameter, and binding hashes.
- Migrations: `20260803_0007_scheduled_tasks` follows `20260802_0006` and adds UTC task lifecycle, safe session provenance, idempotency, and due-task indexes. `20260803_0010_scoped_task_idempotency` follows `20260803_0009`, replaces the owner-only constraint with `uq_scheduled_tasks_owner_session_idempotency`, and scopes the SHA-256 idempotency-key hash to `(owner_id, owner_session_id, idempotency_key_hash)` without adding raw payload, secret, target, or parameter columns.
- M14 proposal attachment: a consequential task is first committed in `pending_confirmation`, with `enabled=false` and `next_run_at=null`. The existing authenticated M14 confirmation service then creates exactly one owner/session-bound proposal using a canonical request that hashes and binds task ID, capability ID, target-identity hash, parameter hash, normalized-instruction hash, normalized schedule, timezone, and task binding hash. The proposal uses the canonical M14 two-minute expiry; only its ID, awaiting-confirmation status, expiry, and binding hash are attached to the task through the owner-scoped repository.
- M14 approval and activation: `ScheduledTaskService.approve_confirmation(context, task_id, response)` accepts only the authenticated owner/session context, owner-scoped task ID, and ordinary M14 affirmative input. It re-derives the canonical safe binding from persisted task fields, confirms the owner/session, link ID, awaiting state, expiry, capability schema, hashes, instruction, schedule, timezone, and M14 request hash before calling the existing authenticated response and one-time-consumption operations. A consumed proposal conditionally transitions only the still-pending linked task to `active`, sets `enabled=true`, calculates `next_run_at` from the validated persisted schedule, and records the existing M14 `executing` status. Replay, expired/missing/mismatched links, wrong session, invalid approval, terminal/non-pending state, and unavailable capabilities return safe errors or non-enumerating absence without mutating the task.
- Invalidation: changing an attached consequential task's currently supported bound instruction or schedule through `update` clears its link, status, expiry, and binding metadata, restores `pending_confirmation`, disables execution, and clears `next_run_at`. Capability, target identity, and parameter metadata remain internal immutable fields at this stage; any unexpected persisted change is rejected by M14 request-hash revalidation before approval. Fresh M14 proposal creation after a supported bound-field update remains the next increment.
- Proposal safety and idempotency: no confirmation secret, token, raw target, raw parameters, provider data, or hidden reasoning is stored in `scheduled_tasks` or task audit records. Equivalent duplicate creation returns the existing attached proposal and creates no second proposal; a mismatched idempotency payload is rejected. Proposal creation or attachment failure raises only `task_confirmation_unavailable`; the committed task remains disabled, pending confirmation, and non-executable. An attachment failure may leave the existing M14 proposal unlinked but unreachable through the task and without a delivered secret; later work must define bounded orphan cleanup.
- Concurrency: same-process creates use a reference-counted lock scoped to owner, authenticated session, and idempotency-key hash across task creation and proposal attachment. The database constraint remains the cross-instance authority; an `IntegrityError` rolls back through the Unit of Work, re-reads the scoped winner, returns it only when its normalized binding hash matches, and otherwise returns `idempotency_key_payload_mismatch`. Consequently, equivalent concurrent consequential creates share one task and one attached M14 proposal; different owners or sessions use independent identities. Conditional repository activation compares owner, session, pending state, disabled state, confirmation ID, and binding hash, so a lost approval or invalidation/cancel race cannot activate the task twice or activate an obsolete binding.
- Scheduler runtime groundwork: migration `20260803_0011_task_claims_and_runs` adds nullable claim identity/timestamps and content-minimized `scheduled_task_runs` metadata. `ScheduledTaskScheduler` is a disabled-by-default, process-local async poller with explicit start/stop, bounded polling, due batches, global and per-owner semaphores, conditional active/enabled/due claim updates, claim leases, and safe run records. It is composed once in the application lifecycle and performs no work on import, readiness, or status reads.
- Scheduler execution boundary: the current approved task schema deliberately stores only target/parameter hashes. The runtime therefore fails a claimed task closed with a sanitized `task_execution_payload_unavailable` or `task_capability_unavailable` outcome instead of reconstructing private inputs, invoking arbitrary code, or persisting plaintext action payloads. Registered capability execution requires a separately designed safe transient/reference payload mechanism and focused scheduler runtime tests before M16 can complete.
- Protected payload foundation: migration `20260803_0012_task_execution_payloads` adds one owner/task-bound AES-256-GCM envelope per task. The dedicated base64 `TARA_TASK_PAYLOAD_ENCRYPTION_KEY` is validated as exactly 32 bytes when the scheduler is enabled, is redacted from logs, and is never derived from `service_secret`. Fresh 12-byte nonces, versioned AES-GCM ciphertext, and authenticated data bind payload version, task, owner, capability, and binding hash. Creation stores only ciphertext/nonce/binding metadata transactionally with the task; absent keys fail task creation closed while a disabled scheduler may start without a key.
- Scheduler execution increment: claimed tasks now load only an active owner/task-scoped payload, require matching capability and binding metadata, decrypt inside the execution scope, revalidate the registered capability arguments, and submit only the reconstructed transient request to the central `SafetyToolExecutor`. Conditional run transitions record `claimed -> running -> completed` for successful/uncertain results and fail closed with safe codes for unavailable, invalid, or denied payload execution. One-time runs complete; recurring runs use the persisted normalized schedule for the next occurrence. No decrypted input or tool output is persisted.
- Runtime safety increment: owner-scoped cancellation now revokes the protected payload, clears the claim, disables the task, and conditionally marks an in-flight claimed/running run canceled; repeat cancellation is idempotent. Failed-claim transitions require the task to remain active, preventing a scheduler error or late completion from overwriting cancellation. `TARA_SCHEDULER_RUN_TIMEOUT_SECONDS` (default `30`, bounded `1..300`) wraps central execution and produces only the sanitized `task_execution_timed_out` terminal code.
- Typed update increment: `ScheduledTaskUpdateCommand` is an explicit allowlist for title, instruction, schedule, capability, target, and parameters. Capability/target/parameter changes require complete transient execution inputs. Every binding-affecting update decrypts only within the payload boundary, remaps the registered capability and policy, writes a fresh AES-GCM nonce/ciphertext in the same Unit of Work, refreshes safe hashes/metadata, and never reconstructs inputs from persisted hashes. Consequential updates invalidate the previous M14 linkage and remain disabled/pending confirmation; read-only updates restore active state only after successful replacement.
- Retention foundation: the process-local scheduler owns one best-effort cleanup cadence. `TARA_SCHEDULER_CLEANUP_INTERVAL_SECONDS` (10..3600), `TARA_SCHEDULER_CLEANUP_BATCH_SIZE` (1..256), `TARA_SCHEDULER_PAYLOAD_RETENTION_HOURS` (1..8760), and `TARA_SCHEDULER_RUN_RETENTION_DAYS` (1..365) bound oldest-first deletion of revoked/expired encrypted payloads and terminal task-run metadata. Cleanup never decrypts payloads, does not run on import/readiness/status, is isolated from due-task polling failures, and remains disabled with the scheduler.
- Focused task coverage: `backend/tests/tasks/test_task_service.py` now verifies read-only direct activation, registered/disabled/invalid capability rejection, safe hashes, consequential proposal owner/session/hash binding, expiry attachment, idempotent proposal reuse, no raw persistence/audit payload, safe proposal/attachment failures, owner/session M14 approval, exactly-once consumption, activation with a computed next run, replay rejection, persisted binding mismatch rejection, instruction invalidation, ten-way equivalent consequential creation, mismatched-payload creation race rejection, session isolation, and two-way approval activation race safety.
- Files changed in this increment: `backend/migrations/versions/20260803_0010_scoped_task_idempotency.py`, `backend/src/tara_api/persistence/models/entities.py`, `backend/src/tara_api/persistence/repositories/tasks.py`, `backend/src/tara_api/tasks/service.py`, `backend/src/tara_api/observability/health.py`, `backend/tests/tasks/test_task_service.py`, and `docs/IMPLEMENTATION_STATUS.md` (alongside the prior M16 confirmation files already in progress).
- Files changed in this increment: `backend/migrations/versions/20260803_0011_task_claims_and_runs.py`, `backend/src/tara_api/config/settings.py`, `backend/src/tara_api/main.py`, `backend/src/tara_api/persistence/models/__init__.py`, `backend/src/tara_api/persistence/models/entities.py`, `backend/src/tara_api/persistence/repositories/tasks.py`, `backend/src/tara_api/tasks/scheduler.py`, `backend/src/tara_api/observability/health.py`, `backend/src/tara_api/api/v1/websocket.py`, `backend/tests/tasks/test_task_service.py`, and `docs/IMPLEMENTATION_STATUS.md` (alongside the prior M16 confirmation files already in progress).
- Validation: `python -m pytest tests/tasks tests/test_migrations.py tests/test_health.py -q` passed (28); `python -m pytest tests -q` passed (262); `python -m ruff check . --no-cache` passed; and `python -m mypy src --cache-dir .mypy_cache_run --no-incremental` passed (111 source files). The only output warning remains the pre-existing upstream `StarletteDeprecationWarning` from FastAPI's `TestClient`.
- Validation: task/migration/readiness tests passed (33); `python -m ruff check . --no-cache` passed; and `python -m mypy src --cache-dir .mypy_cache_run --no-incremental` passed (112 source files). The only output warning remains the pre-existing upstream `StarletteDeprecationWarning` from FastAPI's `TestClient`.
- Remaining M16 work: completed-one-time/orphan payload cleanup and owner-deletion tests; complete scheduler runtime tests for eligibility, concurrent claiming, cancellation, bounded concurrency, recurrence, timeouts, and shutdown; full lifecycle/retry policy completion; fresh proposal creation after invalidation; REST/WebSocket transport; frontend task management; scheduler health/status; final documentation; and acceptance. M16 is not complete and no M17 work has started.

## M15 Complete - Two-Tier Routing and Multi-Step Agent

- Completed scope: added deterministic, server-owned fast/reasoning local-model selection with stable rationale codes. Safe response metadata exposes only the chosen tier and rationale; persistence retains the same non-secret metadata with the assistant turn.
- Bounded tool loop: the agent can create only server-planned registered read-only requests and executes them exclusively through the existing central safety executor. The loop is limited by `TARA_AGENT_MAX_TOOL_ITERATIONS` (default `2`, maximum `4`), stops after a non-success result, and remains within the request cancellation and timeout boundary.
- Safety: tool results are length-bounded, rendered as `UNTRUSTED_TOOL_RESULT` prompt data, and never become instruction, identity, permission, policy, or confirmation input. No client or model-supplied tool call protocol, provider fallback, real external action, semantic retrieval change, or M16 behavior was added.
- Files changed: `backend/src/tara_api/domain/agent.py`, `backend/src/tara_api/agent/service.py`, `backend/src/tara_api/agent/tiered.py`, `backend/src/tara_api/agent/tools.py`, `backend/src/tara_api/agent/registry.py`, `backend/src/tara_api/persistence/agent_store.py`, `backend/src/tara_api/api/v1/websocket.py`, `backend/src/tara_api/main.py`, settings/environment configuration, M15 agent tests, and the listed contract/security/test documents.
- Commands and results: `python -m pytest backend/tests/agent/test_tiered_routing.py backend/tests/agent/test_tool_loop.py backend/tests/agent/test_m15_agent_loop.py backend/tests/tts/test_tts_websocket.py -q` passed (8); `python -m ruff check backend` passed; `python -m mypy backend/src` passed (105 source files); `python -m pytest backend/tests -q` passed (237); and `pnpm validate` passed frontend lint/typecheck/tests (18)/production build plus backend Ruff/mypy/tests (237). The sole warning is the existing upstream `StarletteDeprecationWarning` from `TestClient`. Standard validation used only fake providers and local test doubles; no model download, network access, or external action occurred.
- Unresolved blockers: none for M15 automated acceptance. Manual local-Ollama dual-model performance and cancellation checks remain opt-in deployment verification.
- Exact recommended next milestone: M16 - Proactive Reminders and Briefings. Do not begin M16 as part of M15.

## M14 Complete - Confirmation Gate and Consequential Tool Harness

- Completed scope: added an authenticated, non-production fake consequential-action harness. It creates owner/session-bound confirmation challenges, accepts only explicit affirmative responses through the existing deterministic confirmation service, consumes authorization once, and records only safe synthetic audit metadata.
- Safety: the fake action is disabled by default, rejected in production, performs no external side effect, and cannot be completed by ambiguous responses, replay, cross-session use, expiry, or altered parameters. Configurable uncertain mode reports `uncertain` and never claims success or retries automatically.
- API: authenticated `POST /api/v1/confirmations/fake-consequential` proposes a synthetic action; `POST /api/v1/confirmations/{confirmation_id}/respond` resolves the confirmation and reports its safe lifecycle state.
- Configuration: `TARA_FAKE_CONSEQUENTIAL_ENABLED=false` and `TARA_FAKE_CONSEQUENTIAL_UNCERTAIN=false` remain the secure defaults.
- Validation: focused capability/confirmation tests pass (5); mypy passes (103 source files). No external provider, network access, download, or M15 behavior was added.
- Exact recommended next milestone: M15 - Two-Tier Routing and Multi-Step Agent. No M15 work was started.

## M13 Complete - Capability Registry and Read-Only Tools

- Completed scope: added a typed server-side capability catalog, authenticated Actions API and responsive Actions screen, and one constrained `filesystem.list` read-only local tool. The tool is disabled by default and can only list names inside explicitly configured allowlisted roots.
- Safety: all execution flows through the existing default-deny permission, deterministic policy, central safety executor, and redacted audit publisher. Canonicalization rejects absolute paths, traversal, and resolved targets outside allowlisted roots before filesystem access. Native-only capabilities are cataloged as `requires_native_bridge` with no execution path.
- Configuration: `TARA_TOOLS_FILESYSTEM_READ_ENABLED=false` and `TARA_TOOLS_FILESYSTEM_READ_ROOTS=[]` are the secure defaults. No root path, file content, credentials, provider payload, or tool exceptions are logged or returned.
- Files changed: `backend/src/tara_api/domain/capabilities.py`, `backend/src/tara_api/capabilities`, `backend/src/tara_api/api/v1/actions.py`, `backend/src/tara_api/main.py`, settings/environment configuration, focused capability tests, and `frontend/app/actions` plus `frontend/lib/actions.ts`.
- Validation: focused capability tests passed (3); frontend typecheck and tests passed (18). Ruff passed. Mypy was rerun after the final serializer narrowing fix. No external provider, network access, model download, or M14 implementation is required.
- Manual checks remaining: configure a synthetic local root, authenticate, inspect capability states on mobile and desktop, list a harmless folder, attempt traversal and a symlink/junction escape, then revoke the session and verify subsequent requests fail.
- Exact recommended next milestone: M14 - Confirmation Gate and Consequential Tool Harness. No M14 work was started.

## M12 Complete - Retention, Consolidation, Export, and Hard Delete

- Completed scope: M12 adds APScheduler-compatible hourly retention and daily consolidation services, 30-day casual expiry defaults, pinned exemption, confirmed hard deletion, and short-lived confirmed export artifacts. SQLite remains authoritative; semantic-index delete work uses the transactional outbox, while staged export data is scrubbed on expiry or explicit removal.
- Files changed: M11/M12 changes span wake-word transport/status/lifecycle, `backend/src/tara_api/memory`, persistence outbox/task-status models and migrations `20260802_0005`/`20260802_0006`, configuration, health, tests, and the memory/wake-word contract and boundary documents.
- Validation: `pytest backend/tests -q` passed (226); `pnpm validate` passed frontend lint/typecheck/tests (17)/production build and backend Ruff/mypy/tests (226). The only output warning is the existing upstream `StarletteDeprecationWarning` from `TestClient`.
- Remaining limits: no real wake-word engine, native background audio, screen-off/locked-device capture, or public memory-product API is claimed. M13 is the next milestone.

## M11 Complete - Structured and Semantic Memory plus Foreground Wake-Word Transport

- Completed scope: authenticated foreground wake-word enable/disable, state/detected/error delivery, audio-session binding, TTS-aware suspension, disconnect cleanup, readiness/status integration, and an explicit native-background boundary. Detection remains foreground-only and never triggers an agent or action.
- Memory scope: SQLite structured memory has provenance, categories, pinning, expiry, task status, deterministic bounded browse/context ordering, optional local ChromaDB derived indexing, a transactional index outbox, SQLite-authorized semantic filtering, unavailable-index lexical fallback, and rebuild support.
- Validation: deterministic fakes and isolated SQLite cover wake-word and semantic-index boundaries without microphone, model download, or network access.

## M10 Final Acceptance - Complete

- Completed scope: M10A provider-neutral final PCM contracts plus deterministic fake, explicit-local Piper, and optional explicit ElevenLabs adapters; M10B bounded process-local final-response TTS service, idempotency, queue/concurrency limits, post-synthesis frame-aligned chunks, transient audio retention, timeout, cancellation, and cleanup; and M10C authenticated agent-response handoff, v1 WebSocket TTS lifecycle/audio events, bounded base64 raw-PCM delivery, foreground browser playback, explicit Stop/VAD barge-in seams, TTS readiness, and authenticated status.
- Provider architecture: disabled remains default; fake is test/development-only; Piper requires explicit local executable/model provisioning; ElevenLabs remains explicit server-only cloud configuration. There is no download, shell interpolation, provider fallback, hidden fake fallback, or normal-log text/audio/credential/path/stderr output.
- Handoff/event behavior: only a completed successful final agent response can create one connection-bound TTS request. `tts.started`, meaningful `tts.state`, `tts.audio.start`, ordered `tts.audio.chunk`, `tts.audio.end`, `tts.canceled`, and sanitized `tts.error` use the existing protocol-v1 envelope. Chunks are final post-synthesis raw mono PCM with base64 transport encoding; no standalone WAV fragments or provider-streaming claim is made.
- Playback/barge-in: the browser controller requires a foreground Web Audio user interaction, rejects malformed/stale/out-of-order chunks, holds one bounded active stream, releases memory on terminal events/socket close, and exposes explicit Stop plus foreground VAD-triggered cancellation. Agent text remains independent of interrupted speech.
- Queue/retention/health: TTS work is FIFO, bounded and process-local; delivery has a per-event timeout and cooperative chunk scheduling. Audio remains process-local and is released before/after delivery, cancellation, timeout, eviction, expiry, disconnect, or shutdown. TTS health never synthesizes or downloads; disabled/optional-unavailable service does not fail readiness, while required unavailable service returns 503. Authenticated status exposes safe provider/format/counter fields only.
- Files changed: `backend/src/tara_api/main.py`, `backend/src/tara_api/domain/health.py`, `backend/src/tara_api/config/settings.py`, `backend/src/tara_api/observability/health.py`, `backend/src/tara_api/api/v1/status.py`, `backend/src/tara_api/api/v1/websocket.py`, `backend/src/tara_api/transport/protocol.py`, `backend/src/tara_api/tts/source.py`, `backend/src/tara_api/tts/registry.py`, `backend/src/tara_api/tts/service.py`, `backend/src/tara_api/tts/health.py`, `frontend/lib/tts-playback.ts`, `frontend/tests/unit/tts-playback.test.ts`, `backend/tests/tts/test_tts_websocket.py`, `backend/tests/tts/test_tts_health_integration.py`, `backend/tests/test_health.py`, `backend/tests/test_m5_framework.py`, `backend/.env.example`, `backend/README.md`, `docs/API_CONTRACT.md`, `docs/SECURITY_MODEL.md`, `docs/TEST_MATRIX.md`, `docs/MANUAL_TESTS.md`, and this status document.
- Commands and results: `python -m pytest backend/tests/tts -q` passed (50); `python -m ruff check backend` passed; `python -m mypy backend/src` passed (84 source files); isolated `python -m pytest backend/tests -q` passed (204); frontend lint/typecheck/tests (12)/production build passed; root `pnpm validate` passed frontend validation/build plus backend Ruff/mypy/tests (204).
- Test results: 0 skipped, 0 xfailed, and 0 failed. The only output warning is the existing upstream `StarletteDeprecationWarning` from `TestClient`. Standard acceptance used fake providers and mocked Web Audio only: no Piper install, ElevenLabs request, download, internet access, real microphone/speaker, wake word, background runtime, or M11 work.
- Manual checks remaining: explicit local Piper and optional ElevenLabs configuration, English/Hindi/mixed/long playback, autoplay and suspended-tab behavior, speakers/headphones echo limitations, slow client/network, repeated turns, disconnect/session revocation, queue saturation, log review, and CPU/memory/latency. None are marked passed.
- Known limitations: transport and retention are process-local and require one backend process; base64 chunks are post-synthesis rather than real-time provider streaming; standard browsers remain subject to user gesture/autoplay, echo-cancellation, tab-suspension, and foreground-only capture/playback limits. No wake word, background/screen-off, native integration, tool, phone, messaging, proactive, or M11 capability is implemented.
- Exact recommended next milestone: M11 - Wake Word and Background Runtime Boundaries. Do not begin M11 as part of M10 acceptance.

## M10B Progress - TTS Service, Queue, Chunking, Persistence Policy, and Cancellation

- Completed scope: added a framework-independent final-agent-response TTS service and a process-local bounded FIFO request registry. Immutable content-minimized request identity binds the owner, authenticated session, optional connection, conversation, source agent request, optional assistant turn, configured provider, voice, language, format, creation time, and derived SHA-256 idempotency hash.
- Lifecycle: requests transition `queued -> preparing -> synthesizing -> chunking -> completed`, with terminal `canceled`, `timed_out`, and `failed` states. Terminal states resolve exactly once; cancellation and timeout suppress late provider results, and the service invokes a provider at most once per accepted job.
- Source boundary and idempotency: commands contain only a source agent request and voice/language/format. A server-side completed-response source port supplies M9-validated final text only after owner/session/connection binding. Duplicate concurrent submissions share one job; provider, fake, Piper, and ElevenLabs selection remains explicit with no fallback.
- Chunking and retention: validated final raw PCM is chunked deterministically after synthesis with frame-aligned offsets, byte lengths, final flag, and duration metadata. This is not real-time streaming and M10B emits no WebSocket events. Audio is transient process-local memory only, bounded by a global byte budget, and released on consumption, cancellation, timeout, eviction, terminal expiry, and shutdown. No audio, text, or TTS metadata is persisted to SQLite, so no migration was needed.
- Cancellation/invalidation: owner/session/connection-bound cancellation, connection and session bulk-cancellation seams, cleanup, and idempotent shutdown are implemented. M10B does not add transport cancellation events, browser playback, microphone barge-in, TTS readiness/status integration, or product UI.
- Files changed: `backend/src/tara_api/domain/tts.py`, `backend/src/tara_api/tts/chunking.py`, `backend/src/tara_api/tts/registry.py`, `backend/src/tara_api/tts/service.py`, `backend/src/tara_api/config/settings.py`, `backend/.env.example`, `backend/README.md`, `backend/tests/tts/m10b_conftest.py`, `backend/tests/tts/test_tts_service.py`, `backend/tests/tts/test_tts_queue.py`, `backend/tests/tts/test_tts_idempotency.py`, `backend/tests/tts/test_tts_chunking.py`, `backend/tests/tts/test_tts_cancellation.py`, `backend/tests/tts/test_tts_cleanup.py`, `backend/tests/tts/test_tts_retention.py`, `backend/tests/tts/test_tts_service_security.py`, `docs/SECURITY_MODEL.md`, `docs/TEST_MATRIX.md`, and this status document.
- Migration revision: none. M10B deliberately keeps audio and TTS request metadata out of SQLite until a reviewed durable requirement exists.
- Commands and results: `python -m pytest` for the eight focused M10B suites passed (15 tests); `python -m pytest backend/tests/tts -q` passed (46 tests); `python -m ruff check backend` passed; `python -m mypy backend/src` passed (83 source files); isolated `python -m pytest backend/tests -q` passed (200 tests); root `pnpm validate` passed frontend lint/typecheck/tests (8)/production build plus backend Ruff/mypy/tests (200).
- Test results: 0 skipped, 0 xfailed, and 0 failed. The only output warning is the existing upstream `StarletteDeprecationWarning` from `TestClient`. Standard validation used deterministic fakes and mocked adapter boundaries only; it required no real Piper installation, ElevenLabs request, model download, internet access, WebSocket delivery, browser playback, or frontend voice feature.
- Limitations: there is no application composition, global health/status wiring, WebSocket delivery, browser playback, active microphone interruption, wake word, background listening, tool execution, proactive behavior, or M11 work in this milestone.
- Exact recommended next sub-milestone after final acceptance: M10C - TTS WebSocket Delivery, Browser Playback, and Barge-In. Do not start M10C or M11 as part of M10B.

## M10A Progress - TTS Domain Contracts and Provider Adapters

- Completed scope: added framework-independent final-only TTS contracts, normalized plain-text/result validation, supported mono PCM signed 16-bit little-endian formats, deterministic fake synthesis, explicit-local Piper subprocess adapter, optional explicit ElevenLabs adapter, and a safe standalone provider-health snapshot.
- Completed scope: added disabled-by-default settings for TTS limits, output format, language/voice, Piper local provisioning, and optional server-only ElevenLabs configuration. No FastAPI composition, global health/status integration, WebSocket event, delivery queue, playback, barge-in, microphone interruption, tool, confirmation, semantic memory, or frontend work was added.
- Provider decisions: Piper is the explicit local adapter with no download, shell interpolation, fallback, or retained temp audio. ElevenLabs is approved by the existing architecture as optional cloud TTS and is implemented only behind an explicit provider/key setting with mocked-only standard tests.
- Files changed: backend/src/tara_api/domain/tts.py, backend/src/tara_api/tts, backend/src/tara_api/config/settings.py, backend/src/tara_api/observability/logging.py, backend/pyproject.toml, backend/.env.example, backend/README.md, backend/tests/tts, docs/SECURITY_MODEL.md, docs/TEST_MATRIX.md, and this status document.
- Settings added: TARA_TTS controls plus server-only TARA_ELEVENLABS_API_KEY and TARA_ELEVENLABS_MODEL; all are disabled/empty by default in backend/.env.example.
- Commands and results: focused M10A suite passed (31 tests); targeted M7-M10/auth/health/migration regression set passed (167 tests); Ruff passed; mypy passed (80 source files); full backend suite passed (185 tests); root pnpm validate passed frontend lint/typecheck/tests (8)/build plus backend Ruff/mypy/tests (185).
- Test results: 0 skipped, 0 xfailed, and 0 failed. The only output warning is the upstream StarletteDeprecationWarning from TestClient. Standard validation used mocked Piper processes and HTTP only; it required no Piper installation, real voice model, ElevenLabs credential, model download, internet access, audio playback, WebSocket event, or frontend voice feature.
- Limitations: synthesis remains final-only and internal. Real Piper/ElevenLabs checks are manual opt-in (tts_integration); M10A intentionally has no WebSocket delivery, browser playback, streaming chunks, service queue, cancellation endpoint, barge-in, or frontend voice UI.
- Exact recommended next sub-milestone after final acceptance: M10B - TTS Service, Queue, Streaming Chunks, and Cancellation. Do not start M10B or M11 as part of M10A.

## M9 Final Acceptance - Complete

### Completed Scope

- Completed the local, final-only text-agent loop: deterministic routing, bounded context, one provider call at most, transactionally persisted content-minimized turns, process-local queue limits, idempotency, cancellation, and no tools, confirmations, TTS, semantic retrieval, or device actions.
- Added authenticated v1 WebSocket `agent.request` and `agent.cancel` handling with strict direct-text payloads and server-owned identity. Accepted requests emit ordered `agent.started` and `agent.state` events followed by exactly one terminal `agent.response`, `agent.canceled`, or sanitized `agent.error`; responses remain bound to the originating connection.
- Integrated final-STT handoff: only a server-issued successful `transcript.final` can submit one agent request. Partial, canceled, timed-out, and failed STT outcomes create none. Disconnect, session invalidation, and shutdown cancel matching agent work without late delivery.
- Integrated bounded LLM dependency readiness and authenticated safe LLM/agent status metadata. Health never generates text, pulls a model, loads STT models, or exposes model paths, URLs, prompt/transcript content, credentials, or provider exceptions.

### Files Changed

- Runtime: `backend/src/tara_api/main.py`, `backend/src/tara_api/api/v1/websocket.py`, `backend/src/tara_api/api/v1/status.py`, `backend/src/tara_api/agent/context.py`, `backend/src/tara_api/agent/registry.py`, `backend/src/tara_api/agent/service.py`, `backend/src/tara_api/observability/application.py`, `backend/src/tara_api/observability/health.py`, `backend/src/tara_api/domain/health.py`, `backend/src/tara_api/domain/transport.py`, and `backend/src/tara_api/transport/protocol.py`.
- Tests and lint alignment: `backend/tests/agent/test_agent_websocket.py`, `backend/tests/agent/test_agent_websocket_handoff.py`, `backend/tests/test_health.py`, `backend/tests/test_m5_framework.py`, and the M9 persistence-model import ordering in `backend/src/tara_api/persistence/models/`.
- Documentation/configuration: `backend/.env.example`, `backend/README.md`, `docs/API_CONTRACT.md`, `docs/SECURITY_MODEL.md`, `docs/TEST_MATRIX.md`, `docs/MANUAL_TESTS.md`, and this status document.

### Commands and Results

| Command | Result |
|---|---|
| `python -m pytest backend/tests/agent/test_agent_websocket.py backend/tests/agent/test_agent_websocket_handoff.py -q` | Passed: 3 tests |
| Targeted agent/STT/audio/transport/auth/health/migration regression set | Passed: 124 tests |
| `python -m ruff check backend` | Passed |
| `python -m mypy backend/src` | Passed: 73 source files |
| `python -m pytest backend/tests -q` | Passed: 154 tests |
| Root `pnpm validate` | Passed: frontend lint/typecheck/tests (8)/build plus backend Ruff/mypy/tests (154) |

The only output warning is the upstream `StarletteDeprecationWarning` from `TestClient`. Validation used deterministic fakes, isolated SQLite databases, mocked local HTTP where existing adapter coverage requires it, and no model download, Ollama process, internet access, GPU, cloud service, TTS, tool, confirmation, or semantic-memory service.

### Unresolved Blockers

- None for M9 acceptance. The optional manual local-Ollama checks remain pending in `docs/MANUAL_TESTS.md` and do not block the offline automated acceptance gate.

### Exact Recommended Next Milestone

M10 - Streaming TTS and Barge-In. Do not begin M10 as part of M9 acceptance.

## M9C Progress - Agent Service, Queue, Persistence, and Cancellation

- Completed scope: added a framework-independent single-pass `AgentService` and bounded process-local FIFO request registry. Requests bind server-authenticated owner/session, optional connection, conversation, source, optional final transcript, SHA-256 idempotency representation, and UTC identity metadata. Partial transcripts create no work; direct text requires an idempotency key.
- Completed scope: implemented the explicit queued → routing → retrieving-context → generating → terminal lifecycle, one-model-call maximum, deterministic ambiguous/unsupported/consequential no-model outcomes, timeout/cancellation handling, disconnect/session cancellation seams, and no tool or confirmation path.
- Completed scope: added Alembic revision `20260801_0004` for owner-scoped conversations, content-minimized `agent_requests`, and safe request linkage/metadata on conversation turns. Successful user/assistant turns and terminal request status use explicit transaction boundaries; prompts, context, raw audio, secrets, tickets, token hashes, and hidden reasoning are not persisted.
- Files changed: `.gitignore`, `backend/src/tara_api/domain/agent.py`, `backend/src/tara_api/agent/registry.py`, `backend/src/tara_api/agent/service.py`, `backend/src/tara_api/persistence/agent_store.py`, `backend/src/tara_api/persistence/models/entities.py`, `backend/src/tara_api/persistence/models/__init__.py`, `backend/src/tara_api/persistence/types.py`, `backend/src/tara_api/persistence/repositories/interfaces.py`, `backend/src/tara_api/persistence/repositories/sqlalchemy.py`, `backend/src/tara_api/persistence/repositories/agent.py`, `backend/src/tara_api/persistence/unit_of_work.py`, `backend/migrations/versions/20260801_0004_agent_service.py`, `backend/src/tara_api/config/settings.py`, `backend/src/tara_api/observability/health.py`, `backend/.env.example`, `backend/tests/agent/`, `docs/SECURITY_MODEL.md`, `docs/TEST_MATRIX.md`, and this status document. The `.gitignore` exception keeps persistence-model Python source trackable while retaining the broad model-artifact exclusion.
- Commands and results: migration test passed; focused agent suite passed (52); Ruff passed; mypy passed (73 source files); full backend suite passed (151); root `pnpm validate` passed frontend lint/typecheck/tests (8), frontend production build, Ruff, mypy, and backend tests (151). One initial full-suite run hit the pre-existing timing-sensitive STT timeout check; its isolated retry and the final full suite passed. The only remaining output warning is the upstream `StarletteDeprecationWarning` from `TestClient`.
- Limitations: the registry is process-local and must run under one backend process; M9C has no WebSocket agent events, HTTP/API exposure, STT transport handoff, LLM health/status integration, TTS, tool execution, confirmation creation, semantic memory, or UI integration. M9 remains in progress. Exact next sub-milestone: M9D - Agent WebSocket/API Integration, Health, Documentation, and Final Acceptance. Do not start M9D or M10 as part of M9C.

## M9B Progress - Intent Router, Prompt Builder, and Structured Context

- Completed scope: added framework-independent deterministic intent-routing, structured-context, prompt-build, sensitivity, provenance, and budget contracts. Consequential routes are conservative risk markers only; informational questions about actions remain non-consequential.
- Completed scope: added server-owned persona/safety prompt messages, explicitly untrusted persisted context, and the final user message. Added no tools, hidden reasoning, agent orchestration, model invocation, WebSocket event, user-facing API, semantic retrieval, ChromaDB, TTS, or device capability.
- Completed scope: added authenticated-owner-bound context selection over existing non-ORM repository records: active pinned structured memories first, then recent completed conversation turns. Context excludes expired memories, non-completed turns, source references, restricted data, and unconfigured private/sensitive data.
- Files changed: `backend/src/tara_api/domain/agent.py`, `backend/src/tara_api/agent/routing.py`, `backend/src/tara_api/agent/prompt.py`, `backend/src/tara_api/agent/context.py`, `backend/src/tara_api/agent/context_policy.py`, `backend/src/tara_api/persistence/repositories/interfaces.py`, `backend/src/tara_api/persistence/repositories/sqlalchemy.py`, `backend/src/tara_api/config/settings.py`, `backend/.env.example`, `backend/tests/agent/test_intent_router.py`, `backend/tests/agent/test_prompt_builder.py`, `backend/tests/agent/test_context_provider.py`, `backend/tests/agent/test_context_policy.py`, `docs/SECURITY_MODEL.md`, `docs/TEST_MATRIX.md`, and this status document.
- Commands run: focused M9B pytest; Ruff; mypy; all agent tests; full backend pytest; root `pnpm validate`; and `git diff --check`.
- Test results: focused M9B tests passed (19); Ruff passed; mypy passed (69 source files); all agent tests passed (37); backend suite passed (136); root validation passed frontend lint/typecheck/tests (8), frontend production build, Ruff, mypy, and backend tests (136). The only output warning is the existing upstream `StarletteDeprecationWarning` from `TestClient`; no test skipped, xfailed, or failed.
- Unresolved blockers: none. M9 remains in progress. Exact recommended next sub-milestone: M9C - Agent Orchestration and Conversation Execution Flow. Do not start M9C as part of M9B.

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
| M11 — Structured and Semantic Memory | Complete | Authoritative SQLite memory, ChromaDB-derived index/outbox, bounded retrieval, and rebuild support |
| M12 — Retention, Consolidation, Export, and Hard Delete | Complete | Scheduled lifecycle services, retention, short-lived exports, and confirmed hard-delete paths |
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
