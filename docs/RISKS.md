# Tara Risk Register

## 1. Method

Probability and impact use `Low`, `Medium`, `High`, and `Critical`. Priority is driven first by impact, then probability and proximity. A risk remains open until its mitigation is implemented and verified, or the owner explicitly accepts the residual risk.

Owners are functional roles until named maintainers exist:

- Product: scope and user promise.
- Architecture: cross-system decisions and capability boundaries.
- Frontend: browser behavior and responsive UX.
- Backend: services, persistence, jobs, and operations.
- AI/Voice: STT, VAD, model, and TTS behavior.
- Security: auth, permissions, confirmation, secrets, and privacy.
- Operations: deployment, backup, monitoring, and recovery.

## 2. Active Risks

| ID | Risk | Probability | Impact | Owner | Mitigation and verification | Trigger / contingency |
|---|---|---|---|---|---|---|
| R-001 | Web-only architecture cannot satisfy locked-screen/screen-off wake listening | High | Critical | Product + Architecture | Mark capability `requires_native_bridge`; keep foreground listening explicit; test browser suspension boundary; make no always-on claim | If always-on remains a launch requirement, execute M18 and approve a minimal native bridge before changing product claims |
| R-002 | Web-only architecture cannot directly perform Android calls/SMS, notification access, Accessibility Service automation, or desktop tray behavior | High | High | Product + Architecture | Expose unsupported state honestly; keep device actions behind adapters; exclude executable stubs | If these become launch-critical, create ADR and separate bridge milestone with permission/security testing |
| R-003 | WhatsApp UI automation breaks after app updates | High | High | Product + Integrations | Keep unavailable in web-only v1; if future bridge is approved, isolate selectors, add version checks and smoke tests, investigate supported business API | Disable capability immediately on failed compatibility smoke test; never retry blindly |
| R-004 | Mobile browser/PWA suspends audio, WebSocket, timers, or notifications unpredictably | High | High | Frontend | Maintain support matrix; use explicit active-session model; detect visibility/disconnect; recover to Idle; manual device tests | Disable affected behavior on unsupported browser/version and show guidance |
| R-005 | Local hardware cannot meet sub-1.5-second voice target | Medium | High | AI/Voice + Operations | Establish reference hardware; profile VAD/STT/router/TTS budgets; warm models; choose fit-for-device Ollama/Whisper sizes; stream sentence TTS | Publish degraded hardware tier or adjust local model selection; do not hide failed p95 gate |
| R-006 | Ollama hangs, runs out of memory, or starves other pipeline stages | Medium | High | AI/Voice | Bounded workers, timeouts, cancellation, model health, concurrency limits, memory checks, graceful fallback text | Mark model unavailable, cancel turn, preserve UI responsiveness, require explicit retry |
| R-007 | Misheard or ambiguous commands cause harmful actions | Medium | Critical | Security + AI/Voice | Deterministic risk policy, scoped capabilities, explicit one-time confirmation, clarification on low confidence, no implicit “yes” | Disable consequential tools if confirmation invariant fails; investigate audit trail before re-enable |
| R-008 | Confirmation race, replay, or argument substitution executes an unintended action | Low | Critical | Security + Backend | Bind challenge to owner/session/action hash/target version/policy/expiry; atomic single-use transition; idempotency tests | Stop consequential tools, revoke sessions, reconcile action outcome, patch before re-enable |
| R-009 | Prompt injection through files, memories, or tool output manipulates agent behavior | High | High | Security + AI | Treat retrieved/tool content as untrusted data; bounded context; typed tool schemas; server-owned policy; no secrets in context; adversarial tests | Cancel affected turn/tool, quarantine source, preserve minimized audit evidence |
| R-010 | Tool adapter escapes permitted filesystem/action scope | Medium | Critical | Security + Backend | Canonical paths, allowlisted roots, symlink/junction policy, separate read/write/delete grants, no generic shell tool | Disable tool, inspect audit and target effects, rotate exposed secrets if necessary |
| R-011 | Duplicate or uncertain external side effects after timeout/retry | Medium | Critical | Backend + Integrations | Action IDs, provider idempotency keys, dispatch-state tracking, no blind retry of non-idempotent calls, reconciliation path | Show `uncertain`, block automatic retry, verify provider state before another attempt |
| R-012 | SQLite and ChromaDB diverge, returning deleted or stale memory | Medium | High | Backend | SQLite authority, transactional outbox, read-time validation, idempotent sync, deletion verification, rebuild job | Disable semantic recall, serve structured memory, repair/rebuild index from SQLite |
| R-013 | Hard delete leaves content in exports, caches, logs, index, or backups | Medium | Critical | Security + Backend + Operations | Minimize content in logs; delete active stores/caches/artifacts; test canaries; document backup-retention limitation | Quarantine affected artifacts, complete deletion, disclose residual backup window accurately |
| R-014 | Plain SQLite or weak key storage exposes sensitive memory | Medium | Critical | Security + Operations | Enable SQLCipher before sensitive production use; separate key storage; strict permissions; encrypted backup expectations | Block readiness for sensitive mode; migrate only after verified backup and key recovery test |
| R-015 | Session or WebSocket ticket theft gives unauthorized access | Medium | Critical | Security | Secure/HttpOnly/SameSite cookies, short lifetimes, refresh rotation, CSRF/origin checks, one-use tickets, revocation | Revoke all sessions, rotate signing secret if needed, review audit access window |
| R-016 | Tailscale or reverse-routing misconfiguration exposes Tara publicly or over raw LAN HTTP | Low | Critical | Operations + Security | Bind privately/loopback; same-origin HTTPS; deployment exposure tests; no wildcard CORS; minimal unauth health | Stop service exposure, revoke sessions/secrets, correct ACL/routing, rerun security gate |
| R-017 | Logs or diagnostics leak transcripts, memory, message bodies, credentials, or host paths | Medium | High | Security + Observability | Allowlisted structured fields, redaction middleware, canary tests, confirmed time-limited diagnostics, bounded retention | Halt diagnostics sharing, delete leaked artifact, rotate secrets, fix redaction test |
| R-018 | ElevenLabs receives more personal context than needed or changes privacy/pricing behavior | Medium | High | Product + Security + AI/Voice | Send synthesis text only; explicit cloud indicator/local mode; server-only key; re-verify vendor terms/model/pricing at milestone kickoff | Default to Piper/local mode; suspend cloud TTS until review completes |
| R-019 | ElevenLabs latency/outage creates broken or overlapping speech | Medium | Medium | AI/Voice | Pre-stream fallback to Piper, clean mid-stream stop, per-stream IDs, cancellation and duplicate-audio tests | End current utterance, state degradation, offer/retry using local voice |
| R-020 | Piper fallback quality does not meet Tara's persona or has unsuitable model licensing | Medium | Medium | Product + AI/Voice | Evaluate voice quality and license before release; keep provider replaceable; disclose local voice difference | Choose another compatible Piper voice/model or limit fallback language while retaining text |
| R-021 | faster-whisper accuracy degrades with accent, noise, names, or low-end hardware | Medium | High | AI/Voice | Representative public fixtures, model selection by host, partial/final confidence, clarification, user transcript visibility/correction | Ask for clarification; expose text correction; select larger model where hardware allows |
| R-022 | VAD cuts off pauses or fails in noisy environments | Medium | High | AI/Voice | Configurable 700 ms–1 s silence, smoothing, device fixtures, max-utterance protection, manual ambient tests | Provide sensitivity/end-turn settings and explicit stop control; tune by device class |
| R-023 | Barge-in cancellation leaves stale model/TTS/tool work active | Medium | High | Backend + AI/Voice | Per-turn cancellation scope, stream IDs, stale-event rejection, serialized session turns, stress tests | Cancel session, return to Idle, block new consequential work until state reconciles |
| R-024 | Multiple FastAPI workers run duplicate APScheduler jobs or contend on SQLite | Medium | High | Backend + Operations | Single process/leader ADR; readiness assertion; deployment checks; persistent job metadata | Stop duplicate leader, reconcile occurrences, disable scheduler until topology is corrected |
| R-025 | Timezone, daylight-saving, sleep, or restart causes missed/duplicate proactive events | Medium | Medium | Backend | Store IANA timezone and local intent; explicit misfire policy; deterministic clock tests; idempotent occurrence IDs | Show missed event history; execute at most once according to documented policy |
| R-026 | Proactive behavior becomes intrusive or causes unapproved side effects | Medium | High | Product + Security | User-managed schedules, quiet behavior, visible history, easy disable, same confirmation gate for consequences | Disable schedule/capability; never auto-execute follow-up action |
| R-027 | Database migration or upgrade corrupts personal data | Low | Critical | Backend + Operations | Explicit Alembic step, pre-migration backup, fixture upgrades, integrity checks, tested restore; no silent destructive startup migration | Stop upgrade, restore verified backup, hold release until migration defect is resolved |
| R-028 | Backup is unusable, incomplete, or inconsistent across SQLite and Chroma | Medium | High | Operations | SQLite online backup, aligned Chroma snapshot or rebuild marker, recurring restore tests, version metadata | Restore SQLite and rebuild Chroma; do not claim backup success without restore evidence |
| R-029 | Chroma or SQLite performance degrades as conversation history grows | Medium | Medium | Backend | Retention, consolidation, bounded retrieval, indexes, pagination, performance fixtures, index rebuild | Degrade to structured lookup, run maintenance, adjust retention/index based on measured evidence |
| R-030 | Memory consolidation creates false, duplicated, or overconfident facts | Medium | High | AI + Backend | Provenance, confidence, deduplication, user edit/delete, bounded source references, review tests | Suppress low-confidence fact from context; show source; allow correction and re-index |
| R-031 | Single-user assumptions leak into architecture and block future household use | Medium | Medium | Architecture | Keep owner ID in schemas and isolation checks even with one owner; defer roles/speaker ID explicitly | Record new multi-user ADR and migration plan before expanding product scope |
| R-032 | Dependency/model updates alter behavior, licensing, or API contracts | High | High | Architecture + Operations | Pin versions/model IDs, provenance records, compatibility tests, staged upgrades, vendor re-verification | Roll back to pinned set; disable affected provider/capability |
| R-033 | Cloud or package supply-chain compromise affects local assistant privileges | Low | Critical | Security + Operations | Minimize dependencies, lockfiles/hashes, review updates, least-privilege processes, no arbitrary plugin execution | Isolate host, revoke provider/session secrets, restore trusted build/data backup |
| R-034 | Responsive shared UI becomes lowest-common-denominator and fails native-like mobile or desktop density goals | Medium | High | Frontend + Product | Separate shells over shared domain components; behavioral breakpoints; real-device/manual tests; design token governance | Adjust shell composition without forking product logic or token system |
| R-035 | Guide Star animation harms accessibility or consumes excessive mobile resources | Medium | Medium | Frontend | Reduced motion, smoothed amplitude, limited glow, performance profiling, semantic text status | Disable continuous animation on affected device/preference and retain static state cues |
| R-036 | Browser/API support changes across releases | High | Medium | Frontend | Published support matrix, feature detection, permission recovery, Playwright plus real-device smoke tests | Mark browser unsupported/degraded and provide text mode rather than unsafe workaround |
| R-037 | Source-of-truth drift between PRD, decisions, contracts, and implementation | Medium | High | Architecture | ADR process, status update discipline, contract tests, milestone doc updates, PR review checklist | Stop affected milestone, reconcile docs and behavior before merge/release |
| R-038 | Scope expands into vision, speaker ID, public SaaS, or native bridge before core safety is stable | Medium | High | Product | Milestone gates, explicit post-v1 labels, separate ADR/authorization, no speculative implementation | Remove work from active milestone or seek explicit scope approval |

