<p align="center">
  <img src="ui/assets/vpadconnect-icon.png" alt="VPadConnect application icon" width="88">
</p>

<p align="center">
  <img src="docs/branding/vpadconnect-logo.svg" alt="VPadConnect — Virtual Gamepad. Connected Control." width="640">
</p>

<h3 align="center">Virtual Gamepad. Connected Control.</h3>

<p align="center">
  Turn physical controllers and phones into virtual Xbox controllers, use them for mouse input, or control your Windows PC from a phone — all from one desktop application.
</p>

<p align="center">
  <a href="https://github.com/ArvinNotDev/VPadConnect/releases/latest"><img src="https://img.shields.io/github/v/release/ArvinNotDev/VPadConnect?include_prereleases&label=latest%20release" alt="Latest release"></a>
  <a href="https://github.com/ArvinNotDev/VPadConnect/releases"><img src="https://img.shields.io/github/downloads/ArvinNotDev/VPadConnect/total?label=downloads" alt="Total downloads"></a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2B-0078D6" alt="Windows 10 or later">
  <img src="https://img.shields.io/badge/architecture-x64-64748b" alt="64-bit x64">
  <img src="https://img.shields.io/badge/status-pre--1.0%20beta-orange" alt="Pre-1.0 beta">
</p>

<p align="center">
  <a href="#download">Download</a> ·
  <a href="#features">Features</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#web-companion">Web Companion</a> ·
  <a href="#security-and-privacy">Security</a> ·
  <a href="#build-from-source">Build from source</a> ·
  <a href="#troubleshooting">Troubleshooting</a>
</p>

---

## Overview

**VPadConnect** is a Windows desktop application for working with physical HID controllers and browser-based remote input.

It combines three workflows:

- **Controller emulation:** read supported physical HID controllers, configure their mappings, and send input to a virtual Xbox 360 controller through ViGEmBus.
- **Desktop input:** use a physical controller for mouse movement and configured hotkeys without requiring virtual XInput output.
- **Web Companion:** connect a phone, tablet, or another browser over your local network. Use a touch gamepad, touchpad, motion controls, and permission-controlled Windows PC actions.

The desktop application is built with **Python and PySide6**. The Web Companion runs in a browser and does not require a separate Android or iOS app.

> [!IMPORTANT]
> VPadConnect is currently a **pre-1.0 beta**. Controller behavior depends on the device, its HID interface, connection type, and Windows environment. Automated tests do not mean every controller has been physically tested. Review the compatibility notes below before relying on a feature.

## Download

<p align="center">
  <a href="https://github.com/ArvinNotDev/VPadConnect/releases/latest">
    <img src="https://img.shields.io/badge/Download-Windows%20Installer-2563eb?style=for-the-badge&logo=windows" alt="Download Windows installer">
  </a>
</p>

The recommended way to install VPadConnect is the **Windows x64 setup installer**.

