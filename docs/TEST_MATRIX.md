# Tara Test Matrix

## 1. Test Strategy

Testing follows the architecture boundaries and starts with the narrowest deterministic layer:

1. Unit tests for policy, state, transformation, and UI behavior.
2. Component tests for responsive and accessibility behavior.
3. Integration tests with temporary SQLite/Chroma and fake providers.
4. Contract tests for REST/OpenAPI and versioned WebSocket events.
5. End-to-end tests for complete owner workflows.
6. Security, performance, recovery, and manual device tests before release.

No test may send a real message, place a call, delete owner data, or incur cloud cost unless it is explicitly tagged, isolated, and manually authorized. Consequential automated tests use a fake tool that records intent without external effects.

## 2. Planned Test Tooling

| Area | Planned tools |
|---|---|
| Frontend unit/component | Vitest, React Testing Library, user-event |
| Frontend accessibility | axe-core plus keyboard/screen-reader manual checks |
| Browser end-to-end | Playwright with compact and expanded projects |
| Backend unit/integration | pytest, pytest-asyncio, HTTPX/FastAPI test client |
| Property/state tests | Hypothesis where confirmation, retention, and path-policy state spaces benefit |
| Database | Temporary SQLite databases, Alembic migration fixtures, isolated Chroma directories |
| AI/voice | Deterministic provider fakes and versioned WAV/text fixtures; optional tagged local-model tests |
| Contract | OpenAPI compatibility checks and JSON Schema WebSocket fixtures |
| Performance | Timestamped pipeline probes with warmed and cold profiles |

## 3. Test Environments

| Environment | Purpose | Data policy |
|---|---|---|
| Unit | Pure modules and components | Synthetic only |
| Integration | FastAPI + temporary stores + fake providers | Synthetic only |
| Local AI | Real Ollama/faster-whisper/Piper | Public test fixtures only |
| Cloud TTS opt-in | ElevenLabs smoke/latency | Synthetic text, tagged, cost-capped |
| Browser desktop | Chromium plus one additional supported engine | Synthetic owner |
| Browser mobile | Real Android/iOS browsers or devices where supported | Synthetic owner |
| Private deployment | Tailscale HTTPS production-like host | Synthetic pre-release data |

## 4. Foundation and Persistence

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| FND-001 | CI | Frontend clean install and build | Pinned install completes; build exits successfully |
| FND-002 | CI | Backend clean environment install | Python 3.12 environment resolves and imports cleanly |
| FND-003 | CI | Static quality commands | Type-check, lint, and formatting checks pass |
| FND-004 | CI | Test isolation | Tests write only to declared temporary paths and leave no repository data |
| DB-001 | Integration | Empty database upgrade | Alembic upgrades from empty to head |
| DB-002 | Integration | Idempotent current migration | Upgrade at head performs no destructive duplicate work |
| DB-003 | Integration | Transaction rollback | Injected failure leaves no partial domain records |
| DB-004 | Integration | Optimistic concurrency | Stale resource version returns conflict without overwrite |
| DB-005 | Integration | Invalid database path/key | Startup fails with safe actionable error |
| DB-006 | Integration | Memory/index outbox commit | Memory and outbox row commit atomically |
| DB-007 | Integration | Chroma write failure | SQLite remains committed and outbox remains retryable |
| DB-008 | Integration | Outbox replay | Repeated upsert/delete is idempotent |
| DB-009 | Integration | Index rebuild | Rebuild produces current SQLite-backed searchable IDs only |

## 5. UI, Responsive, and Accessibility

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| UI-001 | Visual | Guide Star Idle | Matches token/state specification in both shells |
| UI-002 | Visual | Guide Star Listening | Signal animation responds to bounded amplitude |
| UI-003 | Visual | Guide Star Thinking | Inward/rotation treatment is restrained and stable |
| UI-004 | Visual | Guide Star Speaking | Output envelope drives waves and stops on cancellation |
| UI-005 | Visual | Confirming/Error/Offline | Each state is distinct without color alone |
| UI-006 | Component | Compact navigation | Four destinations remain reachable with safe-area padding |
| UI-007 | Component | Expanded navigation | Sidebar persists and identifies active route |
| UI-008 | Component | Compact transcript sheet | Sheet opens, resizes, and closes without hiding critical controls |
| UI-009 | Component | Responsive transition | State and route survive width change without duplication |
| UI-010 | Component | Async states | Every core screen renders loading, empty, error, and offline variants |
| A11Y-001 | Automated | Semantic landmarks/headings | No critical axe violations; hierarchy is valid |
| A11Y-002 | Component | Keyboard navigation | All interactive controls reachable in logical order |
| A11Y-003 | Component | Focus management | Dialog/sheet/confirmation focus enters and returns predictably |
| A11Y-004 | Visual | Contrast and target size | WCAG 2.2 AA contrast and minimum target sizes pass |
| A11Y-005 | Component | Reduced motion | Continuous/spatial animation is disabled while state remains clear |
| A11Y-006 | E2E | Text-only assistant path | Complete assistant turn works without microphone/audio playback |

