# Tara Manual Test Procedures

## 1. Purpose

These procedures validate behavior that automated tests cannot fully establish: real microphones and speakers, browser permissions, mobile ergonomics, responsive layout, perceived latency, Guide Star motion, screen-reader behavior, Tailscale routing, OS sleep/suspension, and honest native-capability boundaries.

No manual test should use real sensitive memory, contacts, messages, files, or payments. Consequential flows use a fake tool or a designated harmless test target unless the tester explicitly authorizes otherwise.

## 2. Test Record Template

Record for every run:

- Test ID and date/time.
- Build/version and Git revision.
- Backend host, OS, CPU/GPU/RAM, and model identifiers.
- Browser, browser version, device, OS, and installed-PWA/tab mode.
- Network path: loopback or Tailscale.
- Voice mode: ElevenLabs or Piper/local.
- Result: Pass, Fail, Blocked, or Not applicable.
- Actual result, screenshots/log correlation ID, and defect link.

## 3. Required Device Matrix

Before private v1, test at least:

| Class | Minimum coverage |
|---|---|
| Compact Android | Current supported Chromium browser, portrait and landscape, tab and installed PWA where available |
| Compact iOS | Current supported Safari, portrait and landscape, tab and home-screen mode where available |
| Desktop Windows | Current Chromium plus one additional supported browser |
| Desktop macOS | Safari or declared supported browser if macOS support is claimed |
| Accessibility | Keyboard-only desktop, 200% zoom, reduced motion, one desktop screen reader, one mobile screen reader smoke pass |

Exact versions must be recorded at release time rather than hard-coded here.

## 4. Foundation and Responsive UI

### MAN-UI01 — Compact Shell

1. Open each of Listen, Memory, Actions, and Settings below 768 px width.
2. Rotate the device and open/close the software keyboard where applicable.
3. Exercise bottom navigation and browser Back.

Pass: all destinations remain reachable; safe areas are respected; no horizontal scroll, clipped controls, lost route state, or keyboard-covered primary action appears.

### MAN-UI02 — Expanded Desktop Shell

1. Open each core route above 1200 px.
2. Resize through medium and compact widths, then back to expanded.
3. Use sidebar navigation and optional detail panels.

Pass: sidebar behavior matches the defined breakpoint, content remains bounded/readable, and no duplicate runtime or stale selected state appears.

### MAN-UI03 — Guide Star State Language

1. Trigger Idle, Listening, Thinking, Speaking, Confirming, Error, and Offline fixture states.
2. View each on compact and expanded layouts.
3. Repeat with reduced motion enabled.

Pass: states are distinguishable without color alone, animation is calm and responsive, Confirming is unmistakable, and reduced-motion mode communicates the same state without continuous/spatial motion.

### MAN-UI04 — Loading, Empty, Error, Offline

1. Load each core screen with delayed data.
2. Use an empty fixture.
3. Inject a domain error and disconnect the backend.

Pass: each screen gives an accurate state and recovery action; cached data is not presented as current writable data while offline.

## 5. Voice and Conversation

### M7 Audit Boundary

M7 provides transport and helper contracts only; it does not provide a Listen screen, AudioWorklet pipeline, STT, TTS, or device-selection UI. The voice procedures below remain planned manual acceptance procedures and must not be recorded as passed for M7. The only supported M7 browser behavior is user-invoked foreground `getUserMedia` capture with explicit stop/cancel/page-hide cleanup; locked-screen and background capture remain unsupported.

### MAN-V01 — Microphone Permission Grant

1. Start from a browser profile with no microphone decision.
2. Explicitly start listening and grant access.
3. Speak a short public test phrase.

Pass: capture begins only after the user action and grant; Listening state appears; transcript finalizes once; no raw audio artifact is retained by default.

### MAN-V02 — Permission Denial and Recovery

1. Deny microphone access.
2. Attempt to start listening.
3. Follow the UI guidance to restore permission and retry.

Pass: Tara does not loop prompts or claim to listen; the guidance is browser-appropriate; a later grant works without reloading unrelated data.

### MAN-V03 — End-of-Turn and Ambient Noise

1. Speak phrases with short internal pauses.
2. Pause for less than the configured threshold, then continue.
3. Pause beyond the threshold.
4. Repeat with moderate background noise.