1. Open the [latest release](https://github.com/ArvinNotDev/VPadConnect/releases/latest).
2. Download <code>VPadConnect-Setup.exe</code>.
3. Run the installer and follow the setup prompts.

The installer is self-contained: it includes the application and the official ViGEmBus 1.22.0 installer. Python and an internet connection during installation are not required. The release also provides <code>SHA256SUMS.txt</code> for checksum verification.

### System requirements

| Component | Requirement |
|---|---|
| Operating system | Windows 10 or later |
| Architecture | 64-bit x64 |
| Permissions | Administrator approval for setup and any required driver installation |
| Virtual Xbox output | ViGEmBus 1.22.0, installed by setup when a working compatible installation is not found |
| Phone / tablet | A modern browser and access to the same trusted local network as the PC |

A Windows restart may be required after driver installation. Setup does **not** restart Windows automatically.

### What the installer does

- Lets you choose the installation directory.
- Creates a Start Menu shortcut.
- Creates a Desktop shortcut by default; this can be disabled.
- Lets you choose whether VPadConnect launches after setup.
- Detects an existing working ViGEmBus installation and leaves it in place.
- Installs its bundled ViGEmBus copy only when a working compatible driver is not found.
- Preserves user data when VPadConnect is uninstalled.
- Does not remove the shared ViGEmBus driver during application uninstall.

The installed application runs as your regular Windows user. Administrator approval is requested only for setup operations that require elevation.

## Features

### Desktop controller emulation

- Discover physical HID devices and select the interface that provides the controller's input reports.
- Configure controller mappings through the desktop interface.
- Create virtual Xbox 360 / XInput output using ViGEmBus.
- Use controller input for mouse movement with adjustable sensitivity and deadzone.
- Configure controller-triggered hotkeys.
- Keep controller profiles and application settings between launches.
- Use developer diagnostics when investigating device or report-handling issues.

### Sony controller features

VPadConnect contains dedicated profiles and controller-specific handling for Sony devices.

| Controller | Available project features | Compatibility notes |
|---|---|---|
| **DualSense** | Controller input, gyro steering, vibration / rumble, and Lightbar controls | Existing DualSense gyro, vibration, and Lightbar functionality is retained. Lightbar output includes USB and Bluetooth report handling. |
| **DualShock 4** | Controller input, gyro steering, vibration / rumble, and battery / charging status detection | Wired controller handling is retained. The Beta 3 gyro and rumble implementation has **not yet been physically tested with a DualShock 4**. |
| **Generic HID** | Generic controller profile and selectable HID input interfaces | Actual compatibility depends on the device's report format and available controls. |

The installer also includes the project's built-in <code>Generic</code> and <code>Unojoy</code> profiles. A profile being present does not imply that every device using a similar name or protocol has been validated.

### Web Companion

Use your phone or tablet as a wireless input device through its browser:

- Touchscreen virtual gamepad with standard, driving, and shooter layouts.
- Xbox-style and PlayStation-style controller presentation.
- Touch mouse with adjustable sensitivity.
- Adjustable scrolling speed and reverse-scroll option.
- Motion-based steering for supported mobile browsers.
- Six-axis Air Mouse using the phone's motion sensors, with calibration and sensitivity controls.
- Focus mode for a larger, distraction-free controller surface.
- Browser-local preferences for supported interface settings.
- Multiple paired browser sessions, with up to eight active controllers.

When ViGEmBus is unavailable, virtual gamepad output is disabled, but the touch mouse and supported PC Remote features remain usable.

### PC Remote

The Web Companion can also perform selected Windows actions. These are separate from gamepad input and are controlled by permission categories in the desktop application.

| Permission category | Examples |
|---|---|
| Keyboard | Send text, press supported keys, use predefined shortcuts, and hold modifiers |
| Media | Volume up/down, mute, playback, previous/next track, and stop |
| Clipboard | Send text to the PC clipboard or read clipboard text |
| Application launch | Open the browser, File Explorer, Calculator, Notepad, or Downloads |
| Presentation | Next / previous slide, start presentation, end presentation, and black screen |
| Power | Lock, sleep, turn off the display, log off, restart, or shut down Windows |

Review the PC Remote permissions in VPadConnect before pairing a device. Disable any category you do not intend to use. Power actions can interrupt active work, and some actions cannot be undone.

## Quick start

### 1. Install VPadConnect

Download and run <code>VPadConnect-Setup.exe</code> from the [latest release](https://github.com/ArvinNotDev/VPadConnect/releases/latest). Complete setup and restart Windows if the driver installer requests it.

### 2. Connect a controller

Connect your controller using USB or Bluetooth, then launch VPadConnect.

Open **Controller Emulation → Add Controller**, select the HID interface that supplies the input reports, and configure the desired mapping.

### 3. Choose an output

Select the workflow you need:

- **Virtual gamepad:** create Xbox 360 / XInput output. This requires a working ViGEmBus installation.
- **Mouse control:** use controller movement and buttons for desktop mouse input.
- **Hotkeys:** configure supported controller-triggered actions.

Start emulation when the mapping is ready.

### 4. Connect a phone or tablet

1. Open **Web Companion** in the desktop app.
2. Review the PC Remote permission categories.
3. Start the Web Companion server.
4. Open the displayed HTTPS address on a phone or tablet connected to the same trusted local network.
5. Scan the QR code or enter the six-digit pairing code shown by the desktop app.
6. Verify the displayed certificate fingerprint when your browser warns about the local self-signed certificate.
7. Complete pairing and choose the Gamepad, Mouse, or PC Remote controls you need.

The default Web Companion port is <code>8765</code>. The server can request a narrowly scoped Windows Firewall rule for the Private network profile.

> [!NOTE]
> The Web Companion uses a local self-signed TLS certificate. A browser security warning can be expected. Do not bypass certificate warnings on an unfamiliar network: verify the SHA-256 fingerprint against the value displayed by VPadConnect first.

## Security and privacy

The Web Companion is designed for use on a **trusted local network**, not as a public internet service.

The implementation includes:

- HTTPS with a local, persistent certificate and a minimum TLS version of 1.2.
- A SHA-256 certificate fingerprint displayed by the desktop app.
- QR pairing data that includes the certificate fingerprint.
- A temporary six-digit pairing code that expires after five minutes.
- Pairing-attempt throttling per client address.
- Random per-session bearer tokens for authenticated browser sessions.
- An authenticated persistent WebSocket input stream when available, with an HTTP state fallback.
- Permission checks for keyboard, media, clipboard, app-launch, presentation, and power actions.
- Validation and size limits for browser input and remote-action requests.
- Idle-session expiry and cleanup of held controller, mouse, and keyboard inputs on disconnect.
- Browser security headers, including a restrictive Content Security Policy and <code>no-store</code> caching.

The server accepts up to **eight active browser sessions**. Inactive sessions expire after five minutes. Pairing is limited to 12 attempts per client address per minute.

### Network safety

- Use VPadConnect only on a network you trust.
- Do not configure router port forwarding for the Web Companion.
- Do not expose its listening port directly to the public internet.
- Keep remote permissions disabled for actions you do not need.
- Treat a paired browser like a device with access to the permissions enabled on the PC.
- Stop the Web Companion server when you are finished using it.

These controls reduce risk but do not make an untrusted network safe. Your network configuration and the permissions you enable remain important.

## ViGEmBus and virtual XInput

Virtual Xbox 360 output is provided through **ViGEmBus**.

ViGEmBus was retired on **November 2, 2023**. Version **1.22.0** is its final upstream release and will not receive upstream updates. Compatibility with future Windows releases is therefore not guaranteed.

VPadConnect bundles the official ViGEmBus 1.22.0 installer and checks for an existing working installation before attempting setup. The driver is a system-level component shared with other applications; uninstalling VPadConnect intentionally leaves it installed.

The following features do not require ViGEmBus:

- Physical HID discovery and report reading.
- Desktop mouse control.
- Supported controller hotkeys.
- Web Companion touch mouse.
- Permission-controlled PC Remote actions.

Only virtual Xbox / XInput output depends on the driver.

VPadConnect is not affiliated with or endorsed by Nefarius Software Solutions e.U. See the installed <code>THIRD-PARTY-NOTICES.txt</code> for the bundled driver's license and notice.

## Build from source

### Development environment

The commands below use **PowerShell** and Python 3.12 on Windows.

~~~powershell
git clone https://github.com/ArvinNotDev/VPadConnect.git
cd VPadConnect

py -3.12 -m venv .venv
$python = ".\.venv\Scripts\python.exe"

& $python -m pip install --upgrade pip

# Exclude the optional Qt development index from the Python 3.12 install.
$requirements = Join-Path $env:TEMP 'vpadconnect-requirements-py312.txt'
$lines = Get-Content requirements.txt | Where-Object { $_ -notmatch '^\s*--extra-index-url\b' }
[System.IO.File]::WriteAllLines(
    $requirements,
    [string[]]$lines,
    [System.Text.UTF8Encoding]::new($false)
)

& $python -m pip install --isolated --index-url https://pypi.org/simple -r $requirements pytest
~~~

### Run the application

~~~powershell
& $python main.py
~~~

<code>main.py</code> launches the PySide6 desktop GUI. This repository does not provide a separate headless command-line controller-remapping application.

### Run checks

~~~powershell
# Python syntax / bytecode compilation
& $python -m compileall -q core ui tests main.py

# Python regression tests
& $python -m pytest -q

# Browser JavaScript syntax and regression tests
node --check ui/web/static/app.js
node --test tests/test_web_frontend.cjs
~~~

### Build the Windows executable

~~~powershell
& $python -m PyInstaller --clean --noconfirm VPadConnect_onefile.spec
~~~

The one-file executable is written to <code>dist\VPadConnect.exe</code>.

### Build the installer

Install Inno Setup 6, then run:

~~~powershell
.\scripts\build_installer.ps1
~~~

The installer build downloads the official ViGEmBus payload into the ignored <code>build/vendor/</code> directory, verifies its pinned SHA-256 value, embeds it, and writes:

- <code>dist\VPadConnect-Setup.exe</code>
- <code>dist\SHA256SUMS.txt</code>

The final setup installer is self-contained. The one-file executable is an internal build artifact; the setup installer is the recommended distribution for end users.

## Project structure

| Path | Purpose |
|---|---|
| <code>main.py</code> | Desktop application entry point |
| <code>core/</code> | HID handling, controller mapping, emulation, and Web Companion services |
| <code>ui/</code> | PySide6 desktop interface and browser companion assets |
| <code>profiles/</code> | Built-in controller profiles |
| <code>config/</code> | Default application configuration |
| <code>scripts/</code> | Installer build and distribution scripts |
| <code>tests/</code> | Python and browser-side regression tests |
| <code>docs/branding/</code> | Project branding assets |
| <code>.github/release-notes/</code> | Per-release notes |

## Troubleshooting

<details>
<summary><strong>My controller is not detected</strong></summary>

- Confirm that Windows recognizes the controller.
- Check that the controller is connected and awake.
- In **Add Controller**, select the HID interface that actually provides the input reports. Some devices expose more than one interface.
- Disconnect and reconnect the controller, then reopen the device list.
- Check the developer diagnostics and Raw HID terminal for incoming reports.

</details>

<details>
<summary><strong>Virtual Xbox / XInput output is unavailable</strong></summary>

- Confirm that ViGEmBus is installed and working.
- Complete any driver setup prompt and restart Windows if requested.
- Open the controller-emulation area again after the driver is available.
- Remember that mouse control and PC Remote features do not require ViGEmBus.

</details>

<details>
<summary><strong>My phone cannot open the Web Companion page</strong></summary>

- Make sure both devices are on the same trusted local network.
- Check that the PC is using the Private network profile and that Windows Firewall allows the selected port.
- Check whether guest Wi-Fi or access-point isolation prevents devices from communicating.
- Confirm that the displayed IP address is reachable from the phone.
- Check whether another application is already using the configured port.

</details>

<details>
<summary><strong>The browser shows a certificate warning</strong></summary>

The Web Companion uses a local self-signed certificate. Verify its SHA-256 fingerprint against the fingerprint shown in the desktop app before proceeding. Do not accept a certificate you cannot verify.

</details>

<details>
<summary><strong>Gyro steering or Air Mouse does not respond</strong></summary>

- Use a browser that supports the required device-motion APIs.
- Grant motion-sensor permission when the browser or operating system requests it.
- Keep the phone on the intended orientation and calibrate while holding it still.
- Sensor availability and permission behavior vary by browser and device.

</details>

## Compatibility and known limitations

- VPadConnect is beta software; behavior can vary across Windows versions, controller revisions, USB/Bluetooth modes, and HID interfaces.
- Generic HID support depends on the device's report format. Not every controller can be expected to work automatically.
- DualShock 4 gyro steering and rumble were added in Beta 3 but have not yet been physically validated with a DualShock 4 controller.
- ViGEmBus is retired; virtual XInput compatibility with future Windows releases is not guaranteed.
- Physical-controller-to-keyboard mapping is not currently available as a general mapping output. Keyboard actions in Web Companion are a separate, permission-controlled PC Remote feature.
- A failed ViGEmBus installation prevents virtual XInput output, but does not by itself disable mouse control or Web Companion PC Remote features.

## Contributing and reporting issues

Bug reports and focused contributions are welcome.

Before opening an issue, check whether it has already been reported. A useful bug report includes:

- VPadConnect version and Windows version.
- Controller model and connection type (USB or Bluetooth).
- The HID interface selected in the application, when relevant.
- Steps to reproduce, expected behavior, and actual behavior.
- Relevant application logs or Raw HID output, with personal or sensitive information removed.

Please avoid attaching pairing codes, session tokens, private TLS keys, or other credentials to issues.

- [Report a bug or request a feature](https://github.com/ArvinNotDev/VPadConnect/issues)
- [Browse releases](https://github.com/ArvinNotDev/VPadConnect/releases)
- [Read the changelog](CHANGELOG.md)

## Release notes

- [Latest release — VPadConnect 0.2.1 Beta 3](https://github.com/ArvinNotDev/VPadConnect/releases/tag/0.2.1-beta.3)
- [Beta 3 release notes](.github/release-notes/0.2.1-beta.3.md)
- [Full changelog](CHANGELOG.md)

## License

**No <code>LICENSE</code> file is currently included in this repository.** Until a license is added, do not assume that the code may be reused, modified, or redistributed simply because it is publicly visible on GitHub. The bundled third-party components retain their own licenses and notices.

---

<p align="center">
  <strong>VPadConnect</strong><br>
  <sub>Virtual Gamepad. Connected Control.</sub>
</p>