## 6. Authentication and API Framework

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| AUTH-001 | Integration | First bootstrap | Owner/session created once from permitted context |
| AUTH-002 | Security | Second bootstrap | Rejected without revealing sensitive owner state |
| AUTH-003 | Integration | Valid login | Secure cookies set and private API becomes available |
| AUTH-004 | Security | Invalid login/rate limit | Failure is generic, audited, and throttled |
| AUTH-005 | Integration | Refresh rotation | New credentials work; prior refresh cannot be reused |
| AUTH-006 | Integration | Logout | Current session is revoked and cookies cleared |
| AUTH-007 | Integration | Revoke other device | Target session fails on next request/socket attempt |
| AUTH-008 | Security | Expired access session | Refresh path works only with valid rotating refresh credential |
| AUTH-009 | Security | Missing/invalid CSRF | State-changing request is rejected |
| AUTH-010 | Security | Cross-origin request | Origin policy rejects credentialed mutation |
| AUTH-011 | Unit | Password storage | Only approved memory-hard hash and metadata are persisted |
| AUTH-012 | Security | Credential redaction | No passphrase, token, cookie, or signing secret appears in logs |
| API-001 | Contract | Problem response | Required stable fields and correlation ID are present |
| API-002 | Contract | Request validation | Invalid fields return deterministic field errors |
| API-003 | Contract | Cursor pagination | Stable ordering; no duplicate/omitted records across pages |
| API-004 | Integration | Idempotency key | Retried mutation returns one logical outcome |
| API-005 | Contract | Version compatibility | Reviewed OpenAPI changes are backward-compatible within v1 |

## 7. Observability and WebSocket

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| OBS-001 | Integration | Request correlation | HTTP request, service work, and response share request ID |
| OBS-002 | Integration | Turn correlation | WebSocket, STT, model, TTS, and tool timing share turn ID |
| OBS-003 | Security | Log redaction fixture | Sensitive fixture values are absent from all log outputs |
| OBS-004 | Integration | Dependency status | Each dependency reports ready/degraded/unavailable accurately |
| OBS-005 | Integration | Metrics timing | Required latency metrics are emitted once per completed turn |
| OBS-006 | Integration | Audit separation | Security events are recorded without sensitive payload content |
| OBS-007 | Integration | M5 readiness registry | Required failures return `503`; optional degradation remains ready with safe latency/diagnostic fields |
| OBS-008 | Security | M5 error/correlation envelope | Validation, auth, and not-found failures use safe stable codes and bounded correlation IDs |
| OBS-009 | Integration | M5 authenticated status | Owner status exposes only implemented features and no secret/deployment values |
| WS-M6-001 | Integration | Single-use ticket handshake | Authenticated ticket reaches `session.accepted` exactly once without bearer URL credentials |
| WS-M6-002 | Security | Ticket/session invalidation | Expired, revoked, malformed, reused, or cross-session ticket exchange is rejected safely |
| WS-M6-003 | Contract | JSON transport envelope | Strict v1 hello/ping/close/ack schemas enforce UUID, UTC, size, and sequence rules |
| WS-M6-004 | Security | Transport limits and logging | Connection limits, idle/hello timeout, payload limits, and redacted lifecycle logs remain bounded |
| WS-001 | Contract | Valid ticket handshake | `session.ready` follows authenticated one-time ticket use |
| WS-002 | Security | Missing/expired ticket | Upgrade is rejected |
| WS-003 | Security | Ticket replay | Second use is rejected |
| WS-004 | Security | Wrong origin | Upgrade is rejected despite valid session |
| WS-005 | Contract | Event envelope | Required version/ID/session/sequence/time/payload fields validate |
| WS-006 | Contract | Sequence violation | Duplicate/out-of-order control event is handled deterministically |
| WS-007 | Integration | Heartbeat timeout | Dead connection closes and runtime state recovers |
| WS-008 | Security | Oversized text/binary frame | Frame is rejected without process instability |
| WS-009 | Integration | Reconnect | New socket starts Idle and REST durable state remains consistent |
| WS-010 | Security | Reconnect with pending confirmation | Challenge is not silently approved or resumed |
| WS-011 | Integration | Backpressure | Excess queued audio yields bounded recoverable error |
| WS-012 | Contract | Unsupported protocol/codec | Explicit protocol error precedes clean close |

## 8. Voice, STT, and TTS

