# Tara Security Model

## 1. Security Objective

Tara holds private speech, memory, credentials, personal context, and the ability to cause real-world side effects. The security objective is to ensure that only the single authenticated owner can access that data or authorize capabilities, and that no model output, misheard speech, network peer, or compromised content can bypass deterministic safety controls.

Security is layered:

1. Tailscale limits network reachability.
2. Application authentication identifies and maintains the owner session.
3. Scoped capabilities authorize each class of tool.
4. Server-side validation constrains every tool argument.
5. Confirmation gating authorizes each consequential action instance.
6. Audit events make security-relevant decisions reviewable.

No layer substitutes for another.

## 2. Scope and Assumptions

- v1 has one owner, not multiple users or roles.
- The backend runs on a trusted, owner-controlled PC or home server.
- The web application is reachable through private Tailscale HTTPS and is not publicly exposed.
- The browser device may be lost or shared; sessions must be revocable.
- Ollama, faster-whisper, Piper, SQLite, and ChromaDB are local services/data.
- ElevenLabs is an optional cloud processor for synthesized text only when enabled.
- Standard browser limitations prevent native Android service permissions; no hidden native bridge is assumed.
- Speaker verification is post-v1 and cannot replace explicit confirmation.

## 3. Protected Assets

| Asset | Sensitivity | Required protection |
|---|---|---|
| Owner credentials and sessions | Critical | Strong hash, secure cookies, rotation, revocation, no logs |
| Provider/API secrets | Critical | Server-only storage, least-privilege file access, write-only UI |
| Confirmation challenges | Critical | Short-lived, one-time, action-bound, session-bound |
| Tool permissions | Critical | Default deny, independent grants, audited changes |
| Memory and conversation data | High | Encryption at rest, retention, export control, hard delete |
| Raw audio and transcripts | High | Transient by default, redacted logs, explicit diagnostics consent |
| Filesystem and desktop tools | High | Allowlisted roots/actions, canonical paths, no arbitrary command shell |
| Audit trail | High | Append-oriented, content-minimized, access-controlled |
| Chroma embeddings/index | High | Same storage protections as source data, rebuildable deletion |
| Models and configuration | Medium/High | Pinned identifiers, integrity and provenance checks |
| Service metadata | Medium | Authenticated detailed status, minimal public health output |

## 4. Trust Boundaries

### 4.1 Browser Boundary

All browser input is untrusted, including typed text, audio, filenames, IDs, WebSocket event order, client timestamps, and visibility claims. Browser code never receives provider secrets or direct database access.

### 4.2 Network Boundary

Tailscale peers are not automatically trusted application users. All requests require application authentication. HTTPS and `wss` are mandatory beyond loopback, and origin checks apply to HTTP and WebSocket connections.

### 4.3 Model Boundary

Model output is untrusted advice. Tool names, arguments, memory proposals, and confidence claims are validated against server-owned schemas and policies. The model cannot grant itself permissions, mark an action safe, or approve confirmation.

### 4.4 Tool Boundary

Tools are privileged adapters. Each declares one capability, risk class, argument schema, timeout, idempotency behavior, and safe audit summary. Tools cannot call other tools directly or widen their own allowed resource scope.

### 4.5 Storage Boundary

SQLite is authoritative. ChromaDB is a derived index that may contain sensitive semantic representations but never determines deletion or authorization state. Exports and diagnostics are separate temporary artifacts with expiration.

### 4.6 Cloud Provider Boundary

When ElevenLabs is enabled, only the minimum text and voice configuration needed for TTS is sent. Memory context, tool credentials, hidden prompts, raw audio, and unrelated transcript history are excluded. The UI must disclose active cloud processing.

## 5. Threat Model

