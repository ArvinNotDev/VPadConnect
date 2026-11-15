# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


project_root = Path(SPECPATH)
default_settings = Path(
    os.environ.get(
        "VPADCONNECT_DEFAULT_SETTINGS",
        str(project_root / "config" / "settings.conf"),
    )
)

datas = [
    (str(default_settings), "config"),
    *[
        (str(project_root / "profiles" / filename), "profiles")
        for filename in (
            "DualSense.json",
            "Dualshock4.json",
            "Generic.json",
            "Unojoy.json",
        )
    ],
    (str(project_root / "ui" / "themes"), "ui/themes"),
    (str(project_root / "ui" / "assets"), "ui/assets"),
    (str(project_root / "ui" / "web"), "ui/web"),
]

binaries = collect_dynamic_libs("vgamepad")
datas += collect_data_files("vgamepad")
datas += collect_data_files("qtawesome")

hiddenimports = [
    "hid",
    "vgamepad.win",
    "vgamepad.win.vigem_client",
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


a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # Optional packages pulled by Flask's CLI/IPython integration and
    # PyAutoGUI's OpenCV screenshot backend are not used by VPadConnect.
    excludes=[
        "PyQt6",
        "cv2",
        "IPython",
        "ipykernel",
        "matplotlib",
        "pytest",
        "zmq",
    ],
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