Pass: short pauses do not split the utterance; 700 ms–1 s configured silence ends it; ambient noise does not create repeated false turns.

### MAN-V04 — Browser Suspension Boundary

1. Start a foreground listening session on mobile.
2. Switch applications, lock the screen, and wait.
3. Return to Tara.

Pass: the product never claims continuous locked-screen wake support; suspension/disconnection is stated; recording does not resume without an explicit supported action.

### MAN-V05 — Audio Device Change

1. Begin listening with the default microphone.
2. Connect/disconnect a headset or change the selected input.

Pass: Tara stops or renegotiates safely, identifies the device issue, and never streams from an unintended device silently.

### MAN-V06 — Natural Voice Loop

1. Complete ten short local-model turns covering factual, command-like, and ambiguous phrases.
2. Observe transitions and transcript timing.

Pass: no fixed recording window is perceived; state order is coherent; ambiguous requests clarify; no turn hangs indefinitely.

### MAN-V07 — Barge-In

1. Ask for a response long enough to produce several sentences.
2. Speak over Tara during the second sentence.

Pass: old audio stops promptly, the Guide Star changes to Listening, the new utterance is captured, and old text/audio does not resume.

### MAN-V08 — Local Voice Fallback

1. Enable online voice and verify one test response.
2. Disable network access or inject ElevenLabs unavailability before the next response.
3. Repeat in explicit local mode.

Pass: pre-stream failure falls back to Piper without duplicate speech; local mode never contacts ElevenLabs; the active mode is visible.

### MAN-V09 — Perceived Latency

1. Warm the configured local models using the documented procedure.
2. Run at least 30 short local-route utterances.
3. Measure end of speech to first audible response with pipeline timing and observation.

Pass: p95 is below 1.5 seconds on the declared reference host, or release status clearly records a failed performance gate.

## 6. Authentication and Connection

### MAN-A01 — First-Run Bootstrap

1. Start with a fresh data directory from loopback.
2. Create the owner and label the device.
3. Attempt to revisit bootstrap from loopback and another peer.

Pass: setup succeeds once; subsequent bootstrap is closed; private routes require the created session.

### MAN-A02 — Session Lifecycle

1. Log in from two named devices.
2. Revoke one device from Settings.
3. Attempt REST and WebSocket activity from the revoked device.

Pass: revocation becomes effective immediately enough to prevent new work; the retained device remains active; audit history identifies the event without secrets.

### MAN-A03 — Tailscale Private Access

1. Connect a mobile device through the intended Tailscale network.
2. Open the HTTPS application and complete login and a text turn.
3. Attempt direct LAN/public access using the deployment validation procedure.

Pass: private HTTPS works; no certificate/mixed-content/microphone secure-context error appears; unintended direct access is unavailable.

### MAN-A04 — Connection Loss and Recovery

1. Begin a non-consequential turn.
2. Drop network connectivity during Thinking and again during Speaking.
3. Restore connectivity.

Pass: offline state is honest; no duplicate turn/action appears; reconnect starts Idle and refetches durable history.

## 7. Confirmation and Capability Safety

### MAN-C01 — Exact External-Action Confirmation

1. Use the fake consequential tool to propose sending a test message.
2. Inspect recipient, content summary, expiry, and controls.
3. Approve once.

Pass: warm Confirming state appears; displayed summary matches the bound action; fake tool records exactly one execution after approval.

### MAN-C02 — Reject and Expire

1. Propose the fake consequential action and reject it.
2. Propose it again and allow the challenge to expire.

Pass: neither action executes; both outcomes are shown and audited accurately.

### MAN-C03 — Generic “Yes” Safety

1. Say “yes” during Idle, Listening without a challenge, Thinking, and Speaking.
2. Repeat after a previous challenge has expired.

Pass: no consequential action executes and no stale challenge is revived.

### MAN-C04 — Disconnect During Confirmation

1. Open a confirmation challenge.
2. disconnect or close the browser before responding.
3. Reconnect and inspect action history.

Pass: no execution occurs; the challenge is rejected/expired according to policy; reconnect does not reopen it as implicitly approved.

