# Tara API Contract

## 1. Status and Scope

This document is the proposed v1 contract for the responsive web client and the FastAPI backend. It defines behavior and schemas only; no API is implemented by this documentation phase.

The contract has two transports:

- HTTPS REST under `/api/v1` for durable resources, settings, authentication, exports, and explicit commands.
- An authenticated WebSocket under `/ws/v1/assistant` for live assistant state, audio, transcripts, tool progress, and confirmations.

## 2. Contract Conventions

| Concern | Rule |
|---|---|
| Media type | JSON uses `application/json`; errors use `application/problem+json` |
| Versioning | Major version in path; additive fields are backward-compatible within v1 |
| Time | UTC ISO 8601 with `Z` suffix |
| IDs | Opaque UUID strings |
| Property names | `snake_case` on HTTP and WebSocket boundaries |
| Pagination | Cursor-based with `items` and `next_cursor` |
| Mutation retry | `Idempotency-Key` required for retryable mutation commands |
| Correlation | Client may send `X-Request-ID`; server always returns `X-Request-ID` |
| Authentication | Secure session cookies for REST; single-use ticket for WebSocket |
| CSRF | Required for state-changing cookie-authenticated HTTP requests |
| Unknown fields | Ignored on responses; rejected on security-sensitive request schemas |
| Limits | Explicit body, page, audio-frame, transcript, and export limits |

## 3. Common Schemas

### 3.1 Resource Metadata

All durable resources include:

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID | Stable public identifier |
| `created_at` | timestamp | Creation time |
| `updated_at` | timestamp | Last durable change |
| `version` | integer | Optimistic concurrency version |

Mutations of editable resources send the expected `version`. A mismatch returns `409 resource_version_conflict`.

### 3.2 Problem Response

| Field | Type | Meaning |
|---|---|---|
| `type` | string | Stable documentation URI or `about:blank` |
| `title` | string | Short user-safe category |
| `status` | integer | HTTP status |
| `code` | string | Stable machine-readable code |
| `detail` | string | Safe explanation without secrets |
| `request_id` | string | Correlation identifier |
| `errors` | array | Optional field-level validation errors |
| `retryable` | boolean | Whether a retry may succeed without user change |
| `retry_after_ms` | integer | Optional minimum delay |

Representative codes include `validation_failed`, `authentication_required`, `session_expired`, `csrf_failed`, `capability_denied`, `confirmation_required`, `confirmation_expired`, `resource_not_found`, `resource_version_conflict`, `dependency_unavailable`, `provider_timeout`, `rate_limited`, `audio_format_unsupported`, and `internal_error`.

### 3.3 Service State

The public assistant state is one of:

- `idle`
- `listening`
- `transcribing`
- `thinking`
- `awaiting_confirmation`
- `speaking`
- `offline`
- `error`

The UI maps `transcribing` to the Guide Star's Listening or Thinking visual according to whether capture is still active.

## 4. Authentication API

Implemented M4 endpoints are `GET /api/v1/auth/bootstrap/status`, `POST /api/v1/auth/bootstrap`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `POST /api/v1/auth/logout-all`, `GET /api/v1/auth/session`, `GET /api/v1/auth/sessions`, and `DELETE /api/v1/auth/sessions/{session_id}`. Bootstrap status exposes only `bootstrap_required`; bootstrap closes permanently after the first owner. Login and protected calls use `Authorization: Bearer <opaque-session-token>`. Tokens are returned only on bootstrap/login; `session` and `sessions` responses omit the token and token hash. Tokens expire by absolute and idle limits and are never persisted in raw form. Login failures are generic and rate-limit responses never identify an account.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/auth/bootstrap-status` | No | Reports whether initial owner setup is allowed; never exposes owner data |
| `POST` | `/api/v1/auth/bootstrap` | One-time local bootstrap | Creates the only v1 owner and first device session |
| `POST` | `/api/v1/auth/login` | No | Authenticates owner passphrase and creates a device-labeled session |
| `POST` | `/api/v1/auth/refresh` | Refresh cookie + CSRF | Rotates session credentials |
| `POST` | `/api/v1/auth/logout` | Yes + CSRF | Revokes current session and clears cookies |
| `GET` | `/api/v1/auth/session` | Yes | Returns current owner-safe session summary |
| `GET` | `/api/v1/auth/sessions` | Yes | Lists active device sessions |
| `DELETE` | `/api/v1/auth/sessions/{session_id}` | Yes + CSRF | Revokes a device session; current-session revocation logs out immediately |
| `POST` | `/api/v1/auth/websocket-ticket` | Yes + CSRF | Mints a short-lived, one-use WebSocket ticket |

Bootstrap is disabled permanently after owner creation unless an offline administrative recovery procedure explicitly resets it. Login responses never include bearer tokens in JSON.

## 5. Health and Diagnostics API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/health/live` | No | Process liveness only; no dependency or version details |
| `GET` | `/api/v1/health/ready` | Private network | Required dependency readiness with safe state, timestamp, latency, and diagnostic summaries; returns `503` when not ready |
| `GET` | `/api/v1/status` | Yes | Safe owner-only status for application metadata, uptime, database, authentication storage, schema checks, and implemented feature flags only |
| `POST` | `/api/v1/diagnostics/exports` | Yes + CSRF | Creates a redacted diagnostics export after explicit confirmation |