### M7 Audit Evidence

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| M7-AUD-001 | Unit | PCM format and framing | Only 16 kHz, mono, signed PCM16 little-endian 20 ms frames; malformed, oversized, mismatched, and invalid-sequence frames are rejected |
| M7-AUD-002 | Unit | VAD lifecycle | Deterministic fixtures prove minimum speech, single start/end, silence completion, reset, failure safety, and duration limits without downloads |
| M7-AUD-003 | Integration | Authenticated audio transport | Pre-hello/pre-start frames, mismatched sessions, invalid negotiation, revocation, and raw-payload leakage are rejected safely |
| M7-AUD-004 | Unit | Foreground browser capture | Capture starts only through the explicit public method; permission errors, cleanup, page hiding, conversion, and framing are deterministic |

M7 uses a deterministic local VAD test implementation only. Silero, STT, TTS, a browser AudioWorklet streaming pipeline, and final Listen UI are not implemented or claimed; real browser device-removal behavior remains a manual test for the future capture integration.

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| VOICE-001 | Component | Microphone grant | Selected device begins negotiated capture after explicit action |
| VOICE-002 | Component | Microphone denial | Clear explanation and retry/settings action; no reconnect loop |
| VOICE-003 | Integration | Audio negotiation | Client/server agree on supported codec/rate/channels |
| VOICE-004 | Integration | Speech start | Silero fixture emits one authoritative start event |
| VOICE-005 | Integration | End-of-turn silence | Configured 700 ms–1 s range ends turn as expected |
| VOICE-006 | Integration | Noise-only fixture | No false completed utterance above allowed threshold |
| VOICE-007 | Integration | Maximum utterance | Capture ends safely with user-visible limit message |
| VOICE-008 | Component | Device removal | Active input stops and UI offers device recovery |
| VOICE-009 | E2E | Hidden/suspended page | Session reports limitation and never claims background wake support |
| VOICE-010 | E2E | Barge-in | Speaking stops and new Listening turn starts |
| VOICE-011 | Integration | Cancel propagation | Old LLM/TTS work receives cancellation |
| VOICE-012 | Integration | Stale output frame | Cancelled stream audio is discarded |
| VOICE-013 | E2E | Rapid repeated interruption | State remains ordered and no overlapping audio plays |
| VOICE-014 | E2E | Voice loop recovery | Error returns to Idle and next turn succeeds |
| STT-001 | Local AI | Clean speech fixture | Final transcript matches expected tolerance |
| STT-002 | Local AI | Accent/noise fixture set | Accuracy meets documented fixture threshold |
| STT-003 | Integration | Partial replacement | Partial text replaces prior hypothesis, not duplicates it |
| STT-004 | Integration | Final ordering | Final transcript precedes model turn start |
| STT-005 | Integration | STT cancellation | No final transcript is emitted for cancelled stream |
| STT-006 | Integration | STT timeout | Safe error and recoverable Idle state |
| STT-007 | Integration | STT worker saturation | Bounded backpressure; event loop stays responsive |
| STT-008 | Integration | STT health | Missing model reports unavailable with setup guidance |
| TTS-001 | Integration | ElevenLabs stream | Audio starts from stable sentence before full response completes |
| TTS-002 | Security | Cloud payload minimization | Request contains synthesis text/settings only |
| TTS-003 | Integration | Local mode | Zero ElevenLabs calls; Piper output selected |
| TTS-004 | Local AI | Piper synthesis | Supported fixture text produces playable output |
| TTS-005 | Integration | Online pre-stream failure | One Piper fallback starts without duplicate text/audio |
| TTS-006 | Integration | Mid-stream provider failure | Current stream ends cleanly; no overlapping fallback |
| TTS-007 | Integration | TTS cancellation | Provider and output stream stop promptly |
| TTS-008 | Component | Playback blocked | Browser autoplay restriction produces actionable control |
| TTS-009 | Integration | Secret isolation | ElevenLabs key never enters client bundle, API response, or log |