| Threat | Example | Primary controls |
|---|---|---|
| Unauthorized network access | Another Tailscale peer reaches the backend | Application login, secure sessions, per-request auth, private ACLs |
| Session theft | Cookie copied from a lost device | Secure/HttpOnly cookies, short lifetime, rotation, revocation, device list |
| CSRF | Malicious page triggers a destructive request | SameSite cookies, CSRF token, origin validation, confirmation gate |
| WebSocket hijack/replay | Ticket reused or cross-origin socket opened | One-time short ticket, origin check, session binding, replay rejection |
| Voice misrecognition | “Hey Tara” or “yes” falsely detected | Explicit active session, exact challenge, no transcript-only implicit approval |
| Prompt injection | File/web content instructs the model to send data | Untrusted-content delimiters, least privilege, deterministic policy, confirmation |
| Tool argument injection | Crafted path escapes allowed directory | Typed schema, canonicalization, allowlisted roots, symlink policy |
| Confused deputy | Model uses a granted read tool for unrelated sensitive data | Per-tool scope, purpose-bound context, target validation, audit |
| Duplicate side effect | Retry sends the same message twice | Idempotency keys, one-time action IDs, provider reconciliation |
| Unknown side-effect outcome | Tool times out after sending | No blind retry, uncertain state, reconciliation before another attempt |
| Data remanence | Deleted memory remains in vector index/export | Outbox deletion, index verification, export cleanup, backup policy disclosure |
| Sensitive logs | Transcript or token enters structured logs | Field allowlist, redaction, content-free audit summaries, tests |
| Dependency compromise | Malicious model/plugin/provider package | Pinned dependencies/models, provenance, minimal privileges, update review |
| Denial of service | Oversized audio frames or runaway model/tool loop | Frame limits, backpressure, bounded iterations, timeouts, quotas |
| Scheduler abuse | Proactive job sends data unattended | Scheduler may propose only; consequential execution still requires confirmation |

## 6. Authentication Architecture

### 6.1 Bootstrap

- Bootstrap is permitted only when no owner record exists.
- It is accepted only from loopback or with a high-entropy one-time bootstrap secret presented out of band.
- Bootstrap creates the owner, hashes the passphrase with a memory-hard password hash, creates the first device session, and permanently closes normal bootstrap.
- Recovery is an offline administrative procedure and is never an unauthenticated web endpoint.

### 6.2 Sessions

- Access and refresh credentials are signed opaque session references in `HttpOnly`, `Secure`, `SameSite=Strict` cookies.
- Access sessions are short-lived; refresh rotates both credentials and invalidates the previous refresh value.
- Session records include device label, creation, last use, expiry, rotation lineage, and revocation.
- Password/security changes revoke all other sessions.
- Login attempts are rate-limited and audited without recording the submitted credential.
- Session cookies are scoped as narrowly as deployment routing allows.

### 6.3 CSRF and Origin

- Every state-changing cookie-authenticated request requires a CSRF token and same-origin validation.
- WebSocket upgrades require an allowed `Origin` and a single-use ticket minted over authenticated HTTPS.
- CORS is disabled in same-origin deployment. Any future separate origin must be an explicit allowlist, never wildcarded with credentials.

## 7. Authorization and Capability Policy

Authentication answers “who”; capabilities answer “may this class of action be attempted.”

- Default state is denied.
- Each capability is independently granted and revoked.
- Grants include scope, source, creation time, and optional expiry.
- A disabled, unavailable, or native-bridge-only capability cannot be invoked by model output.
- Changing a grant invalidates pending confirmation challenges that depend on it.
- Read and write capabilities remain separate even for the same integration.
- Financial actions are unsupported by default in v1 even if a generic tool mechanism could express them.

## 8. Confirmation-Gating Policy

### 8.1 Mandatory Classes

Explicit confirmation is required for any action that:

- sends or publishes content;
- places a call;
- spends or commits money;
- deletes or irreversibly overwrites data;
- exports sensitive data;
- changes a security control or broadens a capability;
- performs an externally visible write whose outcome affects another person or system.