### MAN-C05 — Scoped Permissions

1. Enable a read-only capability while leaving related write capability disabled.
2. perform an allowed read.
3. attempt a write through text and voice.

Pass: read works; write is denied before provider invocation; UI shows the two grants independently.

### MAN-C06 — Native-Only Capabilities

1. Open Actions on mobile and desktop web.
2. Inspect calls, SMS, notification access, WhatsApp automation, locked-screen wake, and tray capabilities.

Pass: each unsupported native behavior is labeled `requires_native_bridge` with a plain-language explanation and has no executable toggle/path.

## 8. Memory and Privacy

### MAN-M01 — Remember, Search, Edit, Pin

1. Create synthetic preference, fact, task, and casual memories.
2. Search by exact and semantic phrasing.
3. Edit one item and pin another.

Pass: categories/provenance are visible; search is relevant; edits update results; pinned status is clear.

### MAN-M02 — Degraded Semantic Index

1. Stop or isolate ChromaDB.
2. Browse and edit structured memories.
3. Run semantic search and then restore/rebuild the index.

Pass: structured work remains available; semantic degradation is explicit; rebuild restores search without duplicate/deleted items.

### MAN-M03 — Memory Export

1. Request a full export and review the confirmation.
2. approve, download, and inspect with synthetic data.
3. Wait or advance to artifact expiry.

Pass: export contains current expected records and provenance, excludes secrets/embeddings, and becomes unavailable after expiry.

### MAN-M04 — Hard Delete

1. Create a unique synthetic memory and verify it in direct and semantic search.
2. Request deletion, reject once, then request and approve.
3. Search, export, and run index repair.

Pass: rejection preserves data; approval removes it from UI, SQLite-backed retrieval, Chroma search, and new exports; repair does not resurrect it.

### MAN-M05 — Retention and Consolidation Review

1. Use time-controlled synthetic records around retention boundaries.
2. run retention and consolidation jobs.
3. inspect outcomes and provenance.

Pass: casual records expire at policy boundary, pinned/preferences survive, completed tasks follow configured policy, and summaries remain traceable without duplicates.

## 9. Proactive and Reliability

### MAN-P01 — Reminder Timing

1. Create reminders in the active timezone and across a daylight-saving boundary fixture if supported.
2. Restart the backend before one occurrence.

Pass: next-run display is correct, one event is delivered, and restart does not duplicate it.

### MAN-P02 — Missed Reminder

1. Stop the backend across a scheduled time.
2. restart after the occurrence.

Pass: configured missed-run policy is explained and followed exactly.

### MAN-P03 — Proactive Consequential Follow-Up

1. Trigger a reminder that offers a fake external action.
2. ignore, reject, and approve on separate runs.

Pass: reminder may suggest; no external action runs without a fresh explicit confirmation.

### MAN-R01 — Ollama Failure

1. Stop Ollama during Idle and during a turn.
2. restore it.

Pass: Tara reports model unavailability without hanging; status is degraded; a later turn succeeds.

### MAN-R02 — Chroma/ElevenLabs/Piper Failure Matrix

1. Fail each optional/local provider independently using the documented harness.
2. inspect Listen, Memory, and Settings.

Pass: affected capability degrades accurately; unrelated features remain usable; fallback happens only where defined.

### MAN-R03 — Restart Recovery

1. Restart Next.js and FastAPI during idle, active non-consequential turn, and pending confirmation.
2. reopen the application.

Pass: durable history is consistent, partial work is marked cancelled/failed, pending confirmation does not execute, and scheduler has one leader.

## 10. Accessibility Review

### MAN-X01 — Keyboard-Only

Complete login, route navigation, text turn, memory search/edit, permission review, and fake confirmation without a pointer.

Pass: focus is always visible and ordered; no trap occurs; confirmation focus and return are correct.

### MAN-X02 — Screen Reader

Read the Listen state changes, transcript, confirmation, Memory list, and service status with the declared screen reader.

Pass: semantic state is announced without animation noise; speakers and partial/final text are understandable; labels and errors are specific.

### MAN-X03 — Zoom and Text Scaling

Test desktop at 200% zoom and mobile with large text/accessibility scaling.

Pass: no required content or controls are clipped, overlapped, or accessible only through horizontal scrolling.