## 9. Conversations and AI

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| CONV-001 | Integration | Create conversation | Durable ID and timestamps are returned |
| CONV-002 | Integration | Turn persistence | User/assistant turns preserve order and terminal status |
| CONV-003 | Integration | Cancelled turn | Terminal status is cancelled; stale deltas are rejected |
| CONV-004 | Integration | History pagination | Stable cursor order with bounded payload |
| CONV-005 | Security | Hidden prompt exclusion | API returns no system policy or secret context |
| AI-001 | Integration | Ollama health | Configured model availability is reported accurately |
| AI-002 | Integration | Stream text | Ordered deltas produce one final response |
| AI-003 | Integration | Model timeout | Turn fails safely within configured bound |
| AI-004 | Integration | Ollama OOM/unavailable | Graceful user response; backend remains responsive |
| AI-005 | Integration | Model cancellation | No stale delta after cancellation |
| AI-006 | Unit | Context bound | Recent turns remain within configured token/record budget |
| AI-007 | Unit | Low confidence | Clarification is returned; no tool proposal executes |
| AI-008 | Security | Secret exclusion | Model context contains no provider/auth/storage secrets |
| AI-009 | Integration | Simple intent routing | Fixture selects fast model with rationale code |
| AI-010 | Integration | Reasoning intent routing | Fixture selects larger local model |
| AI-011 | Performance | Router overhead | Routing remains within allocated latency budget |
| AI-012 | Integration | One tool loop | Propose → validate → observe → answer order is correct |
| AI-013 | Integration | Multi-tool loop | Dependencies execute sequentially and results stay bound |
| AI-014 | Unit | Iteration limit | Loop terminates with safe explanation at configured maximum |
| AI-015 | Unit | Context budget with tools | Oversized tool output is bounded and summarized safely |
| AI-016 | Security | Prompt injection in tool output | Policy/capability/confirmation remain unchanged |
| AI-017 | Integration | Tool failure observation | Model receives safe typed failure and does not fabricate success |
| AI-018 | Integration | Multi-step cancellation | Active/pending steps stop; completed side effects are not misreported |

### M15 Implemented Coverage

| Area | Covered behavior | Automated tests |
|---|---|---|
| Two-tier routing | Deterministic fast/reasoning selection and stable rationale codes | `backend/tests/agent/test_tiered_routing.py` |
| Bounded loop | Ordered server-planned read-only calls and stop-on-confirmation behavior | `backend/tests/agent/test_tool_loop.py` |
| Tool-result isolation | Tool output is delimited as untrusted prompt data; no tool protocol is exposed | `backend/tests/agent/test_m15_agent_loop.py` |

## 10. Memory Lifecycle

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| MEM-001 | Integration | Create preference | SQLite record and index outbox are durable |
| MEM-002 | Integration | Edit memory | Version increments; semantic index updates eventually |
| MEM-003 | Integration | Pin/unpin | Retention eligibility changes immediately in SQLite |
| MEM-004 | Integration | Task completion | Status and configured expiry/archive policy apply |
| MEM-005 | Integration | Category filters | Results contain only requested authorized category |
| MEM-006 | Integration | Lexical search | Exact fixture is returned |
| MEM-007 | Integration | Semantic search | Relevant fixture ranks within documented threshold |
| MEM-008 | Security | Deleted candidate filtering | Stale Chroma ID is never returned to client/model |
| MEM-009 | Integration | Chroma unavailable | Structured browse/edit continues in degraded mode |
| MEM-010 | Integration | Provenance | User can inspect safe source metadata |
| MEM-011 | Unit | Context ranking | Pinned and relevant items outrank unrelated history |
| MEM-012 | Unit | Context minimization | Retrieval returns no more than configured bound |
| MEM-013 | Time-controlled | Casual expiry | Unpinned casual record expires after 30 days |
| MEM-014 | Time-controlled | Pinned exemption | Pinned record survives automatic retention job |
| MEM-015 | Time-controlled | Preference retention | Preference remains until explicit deletion/change |
| MEM-016 | Time-controlled | Completed task policy | Task follows configured completion retention |
| MEM-017 | Integration | Consolidation proposal | Summary preserves source references |
| MEM-018 | Integration | Consolidation deduplication | Repeated run does not duplicate equivalent facts |
| MEM-019 | Integration | Export contents | Expected current records and provenance are present |
| MEM-020 | Security | Export minimization | No secrets, hashes, tokens, or embeddings are included |
| MEM-021 | Time-controlled | Export expiry | Artifact and download access disappear after TTL |
| MEM-022 | Security | Confirmed hard delete | No deletion occurs before valid confirmation |
| MEM-023 | Integration | Cross-store delete | SQLite, Chroma, cache, and staging references are removed |
| MEM-024 | Integration | Delete retry/repair | Interrupted index deletion resumes without resurrecting content |