## 3. Immediate Critical Controls

The following controls must exist before Tara handles real owner data or real side effects:

1. Accurate `requires_native_bridge` status for unsupported web capabilities.
2. Application authentication on top of Tailscale.
3. Scoped capabilities with default deny.
4. Deterministic, action-bound, one-time confirmation.
5. No generic shell tool and strict filesystem root policy.
6. SQLCipher-compatible encrypted SQLite and protected secrets.
7. Content-minimized logs and verified diagnostics redaction.
8. Backup/restore and cross-store hard-delete tests.

## 4. Risk Review Cadence

- Review at every milestone kickoff and exit.
- Re-score vendor/model/browser risks at least quarterly during active development, consistent with the PRD's warning that voice vendors change quickly.
- Re-review all Critical risks before enabling a new consequential capability.
- Add a risk when a test is repeatedly skipped, a manual environment is unsupported, or a workaround creates an unmodeled trust boundary.
- Close a risk only with evidence from `TEST_MATRIX.md` or a documented acceptance decision.

## 5. Risk Acceptance Rules

- Critical residual risk requires explicit owner acceptance and must not violate the confirmation or authentication invariants.
- High residual risk requires a named mitigation owner, review date, and user-visible limitation where applicable.
- Unsupported capability is safer than a fragile or misleading partial implementation.
- A model-quality improvement never compensates for a missing deterministic security control.