### 8.2 Server-Side State Machine

```text
proposed
  -> rejected_by_policy
  -> awaiting_confirmation
       -> rejected
       -> expired
       -> invalidated
       -> approved
            -> executing
                 -> succeeded
                 -> failed
                 -> uncertain
```

Only `approved` can enter `executing`. The transition is atomic and one-time.

### 8.3 Challenge Binding

A confirmation challenge is cryptographically random and bound to:

- owner and authenticated session;
- conversation and turn;
- action/tool identifier and schema version;
- canonicalized arguments and target versions;
- capability and policy version;
- safe human-readable summary;
- creation and expiry time;
- idempotency key.

Approval executes exactly the bound action. Any argument or target change requires a new challenge.

The implementation classifies and gates actions in server-owned code before tool dispatch; no model output can influence the decision. An approval yields a short-lived authorization bound to the canonical tool-request hash. The executor atomically consumes that authorization before invoking a tool, so it cannot be replayed, reused, or substituted for changed arguments. Only a recognized affirmative response within an active challenge can approve it; negative responses reject it and ambiguous responses remain unapproved.

### 8.4 Voice Confirmation

Speech recognition may populate a proposed approve/reject response, but only an active, unexpired challenge is eligible. Generic “yes” outside that state has no authority. Disconnect, silence, wake detection, model inference, or proactive schedule execution never counts as confirmation.

## 9. Tool Security

### 9.1 Registration

Every tool registration specifies:

- unique name and version;
- typed input and output schema;
- required capability and target scope;
- risk classification and confirmation rule;
- timeout and cancellation support;
- idempotent/non-idempotent behavior;
- safe log fields and redaction fields;
- availability requirements.

Unregistered tools cannot be invoked.

### 9.2 Filesystem Controls

- Resolve paths to canonical absolute targets before policy checks.
- Restrict access to configured allowlisted roots.
- Reject traversal, device paths, network paths unless explicitly allowed, and symlink/junction escapes.
- Separate read, create, overwrite, move, and delete permissions.
- Show exact canonical target in destructive confirmations.
- Do not expose a generic shell-command tool in v1.

### 9.3 External Integrations

- Credentials are scoped and stored server-side.
- Tool output and third-party content are untrusted before model reuse.
- Consequential calls use stable idempotency identifiers where the provider supports them.
- A timeout after dispatch becomes `uncertain`; reconciliation precedes retry.
- Unsupported phone-native integrations remain registered only as unavailable capability metadata, not executable stubs.

## 10. AI and Prompt Security

- System policy and tool definitions are assembled server-side and not accepted from the client.
- Retrieved memories and external/tool content are marked as data, not instructions.
- Context retrieval is bounded by owner, category, retention state, and relevance.
- The model sees only tools whose capabilities are available, but server policy still re-checks every call.
- Model-selected URLs, file paths, recipients, and payloads are normalized and validated.
- Tool-loop count, token/context budget, and wall time are bounded.
- Secrets are never inserted into model context.
- Model responses cannot modify audit records, confirmation policy, or access controls.

## 11. WebSocket Security

- Use `wss` outside loopback.
- Accept a single-use, short-lived ticket; redact it from all logs.
- Verify authenticated session, allowed origin, ticket binding, protocol version, and connection count.
- Enforce maximum text frame, binary frame, buffered audio, utterance, and idle durations.
- Validate event sequence and state transitions; reject binary audio without an active negotiated stream.
- On disconnect, stop capture processing, cancel output, and expire pending voice confirmation challenges.
- Reconnection never replays approval or resumes microphone capture automatically.
- Raw audio remains transient unless separately consented diagnostics are active.

## 12. Data Protection

### 12.1 At Rest