## 11. Tools and Confirmation

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| TOOL-001 | Unit | Registration schema | Missing capability/risk/timeout/idempotency metadata is rejected |
| TOOL-002 | Security | Disabled capability | Provider is never invoked |
| TOOL-003 | Security | Unsupported native capability | Returns `requires_native_bridge`; no execution path exists |
| TOOL-004 | Unit | Invalid model arguments | Typed validation rejects before execution |
| TOOL-005 | Security | Path traversal | Canonical target outside allowlist is denied |
| TOOL-006 | Security | Symlink/junction escape | Resolved target outside allowlist is denied |
| TOOL-007 | Integration | Read-only tool success | Safe typed result and audit summary are emitted |
| TOOL-008 | Integration | Tool timeout | Result is failed or uncertain according to dispatch state |
| TOOL-009 | Integration | Idempotent retry | One logical effect/result is recorded |
| TOOL-010 | Integration | Non-idempotent retry | Blind automatic retry is blocked |
| TOOL-011 | Security | Log redaction | Tool secret/content fields do not enter logs |
| TOOL-012 | Integration | Capability revocation | New calls fail immediately; affected pending challenge invalidates |
| CONF-001 | Unit | Read-only classification | No confirmation unless stricter policy applies |
| CONF-002 | Unit | External action classification | Confirmation is mandatory |
| CONF-003 | Unit | Destructive/financial classification | Confirmation is mandatory and summary names consequence |
| CONF-004 | Integration | Challenge binding | Challenge stores canonical action hash and policy/session binding |
| CONF-005 | Security | Generic “yes” without challenge | No action executes |
| CONF-006 | Security | Expired challenge | Approval is rejected |
| CONF-007 | Security | Replayed approval | Action executes at most once |
| CONF-008 | Security | Argument substitution | Changed action cannot use prior challenge |
| CONF-009 | Security | Target version change | Challenge invalidates before execution |
| CONF-010 | Security | Session revocation | Pending challenge cannot execute |
| CONF-011 | Security | Capability change | Pending challenge cannot execute |
| CONF-012 | Integration | Explicit rejection | Action remains unexecuted and is audited |
| CONF-013 | Integration | Valid approval | Exact fake action executes once |
| CONF-014 | Integration | Disconnect | Pending voice challenge is not approved/resumed |
| CONF-015 | Integration | Unknown provider outcome | Status is uncertain; no blind retry |
| CONF-016 | Integration | Proactive proposal | Scheduled job creates challenge but does not execute action |

## 12. Scheduler, Security, Performance, and Deployment

| ID | Level | Scenario | Pass criterion |
|---|---|---|---|
| JOB-001 | Time-controlled | Retention job schedule | Executes at configured local intent/UTC instant |
| JOB-002 | Integration | Consolidation isolation | Job failure does not roll back unrelated durable work |
| JOB-003 | Integration | Job restart recovery | Persisted next run survives process restart |
| JOB-004 | Integration | Single leader | One occurrence executes once |
| JOB-005 | Integration | Job observability | Start/result/duration and safe counts are recorded |
| JOB-006 | Integration | Create reminder | Next run and timezone are correct |
| JOB-007 | Time-controlled | DST transition | Documented skip/duplicate policy is honored |
| JOB-008 | Time-controlled | Missed run | Configured skip/run-once behavior is honored |
| JOB-009 | Integration | Disable schedule | No future occurrence executes |
| JOB-010 | Integration | Update schedule | Old next run is replaced atomically |
| JOB-011 | Integration | Reminder delivery | Active client receives one non-consequential event |
| JOB-012 | Integration | No active client | Event remains safely visible in durable status/history as designed |
| JOB-013 | Security | Scheduled tool request | Consequential call pauses for confirmation |
| JOB-014 | Integration | Scheduler unavailable | Settings reports degraded; core assistant remains usable |
| SEC-001 | Security | Unauthenticated private API | Request is denied |
| SEC-002 | Security | Session fixation | Login rotates any pre-auth session identifiers |
| SEC-003 | Security | Cookie attributes | Secure, HttpOnly, SameSite, path, and expiry are correct |
| SEC-004 | Security | Session revocation race | Revoked session cannot create new ticket/action |
| SEC-005 | Security | WebSocket URL/log redaction | Ticket is absent from logs and error bodies |
| SEC-006 | Security | WebSocket event fuzzing | Invalid schemas/state cannot crash or execute work |
| SEC-007 | Security | Connection exhaustion | Per-session limits protect service availability |
| SEC-008 | Security | Filesystem device/network path | Disallowed path classes are denied |
| SEC-009 | Security | Tool confused-deputy attempt | Granted capability cannot widen target scope |
| SEC-010 | Security | Untrusted content instructions | Tool data cannot alter system/tool policy |
| SEC-011 | Security | Confirmation race | Concurrent approvals produce one execution |
| SEC-012 | Security | Confirmation summary integrity | Displayed summary matches bound normalized action |
| SEC-013 | Security | Data remanence | Hard-delete fixture absent from active stores/exports |
| SEC-014 | Security | Prompt-based permission escalation | No capability change occurs |
| SEC-015 | Security | Secret exfiltration prompt | Secrets absent from model context/output/tool args |
| SEC-016 | Security | Data-directory permissions | Unsafe production permissions fail readiness |
| PERF-001 | Performance | End speech to final transcript | Meets allocated STT segment budget on reference host |
| PERF-002 | Performance | End speech to first local audio | Warm local route p95 is under 1.5 seconds on reference host |
| DEP-001 | Deployment | Fresh host install | Documented install reaches healthy status |
| DEP-002 | Deployment | Same-origin routing | Web, REST, and WebSocket work under one HTTPS origin |
| DEP-003 | Security | Public/LAN exposure scan | No unintended unauthenticated listener is reachable |
| DEP-004 | Deployment | Tailscale mobile access | Authenticated supported mobile browser connects over HTTPS |
| DEP-005 | Deployment | Process restart | Services recover without duplicate jobs or corrupt turns |
| DEP-006 | Recovery | SQLite backup/restore | Restored database passes integrity and current migration checks |
| DEP-007 | Recovery | Chroma restore/rebuild | Semantic search recovers from backup or SQLite rebuild |
| DEP-008 | Deployment | Upgrade migration | Backup, migrate, smoke test, and rollback procedure are proven |
| DEP-009 | Security | Local mode egress | No ElevenLabs request or unintended cloud egress occurs |
| DEP-010 | Recovery | Dependency outage | Ollama/Chroma/ElevenLabs/Piper outage states and recovery are correct |