M5 uses one error envelope: `{"error":{"code":"stable_code","message":"safe message","correlation_id":"...","retryable":false}}`. Safe validation field details may be included. `X-Correlation-ID` accepts only bounded safe identifiers; invalid input is replaced with a generated identifier that is returned in every response and error envelope. Secrets, host paths, database URLs, bearer tokens, model prompts, transcript content, and exception text are excluded from status and error responses.

The implemented bootstrap readiness endpoint reports `application` and `database` dependency entries. It returns `200` with `status: ready` only when the database connection succeeds; it returns `503` with `status: unavailable` and `database: unavailable` when the connection cannot be established. It never exposes a database URL, filesystem path, or driver error.

## 6. Conversations API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/conversations` | Starts a durable conversation and returns its ID |
| `GET` | `/api/v1/conversations` | Lists conversations by cursor, newest first |
| `GET` | `/api/v1/conversations/{conversation_id}` | Returns conversation metadata and a bounded recent-turn window |
| `GET` | `/api/v1/conversations/{conversation_id}/turns` | Pages through turns |
| `POST` | `/api/v1/conversations/{conversation_id}/messages` | Text-mode assistant turn for accessibility, diagnostics, and non-voice use |
| `POST` | `/api/v1/conversations/{conversation_id}/deletion-requests` | Creates a confirmation-bound hard-delete request |

A turn includes `role`, `content`, `status`, `started_at`, `completed_at`, and safe timing metadata. Raw model prompts, hidden policy text, and secrets are never returned.

## 7. Memory API

### 7.1 Memory Item

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Server assigned |
| `category` | enum | `preference`, `fact`, `task`, `conversation_summary` |
| `content` | string | Plain text with configured size limit |
| `source` | enum | `user`, `conversation`, `consolidation`, `import` |
| `source_reference` | object/null | Safe provenance pointer, not raw prompt data |
| `pinned` | boolean | Prevents automatic expiry |
| `expires_at` | timestamp/null | Required for expiring casual records |
| `status` | enum/null | Task-only state where applicable |
| `created_at` | timestamp | Server assigned |
| `updated_at` | timestamp | Server assigned |
| `version` | integer | Required for optimistic updates |

### 7.2 Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/memories` | Lists memories with category, pinned, status, and cursor filters |
| `GET` | `/api/v1/memories/search` | Semantic and lexical search with bounded result count |
| `POST` | `/api/v1/memories` | Creates a user-authored memory |
| `GET` | `/api/v1/memories/{memory_id}` | Returns one memory with provenance |
| `PATCH` | `/api/v1/memories/{memory_id}` | Updates content, category, pin, expiry, or task status |
| `POST` | `/api/v1/memories/{memory_id}/deletion-requests` | Creates a confirmation-bound hard-delete request |
| `POST` | `/api/v1/memory-exports` | Creates a confirmation-bound full export request |
| `GET` | `/api/v1/memory-exports/{export_id}` | Reports export status and a short-lived download link when ready |
| `DELETE` | `/api/v1/memory-exports/{export_id}` | Deletes an export artifact |

