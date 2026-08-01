# Tara Design System

## 1. Design Intent

Tara's visual identity is the Guide Star: still when idle, alive when listening, precise when acting. The interface should feel calm, intimate, and competent rather than conversationally noisy. Voice is primary; text supports awareness, review, correction, and control.

The same semantic tokens, state model, components, accessibility behavior, and content tone serve mobile and desktop. Layout density and navigation placement adapt; identity does not.

## 2. Experience Principles

1. The Guide Star is the primary status indicator, not decoration.
2. The current listening or action state must be understandable without reading a transcript.
3. Confirmation interrupts the normal flow visibly and cannot be confused with ordinary speech.
4. Mobile interaction uses native-like reach, safe areas, sheets, and touch targets.
5. Desktop interaction uses persistent navigation, keyboard access, and denser information layouts.
6. Motion communicates state transitions and audio energy; it never becomes ambient distraction.
7. Offline, denied, and unsupported states are named honestly.

## 3. Guide Star States

| State | Visual behavior | Meaning | Accessible status |
|---|---|---|---|
| Idle | Small still point with a 4–6 second breathing glow | Tara is available but not engaged | “Tara is idle” |
| Listening | Brighter core; thin rays pulse with smoothed input amplitude | Speech capture and VAD are active | “Tara is listening” |
| Thinking | Rays condense inward; restrained slow rotation | Transcription, retrieval, reasoning, or safe tool planning | “Tara is thinking” |
| Speaking | Outward waves follow the TTS envelope | Tara is replying | “Tara is speaking” |
| Confirming | Stable warm/amber star; surrounding motion pauses | Explicit approval or rejection is required | “Confirmation required” |
| Error | Dim outline with restrained error marker | A recoverable operation failed | Specific user-safe error |
| Offline | Faint static outline with no glow | Backend or required local service is unreachable | “Tara is offline” |

### 3.1 Transition Rules

- Only the server-authoritative assistant state changes semantic status during a live session.
- Visual interpolation may smooth amplitude but may not invent intermediate semantic states.
- Confirming always overrides Thinking and Speaking visuals.
- Barge-in transitions Speaking → Listening immediately; stale speaking animation is cancelled.
- Recoverable errors announce the fault and return to Idle after acknowledgement or recovery.
- Offline remains static until a successful health/reconnect signal.
- Reduced-motion mode replaces pulses, waves, contraction, and rotation with color, opacity, and concise text changes.

## 4. Color Tokens

### 4.1 PRD Core Tokens

| Semantic token | Dark value | Use |
|---|---:|---|
| `bg.base` | `#0B0D10` | Application canvas |
| `bg.surface` | `#14171C` | Cards, navigation, sheets |
| `bg.elevated` | `#1B1F26` | Dialogs, popovers, elevated detail |
| `accent.signal` | `#39E6D0` | Guide Star, active controls, focus/link accent |
| `accent.warm` | `#F2A65A` | Confirmation and consequential-action state |
| `text.primary` | `#F4F6F8` | Primary text |
| `text.secondary` | `#9AA3AE` | Supporting text and timestamps |
| `border.hairline` | `#262B33` | Dividers and low-emphasis boundaries |

### 4.2 Derived Semantic Roles

Derived tokens must be contrast-tested; final numeric values are locked during the design-foundation milestone.

| Token | Derivation intent | Use |
|---|---|---|
| `text.muted` | Lower emphasis than `text.secondary` while remaining readable | Metadata and inactive labels |
| `status.success` | Quiet green distinct from signal cyan | Completed safe operations |
| `status.warning` | Based on `accent.warm` | Degraded service and pending review |
| `status.danger` | Restrained red | Errors and destructive consequences |
| `status.info` | Signal cyan at non-glow intensity | Neutral status information |
| `focus.ring` | High-contrast signal cyan | Keyboard focus indicator |
| `overlay.scrim` | Translucent graphite | Modal and sheet scrim |
| `star.core` | `accent.signal` | Guide Star center |
| `star.ray` | Signal cyan with state-specific opacity | Listening/thinking rays |
| `star.confirm` | `accent.warm` | Confirmation state |

Color is never the only state cue. Every warning, confirmation, success, offline state, and permission state includes text and/or iconography.

## 5. Typography

| Role | Family | Weight | Intent |
|---|---|---:|---|
| Display | Inter or approved geometric sans | 600–700 | Guide Star title and rare hero moments |
| Heading | Inter | 600–700 | Screen and section hierarchy |
| Body | Inter | 400–500 | Calm, highly readable interface copy |
| Label | Inter | 500–600 | Controls, navigation, compact metadata |
| Monospace | JetBrains Mono | 400–500 | Logs, exports, command/JSON diagnostics only |