### MAN-X04 — Reduced Motion and Contrast

Enable reduced motion and high-contrast/forced-color behavior where supported.

Pass: the Guide Star remains meaningful; confirmation, focus, and status remain visible; no critical information relies on glow.

## 11. Backup, Restore, and Upgrade

### MAN-D01 — Backup and Restore

1. Populate synthetic conversations, memory, schedules, grants, and audit events.
2. create a supported backup.
3. restore into a clean installation and rebuild Chroma if selected.

Pass: database integrity succeeds; durable resources match; semantic search recovers; sessions/secrets follow documented restore policy.

### MAN-D02 — Upgrade and Migration

1. Back up a supported prior schema fixture.
2. apply the release migration and run smoke tests.
3. exercise documented rollback/restore.

Pass: migration preserves expected data and versions; rollback restores a usable prior release without silent loss.

### MAN-D03 — Diagnostics Privacy

1. Seed known canary values representing token, passphrase, transcript, memory, message, and file content.
2. generate a confirmed diagnostics export.
3. search all included files for canaries.

Pass: sensitive canaries are absent; required correlation/status metadata remains useful.

## 12. Manual Release Checklist

- Supported compact and expanded device rows have passed.
- Foreground voice, barge-in, local TTS fallback, and text-only flow have passed.
- Authentication, revocation, Tailscale HTTPS, and reconnect have passed.
- Confirmation rejection, expiry, replay safety, and exact approval have passed.
- Scoped permissions and native-capability labeling have passed.
- Memory search, export, hard delete, retention, and rebuild have passed.
- Accessibility, backup/restore, migration, and diagnostics privacy have passed.
- Measured latency, test hardware, model versions, and known deviations are recorded.
- No unsupported locked-screen, native phone action, or system-tray behavior is presented as implemented.

## 13. M8 Local STT Checks (Pending)

The following checks are pending and must not be marked passed until performed on the declared local host. They require `backend[stt]`, an explicitly provisioned local faster-whisper model outside the repository, and a CPU-first configuration before any optional CUDA validation.

- Start with `TARA_STT_PROVIDER=disabled`; verify authenticated status safely reports disabled STT and readiness remains available when STT is optional.
- Start with an unavailable optional local model, then with `TARA_STT_REQUIRED=true`; verify optional status degrades while required readiness fails without model download.
- Explicitly load the provisioned local model; record first-load latency, device, compute type, CPU, memory, and no network activity.
- Transcribe short English, Hindi, and mixed Hindi/English phrases; exercise silence, background noise, too-short utterances, and the maximum-length utterance.
- Run multiple consecutive turns; cancel queued and active transcription; disconnect during transcription; revoke/expire the session during transcription; and saturate queue limits.
- Simulate provider unavailability and model-load failure; verify only stable safe client errors are shown.
- Measure transcription latency and verify a later turn remains responsive after cancellation or timeout.
- Inspect data and logs: no PCM/audio artifact remains, no transcript appears in normal logs, and authenticated status contains no model path or provider exception.
- Restart the backend and verify readiness does not trigger a model load, inference, download, or network access.

## 14. M9 Local Text-Agent Checks (Pending)

- With `TARA_LLM_PROVIDER=disabled`, submit direct text through an authenticated WebSocket and verify a safe final `agent.error` without a provider call or connection close.
- With a manually provisioned local Ollama model, submit normal text and verify the ordered `agent.started`, `agent.state`, and one final `agent.response`; verify no token/delta, TTS, tool, confirmation, or action event appears.
- Send malformed payloads, repeated idempotency keys, foreign request IDs, cancel requests, disconnects, and session revocation during generation. Verify no duplicate model call, terminal replay, or cross-connection response.
- Complete a voice turn and verify only `transcript.final` starts an agent request. Cancel/fail/timeout STT turns and verify none starts an agent request.
- Toggle optional versus required LLM configuration while the local runtime is unavailable. Verify status is content-minimized, optional readiness remains available, required readiness fails, and no health check triggers generation or model pull.
- Inspect logs, database metadata, and status output using synthetic canaries. Verify prompts, transcript text, provider exception text, URLs, credentials, and model paths are absent.
