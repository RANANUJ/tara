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
| `GET` | `/api/v1/health/ready` | Private network | Readiness for normal requests; minimal aggregate result |
| `GET` | `/api/v1/status` | Yes | User-facing status of backend, models, speech, stores, scheduler, and last voice turn |
| `POST` | `/api/v1/diagnostics/exports` | Yes + CSRF | Creates a redacted diagnostics export after explicit confirmation |

Authenticated status entries contain `component`, `state`, `last_success_at`, `latency_ms`, `error_code`, and a user-safe `message`. Secrets, host paths, model prompts, and transcript content are excluded.

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

1. The authenticated client requests a single-use ticket from `/api/v1/auth/websocket-ticket`.
2. The client opens `/ws/v1/assistant?ticket=<opaque-ticket>` over `wss`.
3. The server verifies origin, ticket expiry, single-use state, session validity, and connection limits.
4. The server sends `session.ready` containing protocol version, heartbeat interval, maximum frame size, input/output audio options, and a new voice-session ID.
5. The client selects a supported audio format in `audio.configure` before sending binary frames.

Tickets expire within a short window, are invalid after first use, and are redacted from access logs.

## 13. WebSocket Event Envelope

Every text event contains:

| Field | Type | Meaning |
|---|---|---|
| `protocol_version` | string | `1.0` for this contract |
| `event_id` | UUID | Unique event identifier |
| `session_id` | UUID | Current voice-session identifier |
| `sequence` | integer | Monotonic sender-local sequence |
| `type` | string | Dotted event name |
| `timestamp` | timestamp | Sender time in UTC |
| `payload` | object | Event-specific fields |

The receiver ignores additive payload fields it does not understand but rejects an unsupported major protocol version.

## 14. Client-to-Server Events

| Event | Required payload | Behavior |
|---|---|---|
| `audio.configure` | input/output codec, sample rate, channel count | Negotiates audio before streaming |
| `conversation.attach` | conversation ID or `new` | Binds the live session to durable history |
| `listening.start` | device ID, locale | Begins an explicit foreground listening session |
| `audio.input.start` | stream ID | Opens the sole active input stream |
| Binary frame | negotiated audio bytes | Belongs to the active input stream |
| `audio.input.end` | stream ID, reason | Closes input and requests final transcription |
| `assistant.interrupt` | active turn ID | Cancels generation and output for barge-in |
| `confirmation.respond` | confirmation ID, `approve` or `reject` | Resolves a live challenge through the same policy service as REST |
| `turn.text` | text, locale | Starts a non-audio turn on the live session |
| `client.visibility` | `visible` or `hidden` | Allows honest handling of browser suspension risk |
| `ping` | nonce | Application heartbeat |

The server must not treat silence, disconnect, repeated wake phrases, or arbitrary transcript text as implicit confirmation. Only `confirmation.respond` or the REST approval endpoint resolves a challenge.

## 15. Server-to-Client Events

| Event | Key payload | Purpose |
|---|---|---|
| `session.ready` | protocol and audio limits | Confirms connection readiness |
| `assistant.state` | state, reason, turn ID | Authoritative Guide Star state |
| `transcript.partial` | turn ID, text, stability | Replaceable live user transcript |
| `transcript.final` | turn ID, text | Durable user transcript candidate |
| `response.text.delta` | turn ID, delta | Incremental assistant text |
| `response.text.final` | turn ID, text | Final assistant text |
| `audio.output.start` | stream ID, codec | Announces following binary TTS frames |
| Binary frame | negotiated audio bytes | Belongs to active output stream |
| `audio.output.end` | stream ID, reason | Ends output cleanly |
| `tool.proposed` | action ID, tool, safe summary | Shows planned tool work |
| `tool.started` | action ID | Reports execution start |
| `tool.completed` | action ID, safe result summary | Reports successful completion |
| `tool.failed` | action ID, error code, retryable | Reports safe failure |
| `confirmation.required` | confirmation ID, summary, expiry | Requests explicit user decision |
| `memory.changed` | memory ID, change type | Invalidates/updates client query state |
| `service.degraded` | component, code, fallback | Announces a non-fatal dependency issue |
| `error` | stable code, message, recoverable | Reports protocol or turn error |
| `pong` | nonce | Heartbeat response |

## 16. WebSocket Ordering and Recovery

- Sequence numbers detect missing or duplicated control events.
- One input and one output audio stream may exist at a time per socket.
- A new `audio.input.start` while Tara is speaking implies barge-in only if it follows an explicit interrupt or negotiated automatic-barge-in setting.
- The client applies `transcript.partial` by replacement, not concatenation; `response.text.delta` is append-only for the matching turn.
- Terminal turn states are `completed`, `cancelled`, and `failed`.
- On reconnect, the client refetches durable conversation and status through REST. It does not replay binary audio or approval events.
- The server may resume text display for a durable completed turn but starts live state at `idle`.

## 17. Audio Contract

- The browser offers supported capture formats; the server selects one in `session.ready`/`audio.configure`.
- The preferred low-latency input is mono PCM at the pipeline's configured rate; compressed Opus is permitted when bandwidth requires it and server decoding is available.
- Frame duration, maximum buffered duration, and maximum utterance length are advertised by the server.
- Client timestamps are hints only; server receive order and sequence are authoritative.
- Raw audio is transient by default and is not stored. An explicit diagnostics mode must be time-limited, visibly enabled, and separately consented.
- Output audio includes stream IDs and is cancelled on barge-in. Stale frames for cancelled streams are discarded.

## 18. Rate, Size, and Timeout Policy

Limits are configuration values published where the client needs them. The contract requires bounded values for:

- login attempts and session creation;
- active WebSockets per owner session;
- JSON and binary frame size;
- queued audio duration;
- utterance duration;
- transcript and text-message length;
- memory content and page size;
- export frequency and artifact lifetime;
- model/tool iteration count;
- provider and tool timeouts.

Limit failures use `429` or a WebSocket `error` event with `retry_after_ms` where retry is safe.

## 19. Compatibility and Contract Governance

- FastAPI's generated OpenAPI document is checked against the reviewed v1 contract.
- WebSocket event schemas are maintained as versioned JSON Schema fixtures under `contracts/websocket` when implementation begins.
- Removing or changing the meaning of a field requires a new major version.
- Adding optional response fields or new event types is backward-compatible.
- Frontend and backend contract tests must run before either side upgrades independently.
- Security-sensitive schema changes require review against `SECURITY_MODEL.md`.