## 13. Release Gates

### Milestone Gate

- All tests directly referenced by the milestone pass.
- No unresolved severity-1 defect in milestone scope.
- Any skipped test has a recorded reason, owner, and expiry.

### Private v1 Gate

- All authentication, capability, confirmation, hard-delete, redaction, backup/restore, and Tailscale security tests pass.
- `PERF-002` meets the PRD target on the declared reference hardware for the warm local path.
- Critical mobile/desktop manual tests pass on the documented support matrix.
- Unsupported native capabilities are visibly labeled and cannot be invoked.
- No Critical risk is unaccepted; no High risk lacks an active mitigation and owner.

## 14. M8 Implemented STT Coverage

| Area | Implemented evidence | Test files |
|---|---|---|
| Domain and PCM | Language/confidence bounds, segment ordering, transcript bounds, PCM sample count/duration, malformed PCM rejection | `backend/tests/stt/test_stt_models.py`, `backend/tests/stt/test_audio_preparation.py` |
| Fake provider | Deterministic local final/partial behavior without external services | `backend/tests/stt/test_fake_provider.py`, `backend/tests/stt/test_transcription_websocket.py` |
| Faster-whisper boundary | Optional import, lazy single load, local directory requirement, no auto-download, mapped final result, cancellation, timeout, and safe failures with mocked modules only | `backend/tests/stt/test_faster_whisper_adapter.py`, `backend/tests/stt/test_faster_whisper_loading.py` |
| Job limits and lifecycle | Duplicate-turn suppression, concurrent duplicate request behavior, queue/concurrency/per-connection limits, terminal ordering, timeout/cancellation, and bounded terminal pruning | `backend/tests/stt/test_transcription_jobs.py`, `backend/tests/stt/test_transcription_queue.py`, `backend/tests/stt/test_transcription_cleanup.py`, `backend/tests/stt/test_transcription_websocket.py` |
| Privacy and isolation | Event payload excludes PCM and credentials; owner/session/connection cancellation checks prevent foreign cancellation | `backend/tests/stt/test_stt_security.py`, `backend/tests/stt/test_transcription_jobs.py` |
| Health and status | Live shared-registry counts, optional unavailable degradation, authenticated safe status fields, and required/optional readiness regression | `backend/tests/stt/test_stt_health.py`, `backend/tests/test_m5_framework.py`, `backend/tests/test_health.py`, `backend/tests/test_readiness.py` |
| Regression | Audio transport, ticket/session binding, migrations, backend suite, and frontend validation remain covered by their existing suites | `backend/tests/audio`, `backend/tests/test_websocket_transport.py`, `backend/tests/test_migrations.py`, `frontend/tests` |

All standard M8 tests use fakes or mocked faster-whisper modules. The `stt_integration` marker is reserved for an explicitly provisioned local model and is not part of standard CI or repository validation. No standard M8 test downloads a model, accesses the internet, requires a GPU, or is xfailed.

## 15. M9A Implemented Language-Model Coverage

| Area | Implemented evidence | Test files |
|---|---|---|
| Domain contracts | Bounded text, UTC timestamps, UUID identity, state/intent enums, confidence, non-negative usage, and no chain-of-thought field | `backend/tests/agent/test_agent_models.py` |
| Provider-neutral validation | Context limits, control-character rejection, safe Unicode handling, and line-ending normalization | `backend/tests/agent/test_llm_validation.py` |
| Fake provider | Deterministic response/usage, delay, timeout, cancellation, unavailable state, malformed/excessive/invalid output, and development-only guard | `backend/tests/agent/test_fake_llm.py` |
| Ollama adapter | Mocked request/role mapping, final response/usage mapping, malformed/unavailable/timeout/cancellation behavior, budgets, no pull route, and credential/config rejection | `backend/tests/agent/test_ollama_adapter.py` |
| Provider health | Disabled/fake development snapshots, mocked ready/unavailable/timeout Ollama snapshots, and production fake/settings rejection | `backend/tests/agent/test_llm_health.py` |

