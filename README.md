# VPadConnect

<p align="center">
  <img src="ui/assets/vpadconnect-icon.png" alt="VPadConnect application icon" width="88">
</p>

<p align="center">
  <img src="docs/branding/vpadconnect-logo.svg" alt="VPadConnect — Virtual Gamepad. Connected Control." width="640">
</p>

<p align="center"><strong>Virtual Gamepad. Connected Control.</strong></p>

**VPadConnect** is a Windows desktop app that maps physical HID controllers to virtual Xbox/XInput output, mouse controls, and hotkeys. It also includes a browser-based companion for mobile gamepad and PC remote controls.

## Download Beta 3

**[Download VPadConnect 0.2.1 Beta 3](https://github.com/ArvinNotDev/VPadConnect/releases/latest)** · [All releases](https://github.com/ArvinNotDev/VPadConnect/releases)

Download and run `VPadConnect-Setup.exe`. This self-contained Windows x64 installer includes the application and the original ViGEmBus 1.22.0 installer. Python and an internet connection during installation are not required. `SHA256SUMS.txt` contains the installer checksum.

### Requirements and installation

- Windows 10 or later, 64-bit x64.
- Administrator approval for installation and any required driver setup.
- A restart may be required after ViGEmBus installation. Setup never restarts Windows automatically.

Setup lets you choose the installation folder, creates a Start Menu shortcut, and creates a Desktop shortcut by default. You can disable the Desktop shortcut and choose whether VPadConnect launches when setup finishes. The application runs normally as your user after installation.

ViGEmBus is installed automatically when a working compatible driver is not found. Existing working installations are left in place. Mouse controls, hotkeys, and Web Companion features that do not use virtual XInput remain available if driver setup fails. Uninstalling VPadConnect preserves user data and never removes the shared ViGEmBus driver.

For a quick tour, see [Quick start](#quick-start). Read [What's new in this beta](.github/release-notes/0.2.1-beta.3.md) and the [full changelog](CHANGELOG.md).

> **Beta:** Controller and Windows compatibility can vary. Back up important profiles before testing and report reproducible problems. Automated checks do not mean every controller has been manually tested.

## Quick start

1. Run `VPadConnect-Setup.exe` and choose the install folder and shortcut options.
2. Connect a controller and open **Controller Emulation → Add Controller**.
3. Select the HID interface that supplies its input reports.
4. Choose virtual XInput output, mouse control, or hotkeys and configure the mapping.
5. Start emulation. Use **Settings → Developer** for diagnostics, including the live Raw HID terminal.

To use a phone or tablet, open **Web Companion** in the desktop app, start its web server, and open the displayed HTTPS address on a device on the same trusted network. Browser gamepad, touch mouse, scrolling, and permission-controlled PC Remote features are available. A browser may warn about the local self-signed certificate; compare its fingerprint with the one shown by the desktop app.

## Features

- Physical HID controller discovery and configurable profiles.
- Virtual Xbox 360/XInput output through ViGEmBus.
- Controller-driven mouse movement, adjustable mouse deadzone and sensitivity, and hotkeys.
- Responsive Settings sections, persistent reduced-motion preference, and rotating developer log files.
- Live Raw HID terminal with timestamped hexadecimal reports, packet statistics, pause/resume, copy, and capture save.
- Mobile Web Companion with touch gamepad, touch mouse, scrolling, and authenticated persistent input when WebSocket is available.

Virtual XInput requires the system-level ViGEmBus driver. The installer checks its service and Plug and Play state, skips a working installation, and installs its bundled copy when missing. ViGEmBus was retired on November 2, 2023; version 1.22.0 is its final release and will not receive upstream updates. Compatibility with future Windows releases is not guaranteed. VPadConnect is not affiliated with or endorsed by Nefarius Software Solutions e.U.; see the installed `THIRD-PARTY-NOTICES.txt` for its license. Mouse and Web Companion PC Remote features that do not use virtual XInput can be used without the driver.

## Run from source and build

`main.py` starts the PySide6 desktop GUI. This repository does **not** provide a separate headless command-line controller-remapping app; the commands below are for running, testing, and building the GUI from source. These PowerShell commands use Python 3.12 and stable packages from PyPI:

```powershell
git clone https://github.com/ArvinNotDev/VPadConnect.git
cd VPadConnect
py -3.12 -m venv .venv
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install --upgrade pip

# Keep the optional Python 3.15 Qt development index out of this Python 3.12 install.
$requirements = Join-Path $env:TEMP 'vpadconnect-requirements-py312.txt'
$lines = Get-Content requirements.txt | Where-Object { $_ -notmatch '^\s*--extra-index-url\b' }
[System.IO.File]::WriteAllLines($requirements, [string[]]$lines, [System.Text.UTF8Encoding]::new($false))
& $python -m pip install --isolated --index-url https://pypi.org/simple -r $requirements pytest

# Run the desktop GUI.
& $python main.py

# Run the Python and browser regression checks.
& $python -m compileall -q core ui tests main.py
& $python -m pytest -q
node --check ui/web/static/app.js
node --test tests/test_web_frontend.cjs

# Build the Windows x64 one-file executable.
& $python -m PyInstaller --clean --noconfirm VPadConnect_onefile.spec

# Build the all-in-one installer (requires Inno Setup 6).
.\scripts\build_installer.ps1
```

The one-file build is written to `dist\VPadConnect.exe` and is retained as an internal build artifact. The installer build downloads the official ViGEmBus payload to the ignored `build/vendor/` directory, verifies its SHA-256, embeds it, and writes `dist\VPadConnect-Setup.exe` plus `dist\SHA256SUMS.txt`. The final installer is self-contained. The application entry point launches the desktop GUI; no terminal-only controller-remapping commands are currently available.

## Known limitations

- Physical-controller-to-keyboard mapping is not currently available. Web Companion keyboard input is a separate, permission-controlled remote feature.
- ViGEmBus is retired and no longer receives upstream updates. Virtual XInput output requires the bundled v1.22.0 driver to install and work on the PC; compatibility with future Windows releases is not guaranteed.
- If driver installation fails, virtual XInput output is unavailable until it is repaired. Mouse control, hotkeys, and Web Companion features that do not use XInput remain available.
- HID interfaces and behavior vary between controller models; check the [beta notes](.github/release-notes/0.2.1-beta.3.md) for validation details and current limitations.

## Links

- [Download Beta](https://github.com/ArvinNotDev/VPadConnect/releases/latest)
- [Full changelog](CHANGELOG.md)
- [Beta release notes](.github/release-notes/0.2.1-beta.3.md)
- [GitHub repository](https://github.com/ArvinNotDev/VPadConnect)

## License

No license file is currently included in the repository.
