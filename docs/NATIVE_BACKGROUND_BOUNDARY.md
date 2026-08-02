# Native Background Runtime Boundary

Tara is a responsive web application. M11 supports wake-word detection only while a visible foreground page has an existing user-authorized microphone capture session and authenticated WebSocket connection.

The web application does not claim screen-off, locked-device, service-worker audio capture, or native background capability. Those states are explicitly reported as unsupported and must not be inferred from a wake-word event.

Any future native companion requires a separate approved milestone, an OS-specific microphone permission flow, device-local encrypted lifecycle state, explicit background indicator controls, battery/thermal budgets, connection-loss behavior, and a reviewed bridge that cannot invoke agents, tools, confirmations, or actions from audio alone.