Search results include a normalized relevance score and a safe match explanation such as `pinned`, `recent`, `exact_match`, or `semantic_match`. Internal embeddings are never returned.

## 8. Capabilities and Actions API

### 8.1 Capability

A capability is a separately revocable permission such as `filesystem.read`, `filesystem.write`, `desktop.launch_app`, `calendar.read`, `messages.send`, or `calls.place`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/capabilities` | Lists registered capabilities, support state, grant state, and risk class |
| `PATCH` | `/api/v1/capabilities/{capability_id}` | Enables or disables one capability after any required confirmation |
| `GET` | `/api/v1/actions` | Lists recent action attempts and outcomes without sensitive payload bodies |
| `GET` | `/api/v1/actions/{action_id}` | Returns safe action status and audit metadata |
| `POST` | `/api/v1/actions/{action_id}/cancel` | Cancels a pending or running action when supported |

`support_state` is `available`, `degraded`, `unavailable`, or `requires_native_bridge`. Web-only unsupported Android capabilities must return `requires_native_bridge`, not a misleading disabled state.

### 8.2 Risk Classes

| Class | Examples | Default policy |
|---|---|---|
| `read_only` | Read calendar, inspect allowed file metadata | Permission check; no confirmation unless data is unusually sensitive |
| `reversible_write` | Create draft, set local preference | Permission check; confirmation configurable |
| `external_side_effect` | Send message, place call, publish data | Mandatory confirmation |
| `destructive` | Delete file/memory, overwrite data | Mandatory confirmation with exact target summary |
| `financial` | Purchase or payment | Mandatory confirmation; unsupported by default in v1 |

## 9. Confirmation API

Consequential requests do not execute on the initial request. The server returns `202 Accepted` with an `awaiting_confirmation` action and a short-lived confirmation challenge bound to the normalized action, arguments, owner session, and conversation turn.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/confirmations/{confirmation_id}` | Returns safe action summary, expiry, and status |
| `POST` | `/api/v1/confirmations/{confirmation_id}/approve` | Approves and executes the exact bound action once |
| `POST` | `/api/v1/confirmations/{confirmation_id}/reject` | Rejects the action and records the decision |

Rules:

1. Approval cannot alter action arguments.
2. Challenges are one-time and expire quickly.
3. A disconnected voice session does not imply approval.
4. Duplicate approval returns the existing terminal result and cannot execute twice.
5. A changed permission, session revocation, target version change, or policy change invalidates the challenge.
6. The confirmation summary states actor, action, target, destination, material payload summary, and irreversible effect.

The M3/M4 backend safety contract remains internal-only and exposes no confirmation HTTP endpoint. Authenticated confirmation creation, response, and consumption bind the challenge and one-time authorization to the originating owner and session, re-check session validity, and reject cross-session use. It requires a reviewed tool definition, typed server-side argument validation, an enabled capability scope, centralized deterministic risk classification, and a matching one-time confirmation authorization before any consequential adapter is invoked.

## 10. Schedules and Proactive Behavior API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/schedules` | Lists proactive jobs and next run times |
| `POST` | `/api/v1/schedules` | Creates a reminder or briefing schedule |
| `PATCH` | `/api/v1/schedules/{schedule_id}` | Updates schedule, timezone, payload, or enabled state |
| `POST` | `/api/v1/schedules/{schedule_id}/deletion-requests` | Requests confirmed deletion |
| `POST` | `/api/v1/schedules/{schedule_id}/run` | Runs a non-consequential preview now |

Schedules use an IANA timezone, retain the original local-time intent, and define behavior for missed runs. A schedule may propose a consequential action but cannot pre-authorize it.

## 11. Settings API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/settings` | Returns user-editable settings and effective capability information |
| `PATCH` | `/api/v1/settings/voice` | Updates voice provider, voice ID reference, speed, and local-mode preference |
| `PATCH` | `/api/v1/settings/listening` | Updates foreground session sensitivity and end-of-turn timing |
| `PATCH` | `/api/v1/settings/privacy` | Updates retention and cloud-use preferences |
| `PATCH` | `/api/v1/settings/appearance` | Updates theme, motion, and density preferences |

