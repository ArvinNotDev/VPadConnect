# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


project_root = Path(SPECPATH)

datas = [
    (str(project_root / "config"), "config"),
    (str(project_root / "profiles"), "profiles"),
    (str(project_root / "ui" / "themes"), "ui/themes"),
    (str(project_root / "ui" / "assets"), "ui/assets"),
    (str(project_root / "ui" / "web"), "ui/web"),
]

# vgamepad loads ViGEmClient.dll via an absolute path relative to its package.
# Include both architecture folders so the bundled package keeps its expected layout.
binaries = collect_dynamic_libs("vgamepad")

hiddenimports = [
    "hid",
    "vgamepad.win",
    "vgamepad.win.vigem_client",
    "vgamepad.win.vigem_commons",
    "vgamepad.win.virtual_gamepad",
    "keyboard",
    "pyautogui",
    "pyperclip",
    "cryptography.hazmat.bindings._rust",
    "qrcode",
    "qrcode.image.pil",
    "flask",
    "werkzeug.serving",
    "simple_websocket",
]

datas += collect_data_files("vgamepad")
datas += collect_data_files("qtawesome")


a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["PyQt6"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VPadConnect",
    icon=str(project_root / "ui" / "assets" / "vpadconnect-icon.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="VPadConnect",
)