- Use SQLCipher-compatible encrypted SQLite before sensitive personal, financial, or health-adjacent data is accepted beyond development fixtures.
- Store the encryption key separately from the database with OS-level access controls.
- Protect ChromaDB, logs, exports, and backups with equivalent filesystem permissions and encrypted-volume expectations.
- Do not treat embedding vectors as anonymous.
- Keep secret material outside source control and browser-readable configuration.

### 12.2 In Transit

- Use HTTPS/`wss` through Tailscale.
- No raw unauthenticated LAN HTTP.
- ElevenLabs requests use TLS and send only the text needed for synthesis.
- Cloud TTS can be disabled globally through local mode.

### 12.3 Retention, Export, and Delete

- Preferences persist until changed/deleted; completed tasks follow configured expiry; casual conversation expires after 30 days unless pinned.
- Automatic jobs log counts and IDs, not deleted content.
- Export requires confirmation, is encrypted or strongly access-controlled at rest, uses a short-lived download, and is removed after expiry.
- Hard delete removes authoritative rows, semantic index entries, caches, and temporary exports.
- Existing offline backups may retain prior data until their documented retention expires; the UI must explain this limit accurately.

## 13. Secrets Management

- Provider secrets are accepted through dedicated write-only settings operations.
- The UI shows only configured state and masked metadata.
- Secrets use OS credential storage where available or a permission-restricted encrypted secret file.
- Separate session signing, database encryption, bootstrap, and provider secrets.
- Rotation invalidates dependent sessions/tickets where relevant.
- Diagnostics and exception serialization explicitly redact secret field names and authorization headers.

## 14. Logging, Audit, and Privacy

Operational logs use an allowlist of safe fields. Audit records capture who, what capability, what safe target summary, decision, result, timestamp, and correlation IDs.

Do not log by default:

- cookies, tokens, keys, passphrases, or authorization headers;
- raw audio or voiceprints;
- complete transcripts, prompts, model context, or model output;
- memory content or embeddings;
- message bodies, file contents, or contact details;
- full third-party requests/responses.

Audit events must survive ordinary operational log rotation but remain bounded by a documented retention policy. Exporting diagnostics or audit information is itself a confirmed sensitive action.

## 15. Deployment Hardening

- Bind services to loopback or a private interface; expose only the intended same-origin HTTPS route through Tailscale.
- Run Next.js, FastAPI, Ollama, and supporting processes under dedicated least-privilege accounts where practical.
- Run one scheduler leader.
- Restrict data and secret directories to the service owner.
- Pin dependencies and model identifiers; review updates before rollout.
- Apply Alembic migrations only after a backup and compatibility check.
- Disable debug mode and interactive API documentation in production unless authenticated and explicitly enabled.
- Prevent public search indexing and public cache/CDN storage of the private app.
- Test restore and session revocation during release readiness.

## 16. Security Verification Gates

Release is blocked unless tests demonstrate:

1. Unauthenticated REST and WebSocket access is denied.
2. CSRF and cross-origin WebSocket attempts fail.
3. Replayed/expired WebSocket tickets fail.
4. Disabled capabilities cannot execute despite model proposals.
5. Consequential actions cannot execute before confirmation.
6. Confirmation cannot be replayed or applied after argument changes.
7. Path traversal and symlink/junction escapes are denied.
8. Logs and diagnostics contain no configured sensitive fixtures.
9. Hard delete removes SQLite and Chroma references.
10. ElevenLabs receives no unrelated context and local mode produces no cloud TTS request.

## 17. Incident Response

If suspicious behavior occurs:

1. Disable affected capabilities and cloud egress.
2. Revoke all sessions and rotate session-signing/bootstrap secrets as applicable.
3. Stop scheduler execution and consequential tools while preserving evidence.
4. Export redacted diagnostics and content-minimized audit events.
5. Determine whether any action outcome is uncertain and reconcile with the external system.
6. Restore from a verified backup only after identifying the failure boundary.
7. Record the incident's architectural lesson in `DECISIONS.md` or `RISKS.md` before re-enabling the capability.