Secrets such as ElevenLabs API keys use a dedicated write-only secret endpoint and are represented only by `configured`, `last_validated_at`, and masked metadata. They are never returned to the browser.

## 12. WebSocket Handshake

1. An authenticated client calls `POST /api/v1/ws/tickets` with its existing opaque bearer session in the HTTP authorization header.
2. The endpoint returns a cryptographically random, single-use connection ticket and short expiry. Only its SHA-256 hash plus owner/session binding are retained in bounded in-memory process state.
3. The client opens `/api/v1/ws/session?ticket=<single-use-ticket>` over `wss` outside loopback. The long-lived bearer token is never placed in a URL.
4. The server atomically consumes the ticket, rechecks the originating owner session, enforces the per-session connection limit, and requires `session.hello` before activating the connection.
5. After a valid hello, the server emits `session.accepted`. M6 supports JSON text transport only; audio negotiation and binary frames are deferred.

Tickets expire within a short window, are invalid after first use, and are redacted from access logs.

## 13. WebSocket Event Envelope

Every text event contains:

| Field | Type | Meaning |
|---|---|---|
| `protocol_version` | integer | `1` for this contract |
| `event_id` | UUID | Unique event identifier |
| `session_id` | UUID | Bound authenticated owner-session identifier |
| `sequence` | integer | Monotonic sender-local sequence |
| `type` | string | Dotted event name |
| `timestamp` | timestamp | Sender time in UTC |
| `payload` | object | Event-specific fields |

M6 Pydantic schemas reject unknown envelope fields and unsupported protocol versions. Event IDs must be UUIDs, timestamps must include an offset and are normalized to UTC, messages are capped at 16 KiB by default, and sender sequence numbers are non-negative and strictly increasing.

## 14. Client-to-Server Events

| Event | Required payload | Behavior |
|---|---|---|
| `session.hello` | empty object | Required first event; activates the authenticated transport |
| `session.ping` | empty object | Application-level transport heartbeat |
| `session.close` | empty object | Requests graceful close |
| `client.ack` | `event_id` UUID | Acknowledges a server transport event |

The server must not treat silence, disconnect, repeated wake phrases, or arbitrary transcript text as implicit confirmation. Only `confirmation.respond` or the REST approval endpoint resolves a challenge.

## 15. Server-to-Client Events

| Event | Key payload | Purpose |
|---|---|---|
| `session.accepted` | connection ID, protocol version | Confirms active authenticated transport |
| `session.pong` | referenced client event ID | Responds to `session.ping` |
| `session.error` | stable code, safe message | Reports protocol/transport failure without internals |
| `session.closing` | safe reason | Announces graceful close |
| `server.ack` | referenced client event ID | Confirms `client.ack` |

## 16. WebSocket Ordering and Recovery

- The lifecycle is `connecting → authenticating → active → closing → closed`, with `failed` for an isolated transport error.
- `session.hello` is required within 10 seconds by default; events before hello, malformed events, unsupported types, invalid sequence, oversized JSON, and rate-limit violations receive a safe `session.error` then close.
- Every received event rechecks session validity; idle checks run at a bounded interval and close revoked/expired sessions. Idle connections close after 120 seconds by default.
- Tickets are one use even when a failed handshake follows exchange. The in-memory ticket and connection registries are process-local; a future multi-process deployment requires a shared reviewed backend.
- M8 adds only the bounded `transcript.*` event family described in section 20. Assistant, confirmation, tool, and response event families remain reserved.

## 17. Audio Contract

M6 rejects binary frames and implements no audio, speech, transcript, agent, tool, confirmation, or TTS payload. Audio contracts begin no earlier than M7.

