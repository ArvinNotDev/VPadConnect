# VPadConnect Flutter Mobile Companion — UX & Architecture Blueprint

## Product direction

Build a native Flutter companion for Android first. It replaces the browser UI on the phone, not the existing Windows application or its embedded server. The current browser companion remains supported.

The mobile app must reuse the desktop server's existing pairing, controller-state, WebSocket, and remote-action contracts. No desktop-side protocol changes are required for the initial implementation.

## Information architecture

1. **Home** — connection overview, PC identity, quick actions, feature shortcuts, and service health.
2. **Gaming** — virtual controller, Xbox/PlayStation presentation, Standard/Driving/Shooter presets, dual analog sticks, D-pad, face buttons, shoulders, and analog triggers.
3. **Touchpad** — full-screen pointer surface, left/right/middle click, two-finger scroll, pointer sensitivity, and Air Mouse controls.
4. **PC Remote** — keyboard/text input, modifiers and shortcuts, clipboard, media controls, app launch, presentation controls, and power actions.
5. **Settings** — controller layout, touch/motion sensitivity, haptics, screen-awake preference, connection identity, certificate fingerprint, and disconnect.

Use a five-item Material 3 bottom navigation bar in normal mode. Gamepad and Touchpad each provide an immersive full-screen mode that hides navigation chrome while preserving a reachable exit affordance.

## Pairing journey

### First launch

- Show the VPadConnect identity and explain that the phone and PC should be on the same trusted local network.
- Primary action: Scan QR code.
- Secondary action: Enter connection details.
- Ask for a device name with a useful default; do not require account creation.

### QR pairing

The existing desktop creates a URL in this form:

    https://<lan-host>:8765/#pair=<six-digit-code>&fp=<sha256-certificate-fingerprint>

The app must:
- Scan QR codes inside the app with the camera.
- Parse the URL fragment, because the code and fingerprint are intentionally not sent in HTTP requests.
- Accept only HTTPS URLs with a valid host, six-digit code, and 64-character SHA-256 fingerprint.
- Pin the TLS certificate fingerprint before sending pairing credentials.
- Call GET /api/info, confirm the reported server fingerprint, then POST /api/pair.
- Show clear errors for expired codes, incorrect codes, fingerprint mismatches, unreachable hosts, and session-capacity errors.

### Manual pairing

- Accept a host/IP (port defaults to 8765) and the six-digit pairing code.
- Fetch only the public /api/info endpoint to discover the fingerprint. If the certificate is self-signed, capture its DER fingerprint during this one non-credential request and verify it against the fingerprint reported by the server.
- Display the full fingerprint and require the user to compare it with the desktop UI.
- Pin the fingerprint for the actual pairing request and every later HTTPS/WebSocket connection.
- Never silently disable TLS validation.

## Connected experience

### Home

- Persistent connection status and PC name.
- Clear visual separation between Gaming, Touchpad, and PC Remote.
- Quick actions for frequently used tools.
- Explain when ViGEmBus is unavailable: gamepad output is unavailable, but Touchpad and PC Remote remain usable.

### Gaming

- Dark, low-distraction surface with a high-contrast controller.
- Xbox and PlayStation layouts.
- Standard, Driving, and Shooter presets.
- Large, independent multi-touch targets; pointer/touch cancellation must release every held button and recenter each stick.
- Analog triggers for Driving and digital trigger hold for Shooter.
- Motion steering with explicit enable, permission/status feedback, and center calibration.
- Landscape-first optimized arrangement, with a usable portrait layout.

### Touchpad

- A large pointer surface with visible gesture affordances.
- Drag to move, tap for click, two-finger scroll, and explicit click buttons.
- Air Mouse is opt-in and requires a clear calibration state.
- Pointer and scroll sensitivity are adjustable.

### PC Remote

- Separate cards for Keyboard, Clipboard, Media, Quick Launch, Presentation, and Power.
- Disable actions when the desktop has not granted their permission; explain why rather than allowing a failing action.
- Confirm destructive actions such as restart and shutdown.
- Keep clipboard content ephemeral and do not log it.

### Settings

- Group settings by controller, touch/motion, feedback, and connection.
- Display the pinned certificate fingerprint and connected PC identity.
- Offer explicit disconnect and re-pair actions.
- Persist non-sensitive preferences locally; store session tokens and installation identifiers only in platform secure storage.

## Visual system

- Dark-first palette: deep navy surfaces, restrained blue primary accents, cyan for live/active states, amber for warnings, and red only for destructive actions.
- Material 3 foundation with custom VPadConnect components, 20–24 px card radii, consistent 8 px spacing increments, and strong typographic hierarchy.
- Avoid heavy blur, perpetual animations, and excessive gradients. Keep transitions short and purposeful.
- Use subtle surface elevation, thin borders, and lightweight state transitions rather than decorative glass effects.
- Minimum 48 dp touch targets; respect safe areas, keyboard insets, dynamic text, and both orientations.
- Use haptics only for meaningful feedback and allow them to be disabled.

## Technical architecture

mobile_app/ is an independent Flutter client.

- core/: theme and shared primitives.
- models/: validated pairing/session data.
- services/: TLS-pinned pairing, HTTP actions, WebSocket input, and secure local storage.
- screens/: pairing, home, gaming, touchpad, remote, and settings.
- widgets/: reusable controls and status components.

The desktop server remains the source of truth. The app uses:
- GET /api/info
- POST /api/pair
- POST /api/state as a fallback
- GET /api/stream WebSocket for low-latency state snapshots
- POST /api/action
- POST /api/disconnect

The WebSocket protocol begins with {"type":"auth","token":"..."}, receives {"type":"ready"}, and accepts {"type":"state","state":...} messages. Ping messages use {"type":"ping"}.

Controller snapshots must match the existing server schema: mode, buttons, analog, joystick, and mouse. Values must stay within the server's validated ranges. The client should coalesce high-frequency updates, avoid replaying stale relative mouse movement, and always send a neutral snapshot/release state when leaving a control surface or losing focus.

## Delivery phases

1. **Foundation & UX** — this blueprint, Flutter app structure, theme, QR/manual pairing, TLS fingerprint verification, and connected navigation shell.
2. **Gaming input** — WebSocket lifecycle, controller snapshots, multi-touch controls, Xbox/PlayStation layouts, presets, and input-release safety.
3. **Touchpad & motion** — pointer gestures, scroll, click behavior, Air Mouse, steering, and calibration.
4. **PC Remote** — permission-aware action service and keyboard, clipboard, media, launch, presentation, and power screens.
5. **Hardening** — persistence, reconnect states, accessibility, orientation/device testing, unit tests, and Android release pipeline.

Keep each phase independently reviewable. Do not modify the Python core, desktop UI, existing browser UI, protocol, or database as part of the Flutter client work unless a verified compatibility issue requires a separately scoped change.