Body line height defaults to 1.5. Interface copy uses sentence case. All-caps is limited to tiny non-critical eyebrow labels and must not carry required meaning.

### 5.1 Type Scale

The implementation milestone will lock responsive values, but roles remain stable:

- Display: hero/Guide Star title only.
- Page title: one per route.
- Section heading: major region within a route.
- Subheading: card/list group.
- Body: default prose and transcript.
- Label: controls and metadata.
- Caption: timestamps and low-priority status.

Mobile sizes may be slightly more compact, but body text must not fall below comfortable mobile reading size and form controls must avoid browser zoom triggers.

## 6. Spacing, Shape, and Elevation

- Base spacing unit: 4 px; common rhythm: 8, 12, 16, 24, 32, and 48 px.
- Touch targets: at least 44 × 44 CSS pixels, with 48 px preferred for primary mobile controls.
- Corners: restrained medium radius for cards, larger radius for sheets, full radius for chips and circular controls.
- Borders: one-pixel hairlines using `border.hairline`; avoid bright boxed grids.
- Shadows: minimal on the dark canvas; use elevation color, outline, and soft shadow together.
- Glow: reserved for the Guide Star and current signal state. Buttons and cards do not compete with it.
- Content width: reading-focused screens remain bounded on wide displays; operational lists may expand into columns.

## 7. Motion System

Framer Motion implements state choreography with the following rules:

- Idle breathing: 4–6 second cycle from the PRD, low amplitude.
- Listening rays: amplitude follows a smoothed and clamped audio envelope, never raw frame jitter.
- Thinking: slow inward contraction and subtle rotation; no high-frequency spinner behavior.
- Speaking waves: follow TTS envelope and stop immediately on cancellation.
- Confirming: motion settles; warm color and stable composition demand attention.
- Navigation: short fades and small directional shifts; avoid full-screen theatrical transitions.
- Bottom sheets: spring motion with bounded overshoot and predictable dismissal.
- Reduced motion: remove continuous motion and spatial travel; retain immediate opacity/color changes.

Motion must never delay input, confirmation, cancellation, or error recovery.

## 8. Responsive Layout Model

Breakpoints are behavioral, not device-brand targets:

| Layout | Approximate range | Navigation | Content behavior |
|---|---:|---|---|
| Compact | Below 768 px | Fixed bottom navigation | Single primary column; transcript and details use sheets |
| Medium | 768–1199 px | Collapsible rail/sidebar | Wider single column or selective two-column regions |
| Expanded | 1200 px and above | Persistent left sidebar | Main workspace plus optional detail panel |

Container queries should refine dense components inside panels. CSS safe-area insets are required in compact installed-PWA mode.

### 8.1 Mobile Native-Like Behavior

- Listen opens as a full-height, distraction-free surface.
- The Guide Star stays in the visual center of the available area, not the raw viewport when bottom navigation or a keyboard is present.
- The live transcript rises as a bottom sheet and preserves access to the star and interruption control.
- Primary controls sit within thumb reach and have visible pressed, disabled, and permission-denied states.
- Navigation has four stable destinations: Listen, Memory, Actions, Settings.
- Back navigation closes transient sheets before leaving the route.
- Screen rotation and virtual-keyboard resize preserve active-session controls.
- Installed mode may feel app-like, but copy must explain that locked-screen/background wake listening is unavailable in the web-only architecture.

### 8.2 Desktop Behavior

- A persistent left sidebar contains identity, four destinations, connection state, and account/session access.
- Listen uses a centered Guide Star workspace with transcript/history in a side or lower region depending on width.
- Memory and Actions use denser list/table patterns with persistent filters where space allows.
- Settings groups operational status and controls into clear sections.
- Keyboard shortcuts may focus Listen, stop playback, open confirmation, and navigate routes, but destructive actions still require explicit confirmation.
- Browser/PWA windows replace the PRD's Flutter desktop shell. Native system-tray docking is not promised without a future host decision.

## 9. Core Screens

### 9.1 Listen

Purpose: default assistant surface and authoritative runtime state.

Required elements:

- Guide Star with text status.
- Service status chip showing ready, degraded, or offline.
- Explicit microphone/session control.
- Live user and assistant transcript with partial/final distinction.
- Barge-in/stop affordance while speaking.
- Confirmation card when a consequential action is pending.
- Clear explanation and recovery action for mic denial, unsupported browser, backend offline, or provider failure.

### 9.2 Memory

Purpose: make retained knowledge visible and controllable.

Required elements:

