# Changelog

All notable user-facing changes to VPadConnect are documented
here. Version numbers follow semantic-versioning conventions where practical.

## [0.2.1-beta.3] — 2026-11-04

### New features

- Added DualShock 4 gyro steering and vibration/rumble support.
- Improved DualShock 4 battery percentage and charging status detection.

### Improvements and compatibility

- Improved Sony controller HID report handling and added DualShock 4-specific
  calibration and motion processing.
- Preserved existing DualSense gyro, vibration, and Lightbar functionality.
- Preserved wired DualShock 4 controls.
- Continued bundling the official ViGEmBus 1.22.0 installer with the existing
  Inno Setup flow, including detection of an already working driver and
  installation only when required.

### Validation

See the release notes for build results and environment-specific test limits.

## [0.2.1-beta.2] — 2026-10-30

### Windows installer

- Added `VPadConnect-Setup.exe`, an administrator-assisted Inno Setup installer
  with a selectable install folder, Start Menu shortcut, optional Desktop
  shortcut, and optional launch after setup.
- Bundled the original signed ViGEmBus 1.22.0 installer. Setup checks the driver
  service and Plug and Play device state, installs the driver when missing, and
  reports when Windows needs a restart or the driver could not be confirmed.
- Moved installed-build settings, profiles, logs, and persistent Web Companion
  data to `%LOCALAPPDATA%\VPadConnect`. Existing beside-the-executable data is
  copied without overwriting conflicts or deleting the source.
- Uninstall preserves user data and never removes ViGEmBus. Added the driver's
  BSD 3-Clause notice to the installer and installed files.
- Documented the retirement of ViGEmBus and its final upstream release.

### Validation

- `python -m compileall -q core ui tests main.py` — passed.
- `python -m pytest -q` — 100 passed.
- `node --check ui/web/static/app.js` — passed.
- `node --test tests/test_web_frontend.cjs` — 32 passed.
- PyInstaller and Inno Setup builds completed; the official ViGEmBus payload
  checksum and Authenticode signature were verified.
- Driver skip/success/failure/restart handling passed mocked Windows
  orchestration tests. No kernel driver was installed or changed on the build
  host; isolated installer install/upgrade/uninstall tests remain unverified.
- The silent switches match the Microsoft WinGet manifest; the official driver
  installer was not executed because no isolated Windows environment was
  available.

## [0.2.1-beta.1] — 2026-10-30

This is the first pre-1.0 beta under the VPadConnect version line. It gathers the
current desktop and Web Companion work into a fresh downloadable Windows release.

### Raw HID live terminal and developer diagnostics

- Added a dedicated dark live terminal for timestamped hexadecimal HID reports,
  with packet count, receive rate, last-report size, and controller name.
- Added pause/resume, clear, copy-latest, save-capture, and optional auto-scroll
  controls. Terminal history is bounded to 1,600 lines.
- Limited UI report delivery to 30 updates per second and disabled delivery while
  the terminal is hidden, avoiding unnecessary pressure on the UI thread.
- Kept file diagnostics separate, rate-limited, and rotated to bound disk usage.
- Made Raw HID timestamps use an explicit UTC-to-local conversion for Windows compatibility.

### Settings and input responsiveness

- Made Device, UI, and Developer Settings scroll independently in compact windows.
- Added a persistent Reduce interface animations option and an adjustable mouse
  deadzone for physical-controller mouse mode.
- Removed the redundant OS cursor-position query before every relative mouse move,
  while retaining recovery from PyAutoGUI's fail-safe corner.
- Added visible developer logging controls for choosing, opening, and clearing
  diagnostic logs.

### Web Companion and desktop experience

- Improved the mobile Web Companion's touch gamepad, touch mouse, scrolling,
  PC Remote, connection handling, and browser-local preferences.
- Kept the input stream persistent over an authenticated WebSocket when available,
  with an HTTP state fallback and cleanup of held inputs on disconnect.
- Added the current indigo/cyan desktop motion polish and reduced-motion support.
- Gated virtual XInput output on the optional ViGEmBus driver while keeping
  touch mouse and PC Remote features available without it.

### Distribution and validation

- Reset the application version line to `0.2.1-beta.1` to mark the VPadConnect
  beta as a pre-1.0 release.
- The release provides a Windows x64 **one-file** `VPadConnect.exe` and a SHA-256
  checksum file; see the release notes for local build validation results.
- This is a beta: automated checks do not replace testing on every Windows PC
  and with every physical controller. Please report reproducible issues.

## [Unreleased]

_No unreleased changes._

## [2.0.8] — 2026-09-26

### What's new

- Added per-controller DualSense and DualSense Edge Lightbar color settings,
  saved and restored using each controller's stable HID identity when available.
- Added optional battery-level colors and a charging indication for the
  Lightbar.
- Added DualSense USB and Bluetooth Lightbar output reports with Bluetooth
  sequence and CRC handling.

### Validation

- Added focused checks for USB/Bluetooth Lightbar reports, Bluetooth CRC and
  sequence handling, per-controller settings persistence, and temporary
  battery colors.

## [2.0.7] — 2026-09-17

### What's new

- Reworked HID input timing for a more responsive active-input path.
- Removed the unnecessary wait after every received HID report.
- Added adaptive idle backoff so empty HID reads do not become a busy loop or
  unnecessarily consume CPU.
- Improved mouse mode responsiveness by reducing motion smoothing latency.
- Added a fixed 10% mouse deadzone to filter tiny stick noise and accidental
  cursor movement.
- Remapped deadzone output to preserve full mouse speed after the deadzone.
- Kept time-based motion, fractional-pixel accumulation, nonlinear response,
  D-Pad movement, and controller-button mouse clicks together in one smoother
  mouse path.

### Reliability and compatibility

- Added validation coverage for mouse deadzone behavior and input timing.
- Existing `polling_rate` settings remain readable and are normalized to the
  clearer `poll_interval_ms` setting.
- Keyboard emulation remains intentionally disabled in this release.
- Renamed PyInstaller specification files from the historical
  historical `UniversalRemapper` name to `VPadConnect` during an earlier release.

### Validation

- `python -m pytest -q` — 26 tests passed.
- `python -m compileall -q core tests ui` — passed.
- `git diff --check` — passed.

## [2.0.6] — 2026-09-01

- Fixed DualShock 4 connection stability by limiting the DualSense-only
  feature-report request to DualSense devices.
- Preserved DualSense feature reports used for additional data such as battery
  status.

## [2.0.5] — 2026-08-26

- Added live vibration settings and XInput vibration testing.

[0.2.1-beta.1]: https://github.com/ArvinNotDev/VPadConnect/releases/tag/v0.2.1-beta.1
[0.2.1-beta.3]: https://github.com/ArvinNotDev/VPadConnect/releases/tag/v0.2.1-beta.3
[2.0.8]: https://github.com/ArvinNotDev/VPadConnect/tree/3d4b900c1725c762c184bdd638288e07ebbcd906
[2.0.7]: https://github.com/ArvinNotDev/VPadConnect/tree/58d071976700fab8bd41c7e1a3b8ecf098c29c4d
[2.0.6]: https://github.com/ArvinNotDev/VPadConnect/tree/f66e8f601f74bb27e0f149e615f17d93c03d4223
[2.0.5]: https://github.com/ArvinNotDev/VPadConnect/tree/399aa5efb165f08b3e415aa9473898740204c120