M7 extends the authenticated transport with foreground-only audio control events: `audio.session.start`, `audio.format`, `audio.session.stop`, `audio.session.cancel`, and `audio.flush`. After `session.hello`, one active audio session per connection may negotiate only PCM signed 16-bit little-endian, mono, 16 kHz, 20 ms frames (640 payload bytes). Binary frames are exactly 664 bytes: `TAR1` + audio-session UUID + uint32 monotonic sequence + PCM payload. Frames are rejected before processing unless the connection owner session is active, the audio session is negotiated, the UUID matches, and the sequence is strictly next. Raw audio is transient, never buffered, logged, persisted, or returned. A session is capped at 60 seconds and an utterance at 30 seconds; `audio.flush` ends and clears the active session deterministically. Server events are `audio.session.accepted`, `audio.session.stopped`, `vad.speech.started`, `vad.speech.ended`, `vad.turn.completed`, and smoothed/throttled `audio.level` (at most 10 Hz). M8 consumes completed VAD turns only to emit the bounded transcript events below; it does not emit assistant or tool events.

## 18. Rate, Size, and Timeout Policy

Limits are configuration values published where the client needs them. The contract requires bounded values for:

- login attempts and session creation;
- active WebSockets per owner session;
- JSON message size (16 KiB default) and event rate (30 events/second default);
- synchronous transport delivery only: M6 creates no unbounded outgoing or audio queue;
- memory content and page size;
- export frequency and artifact lifetime;
- model/tool iteration count;
- provider and tool timeouts.

Ticket endpoint failures use the standard HTTP error envelope. WebSocket failures use `session.error` and safe close codes: `4401` authentication/session invalidation, `1002` protocol error, `1008` policy/hello/rate violation, `1009` message too large, `1013` connection limit, and `1011` unexpected transport failure.

## 19. Compatibility and Contract Governance

- FastAPI's generated OpenAPI document is checked against the reviewed v1 contract.
- WebSocket event schemas are maintained as versioned JSON Schema fixtures under `contracts/websocket` when implementation begins.
- Removing or changing the meaning of a field requires a new major version.
- Adding optional response fields or new event types is backward-compatible.
- Frontend and backend contract tests must run before either side upgrades independently.
- Security-sensitive schema changes require review against `SECURITY_MODEL.md`.

## 20. M8 Transcript Contract

M8 is server-side STT only. Every transcript event uses the existing server envelope: `session_id`, monotonic server `sequence`, `type`, and `payload`. The server supplies `transcription_id`, `audio_session_id`, and `turn_id`; client payloads cannot override the authenticated owner, session, or connection binding.

| Event | Payload | Contract |
|---|---|---|
| `transcript.started` | transcription, audio-session, and turn IDs | Accepted job has begun preparation. |
| `transcript.partial` | IDs, `text`, `sequence`, `is_final: false` | Ordered provisional text. The deterministic fake provider may emit these; faster-whisper does not. |
| `transcript.final` | IDs, `text`, `language`, optional `confidence`, `is_final: true` | Exactly one successful terminal result. Faster-whisper is final-only. |
| `transcript.canceled` | IDs | Terminal cancellation. No final event follows. |
| `transcript.error` | IDs and stable `code` | Terminal safe failure; no provider detail, model path, audio, token, or stack trace is returned. |

The normal successful ordering is `transcript.started`, zero or more ordered `transcript.partial` events, then `transcript.final`. A canceled or failed job terminates with `transcript.canceled` or `transcript.error` instead. Late results after cancellation or timeout are discarded.

Clients may send `transcript.cancel` with exactly `{"transcription_id":"UUID"}`. Cancellation succeeds only for the same authenticated owner/session/connection that created the job. Invalid, foreign, terminal, or malformed cancellation requests receive the existing safe transport error path.

The registry rejects work before registration with stable safe codes including `audio_too_short`, `queue_full`, `audio_too_long`, `connection_job_limit`, and `session_job_limit`. Timed-out jobs report `transcription_timeout`; model, malformed-provider, and other provider failures report `provider_failure`. The in-process limits cover total pending jobs, concurrent execution, jobs per connection, jobs per session, audio size, and timeout.

Transcript delivery is isolated by authenticated owner, session, and connection. Jobs are canceled when that connection closes or its session becomes invalid. M8 neither persists raw audio nor transcript text.

Authenticated `GET /api/v1/status` includes a safe `stt` object: configured/required flags, provider label, provider state/readiness/model-loaded state, language and partial modes, queued and active job counts, and configured queue/concurrency limits. STT health never loads a model, transcribes audio, downloads a model, or accesses the network. An unavailable optional provider degrades status but leaves readiness successful; an unavailable required provider makes readiness fail.