- Search field and category/status filters.
- Memory items with category, provenance summary, pin, expiry, and task status where relevant.
- Edit and pin controls.
- Deliberate forget/hard-delete flow with confirmation.
- Full export action with privacy warning and export expiry.
- Empty, indexing-degraded, and no-results states.

### 9.3 Actions

Purpose: expose capabilities as independently revocable permissions.

Required elements:

- One row/card per capability with purpose, support state, risk class, and grant state.
- `requires_native_bridge` explanation for unsupported phone-native actions.
- Confirmation badges for external, destructive, and financial classes.
- Recent action history with outcome and safe summary.
- No single blanket “allow all automation” control.

### 9.4 Settings

Purpose: operational health, voice, privacy, connection, appearance, and data controls.

Required elements:

- Service status card covering backend, model, STT, TTS, memory stores, scheduler, and connection.
- Voice provider and local-mode choice.
- Foreground listening sensitivity and end-of-turn timing.
- Cloud-use disclosure and retention controls.
- Tailscale/private connection guidance.
- Session/device management.
- Memory export, diagnostics export, and hard-delete entry points.

## 10. Shared Components

| Component | Responsibility |
|---|---|
| `GuideStar` | Semantic assistant state and amplitude visualization |
| `ServiceStatusChip` | Compact ready/degraded/offline signal |
| `LiveTranscript` | Partial/final transcript, turn grouping, scroll behavior |
| `ConfirmationCard` | Exact action summary with approve/reject controls and expiry |
| `CapabilityPermissionRow` | Scoped permission and support state |
| `MemoryItem` | Content, provenance, retention, pin/edit/delete actions |
| `ServiceStatusCard` | Plain-language dependency health |
| `EmptyState` | Calm explanation and primary recovery action |
| `ErrorNotice` | Safe error, correlation ID access, retry where valid |
| `OfflineBanner` | Persistent connection truth without blocking cached browsing |

shadcn/ui primitives are adapted through Tara tokens; domain components must not expose raw primitive styling decisions to feature screens.

## 11. Confirmation Experience

Confirmation is a distinct safety mode, not an ordinary modal toast.

- The Guide Star changes to warm amber and becomes steady.
- The pending action summary names the exact target and consequence.
- Approve and reject controls are visually distinct, equally reachable, and keyboard accessible.
- Approval never defaults from a timer, silence, Enter key on page load, or reconnect.
- The countdown communicates expiry without creating pressure.
- If action arguments change, the current challenge disappears and a new summary is required.
- Completion reports actual outcome; timeout with unknown result is labeled uncertain, not failed or successful.

## 12. Content and Persona

Tara's copy is warm, composed, and quietly confident. It is concise without sounding abrupt.

- Prefer “I couldn't reach the local model. Try again?” over technical stack traces.
- Prefer “Microphone access is off” over ambiguous “Permission error.”
- State uncertainty directly: “I'm not sure I understood. Did you mean…?”
- Confirmation copy is exact and neutral, not persuasive.
- Do not anthropomorphize failures or imply that unsupported capabilities are temporarily broken.
- Avoid exclamation-heavy, chirpy, or mascot-like language.

## 13. Accessibility

- Meet WCAG 2.2 AA for contrast, keyboard operation, focus visibility, semantics, labels, errors, and target size.
- Provide a text-mode assistant path for users who cannot or do not want to use audio.
- Guide Star state changes use an appropriately throttled live region; amplitude animation is never announced.
- Transcripts distinguish speaker and partial/final state without relying on color.
- Confirmation receives managed focus, is fully operable by keyboard, and returns focus predictably.
- All icon-only controls have accessible names and visible tooltips on pointer devices.
- Screen readers receive status text rather than decorative star geometry.
- Reduced motion, high contrast, text scaling, zoom, and browser font overrides must remain usable.

## 14. Loading, Empty, Error, and Offline States

Every screen defines all four states:

- Loading: skeleton or compact progress indicator without star-state ambiguity.
- Empty: explain what will appear and provide one relevant action.
- Error: state what failed, whether data is safe, and whether retry is valid.
- Offline: cached durable data may remain readable; mutations and live voice are disabled with explanation.

The Guide Star's Error/Offline state is reserved for assistant availability. A failed memory search does not force the global star into Error if the assistant remains usable.

## 15. Design Governance

- Semantic tokens are the only source for product color, typography, spacing, radius, shadow, and motion roles.
- New components must demonstrate compact and expanded layouts, keyboard operation, reduced motion, and all async states.
- Screenshots and automated visual regression cover all Guide Star states and both shell layouts.
- Changes to Guide Star semantics, confirmation visuals, or core token names require an architecture decision.
- Light mode is a compatible future token set, not a v1 requirement unless separately approved.