M9A standard tests use deterministic fakes and `httpx.MockTransport` only. They do not require an Ollama process, model pull, internet access, cloud provider, or GPU hardware.

## 16. M9B Implemented Intent, Prompt, and Context Coverage

| Area | Implemented evidence | Test files |
|---|---|---|
| Intent routing | Deterministic category, confidence, reason-code, clarification, and consequential-risk classification; informational action questions remain non-consequential | `backend/tests/agent/test_intent_router.py` |
| Prompt construction | Server-owned persona/safety messages, explicit untrusted-context delimiters, final user input, bounded deterministic context inclusion, and no tool or hidden-reasoning prompt fields | `backend/tests/agent/test_prompt_builder.py` |
| Context policy | Normal-only default, explicit private/sensitive enabling, and permanent restricted exclusion | `backend/tests/agent/test_context_policy.py` |
| Persistence context | Authenticated-owner-bound retrieval, pinned-first active memories, completed turns only, safe provenance metadata, expiry exclusion, deterministic character/token truncation, and no ORM exposure | `backend/tests/agent/test_context_provider.py` |

M9B tests use only the isolated SQLite fixtures and deterministic code paths. They do not invoke an LLM, Ollama process, ChromaDB, network access, tool, WebSocket, or device capability.

## 17. M9C Implemented Agent Service Coverage

| Area | Implemented evidence | Test files |
|---|---|---|
| Service lifecycle | Direct/final-transcript request handling, partial-transcript exclusion, input validation, deterministic no-model outcomes, provider failure mapping, and session rejection | `backend/tests/agent/test_agent_service.py` |
| Queue and idempotency | FIFO bounded workers, global/concurrency/connection limits, accurate counters, concurrent duplicate suppression, and session-scoped idempotency | `backend/tests/agent/test_agent_queue.py`, `backend/tests/agent/test_agent_idempotency.py` |
| Persistence | Owner-scoped conversation resolution, immutable request metadata, atomic successful turns, valid provider usage metadata, and prompt exclusion | `backend/tests/agent/test_agent_persistence.py`, `backend/tests/test_migrations.py` |
| Cancellation and cleanup | Owner/session/connection-bound cancellation, idempotent repeated cancellation, terminal pruning, and explicit worker shutdown | `backend/tests/agent/test_agent_cancellation.py`, `backend/tests/agent/test_agent_cleanup.py` |
| Security | Prompt/auth material exclusion from persisted metadata, no confirmation/tool path, and deterministic consequential-action refusal | `backend/tests/agent/test_agent_security.py` |

M9C tests use deterministic fake providers, isolated SQLite databases, and process-local workers only. They require no Ollama process, model pull, internet, cloud service, tool, WebSocket agent event, or device capability.

## 18. M9D Agent Transport, Health, and Final Acceptance Coverage

| Area | Implemented evidence | Test files |
|---|---|---|
| WebSocket agent protocol | Authenticated `agent.request`, strict payload rejection, ordered started/state/terminal delivery, and safe error payloads | `backend/tests/agent/test_agent_websocket.py` |
| STT handoff | Final transcript submission starts one bound agent request; partial/failed/canceled STT paths remain excluded by the job publisher | `backend/tests/agent/test_agent_websocket_handoff.py`, `backend/tests/stt/test_transcription_websocket.py` |
| Lifecycle safety | Registry shutdown cancellation cannot be swallowed by a worker; existing owner/session/connection cancellation and idempotency coverage remains active | `backend/tests/agent/test_agent_cancellation.py`, `backend/tests/agent/test_agent_cleanup.py`, `backend/tests/agent/test_agent_idempotency.py` |
| LLM health/status | Disabled/fake/unavailable provider health, required/optional readiness semantics, and authenticated safe status fields | `backend/tests/agent/test_llm_health.py`, `backend/tests/test_health.py`, `backend/tests/test_readiness.py` |

M9D standard validation uses only deterministic providers, isolated SQLite files, and mocked local HTTP where adapter coverage requires it. It does not require an Ollama process, model pull, internet access, cloud service, TTS, tool, confirmation, semantic retrieval, or device action.

## 19. M10A TTS Provider Foundation Coverage

| Area | Implemented evidence | Test files |
|---|---|---|
| Domain and validation | UTC identities, plain-text normalization, bounded final PCM, format allowlists, alignment, duration/sample consistency, and chunk validation | backend/tests/tts/test_tts_models.py, backend/tests/tts/test_tts_validation.py |
| Fake provider | Deterministic audio/duration, delay, timeout, cancellation, unavailable, malformed/excessive audio, invalid metadata, and unsupported language/format | backend/tests/tts/test_fake_tts.py |
| Piper adapter | Explicit local voice, argument-array invocation, stdin text, PCM mapping, non-zero exit/timeout/cancellation handling, child termination, bounded stdout, and sanitized stderr | backend/tests/tts/test_piper_adapter.py |
| Health and security | Disabled/fake/Piper path/timeout health states, production configuration guards, and TTS-sensitive structured-log redaction | backend/tests/tts/test_tts_health.py, backend/tests/tts/test_tts_security.py |
| Optional cloud adapter | ElevenLabs final-audio mapping and safe provider error mapping through httpx.MockTransport only | backend/tests/tts/test_elevenlabs_adapter.py |

M10A real provider checks are opt-in under tts_integration. Standard CI uses no Piper executable, voice model, ElevenLabs credential, cloud request, internet access, audio playback, WebSocket event, or frontend capability.

## 20. M10B TTS Service, Queue, Chunking, and Cancellation Coverage

| Area | Implemented evidence | Test files |
| --- | --- | --- |
| Agent-response service boundary | Completed server-resolved source only, normalized text, typed source/provider failures, and one provider call maximum | `backend/tests/tts/test_tts_service.py` |
| Queue and idempotency | FIFO work, bounded concurrency, connection limit, duplicate suppression, and owner/session isolation | `backend/tests/tts/test_tts_queue.py`, `backend/tests/tts/test_tts_idempotency.py` |
| Chunking and retention | Frame-aligned post-synthesis PCM chunk metadata, no invalid fragments, transient audio consumption, and shutdown release | `backend/tests/tts/test_tts_chunking.py`, `backend/tests/tts/test_tts_retention.py` |
| Cancellation and cleanup | Active cancellation, timeout terminal state, connection/session cancellation seams, and worker cleanup | `backend/tests/tts/test_tts_cancellation.py`, `backend/tests/tts/test_tts_cleanup.py` |
| Privacy and isolation | Cross-connection source rejection and structured-log redaction of text/audio/token/stderr fields | `backend/tests/tts/test_tts_service_security.py` |

M10B standard validation uses deterministic fakes and mocked provider boundaries only. It requires no Piper installation, ElevenLabs credential or request, model download, internet access, WebSocket delivery, playback, barge-in, or frontend voice feature.

## 21. M10C TTS Transport, Playback, and Final Acceptance Coverage

| Area | Implemented evidence | Test files |
| --- | --- | --- |
| WebSocket handoff/delivery | Successful fake-agent handoff, ordered lifecycle events, final PCM start/chunks/end, and client cancel shape | `backend/tests/tts/test_tts_websocket.py` |
| Health and authenticated status | Required unavailable readiness and safe disabled status counters | `backend/tests/tts/test_tts_health_integration.py` |
| Browser playback | Mocked Web Audio activation, ordered chunk acceptance, fail-closed ordering, explicit Stop, VAD barge-in, and suspended context | `frontend/tests/unit/tts-playback.test.ts` |

Standard M10C validation uses fake providers and mocked Web Audio only. It performs no Piper install, ElevenLabs request, model download, internet access, real microphone/speaker use, background capture, wake-word operation, or native-device action.

## 22. M11A Foreground Wake-Word Foundation Coverage

| Area | Implemented evidence | Test files |
| --- | --- | --- |
| Domain contracts and settings | UTC timestamps, confidence/phrase/frame/configuration bounds, immutable audio-session identity, M7 frame binding, disabled default, and production-fake rejection | `backend/tests/wakeword/test_wakeword_models.py` |
| Deterministic fake detector | Trigger/no-trigger/repeated behavior, delay, cancellation, unavailable state, and malformed output without network or microphone access | `backend/tests/wakeword/test_fake_wakeword.py` |
| Foreground service | Disabled behavior, confidence/consecutive policy, debounce/cooldown, stale-frame rejection, bounded metadata buffer, provider isolation/recovery, and no agent handoff | `backend/tests/wakeword/test_wakeword_service.py`, `backend/tests/wakeword/test_wakeword_debounce.py` |
| Identity isolation | Owner/session/connection/audio-session state isolation, cleanup, revocation handling, reconnect-safe new state, and concurrent per-session detection | `backend/tests/wakeword/test_wakeword_isolation.py` |
| Health and privacy | Disabled/fake/unavailable non-activating snapshot, truthful foreground capability flags, safe failures, and log redaction/no service logging | `backend/tests/wakeword/test_wakeword_health.py`, `backend/tests/wakeword/test_wakeword_security.py` |
| Browser lifecycle controller | Existing-capture gate, hidden-tab suspend, conditional resume, permission/device/socket cleanup, TTS suspend, and no background capability claim | `frontend/tests/unit/wakeword.test.ts` |

M11A standard validation uses deterministic fakes and mocked browser-state callbacks only. It requires no real microphone, wake-word model, model download, internet access, background capture, WebSocket wake-word event, native service, or device action.
