"""Allowlisted, permission-gated Windows operations for authenticated remote sessions."""
from __future__ import annotations
import ctypes
import os
import platform
import subprocess
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from core.remote_protocol import ACTION_PERMISSION, KEY_NAMES, MODIFIER_KEYS, SHORTCUTS, validate_remote_request
from core.utils.paths import data_path

DEFAULT_REMOTE_PERMISSIONS = {"keyboard": True, "media": True, "clipboard": True, "app_launch": True, "presentation": True, "power": True}
PERMISSION_FILE = data_path("remote_permissions.json")
_PERMISSION_LOCK = threading.RLock()
_MEDIA_VKEYS = {"volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD, "play_pause": 0xB3, "previous_track": 0xB1, "next_track": 0xB0, "stop": 0xB2}


PERMISSION_SCHEMA_VERSION = 2
DEVICE_PERMISSION_SCHEMA_VERSION = 1
DEVICE_PERMISSION_FILE = data_path("remote_device_permissions.json")
_DEVICE_PERMISSION_LOCK = threading.RLock()


def _valid_remote_device_id(device_id: str) -> bool:
    import re

    return bool(re.fullmatch(r"[a-f0-9]{32}", str(device_id or "").lower()))


def _normalize_remote_permissions(permissions: dict[str, Any] | None) -> dict[str, bool]:
    normalized = dict(DEFAULT_REMOTE_PERMISSIONS)
    if isinstance(permissions, dict):
        for name in normalized:
            if type(permissions.get(name)) is bool:
                normalized[name] = permissions[name]
    return normalized


def _normalize_device_remote_permissions(
    permissions: dict[str, Any] | None,
) -> dict[str, bool]:
    """Keep screen sharing separate from PC actions and deny it by default."""
    normalized = _normalize_remote_permissions(permissions)
    normalized["screen_view"] = False
    if isinstance(permissions, dict) and type(permissions.get("screen_view")) is bool:
        normalized["screen_view"] = permissions["screen_view"]
    return normalized


def load_device_remote_permissions(
    device_id: str, path: str | Path = DEVICE_PERMISSION_FILE
) -> dict[str, bool]:
    """Load one browser installation's permissions, falling back to legacy defaults."""
    defaults = _normalize_device_remote_permissions(load_remote_permissions())
    normalized_id = str(device_id or "").lower()
    if not _valid_remote_device_id(normalized_id):
        return defaults

    import json

    with _DEVICE_PERMISSION_LOCK:
        try:
            with Path(path).open("r", encoding="utf-8") as stream:
                document = json.load(stream)
        except (OSError, ValueError, TypeError):
            return defaults

    if not isinstance(document, dict):
        return defaults
    if document.get("schema_version") != DEVICE_PERMISSION_SCHEMA_VERSION:
        return defaults
    devices = document.get("devices")
    if not isinstance(devices, dict):
        return defaults
    stored = devices.get(normalized_id)
    return _normalize_device_remote_permissions(stored) if isinstance(stored, dict) else defaults


def save_device_remote_permissions(
    device_id: str,
    permissions: dict[str, Any],
    path: str | Path = DEVICE_PERMISSION_FILE,
) -> None:
    """Atomically persist permissions for one browser installation."""
    if not _valid_remote_device_id(str(device_id or "").lower()):
        raise ValueError("Invalid remote device identifier")

    import json
    import tempfile

    normalized_id = str(device_id).lower()
    normalized = _normalize_device_remote_permissions(permissions)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with _DEVICE_PERMISSION_LOCK:
        try:
            with target.open("r", encoding="utf-8") as stream:
                existing = json.load(stream)
        except (OSError, ValueError, TypeError):
            existing = {}

        devices = existing.get("devices", {}) if isinstance(existing, dict) else {}
        if not isinstance(devices, dict):
            devices = {}
        devices = {
            key: value for key, value in devices.items()
            if _valid_remote_device_id(str(key).lower()) and isinstance(value, dict)
        }
        devices[normalized_id] = normalized
        # Keep the settings file bounded for long-lived installations.
        if len(devices) > 256:
            devices = dict(list(devices.items())[-256:])

        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=target.parent,
                prefix=target.name + ".", suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(
                    {
                        "schema_version": DEVICE_PERMISSION_SCHEMA_VERSION,
                        "devices": devices,
                    },
                    stream,
                    indent=2,
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def load_remote_permissions(path: str | Path = PERMISSION_FILE) -> dict[str, bool]:
    import json
    result = dict(DEFAULT_REMOTE_PERMISSIONS)
    target = Path(path)
    try:
        with target.open("r", encoding="utf-8") as stream:
            loaded = json.load(stream)
    except (OSError, ValueError, TypeError):
        return result

    if not isinstance(loaded, dict):
        return result

    # Files created by older VPadConnect versions had no schema version and
    # defaulted every remote permission to off. Migrate them once to the new
    # defaults; subsequent user edits are stored with the current schema version.
    if loaded.get("schema_version") != PERMISSION_SCHEMA_VERSION:
        save_remote_permissions(result, target)
        return result

    for name in result:
        if isinstance(loaded.get(name), bool):
            result[name] = loaded[name]
    return result


def save_remote_permissions(permissions: dict[str, bool], path: str | Path = PERMISSION_FILE) -> None:
    import json
    import tempfile
    normalized = dict(DEFAULT_REMOTE_PERMISSIONS)
    for name in normalized:
        if isinstance(permissions.get(name), bool):
            normalized[name] = permissions[name]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=target.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"schema_version": PERMISSION_SCHEMA_VERSION, **normalized}, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def remote_capabilities(permissions: dict[str, bool] | None = None) -> dict[str, bool]:
    current = dict(DEFAULT_REMOTE_PERMISSIONS)
    if permissions:
        for name in current:
            if isinstance(permissions.get(name), bool):
                current[name] = permissions[name]
    return {"pc_status": True, "keyboard": current["keyboard"], "media": current["media"], "clipboard": current["clipboard"], "app_launch": current["app_launch"], "presentation": current["presentation"], "power": current["power"]}


def _keyboard_call(method: str, value: str) -> None:
    if os.name != "nt":
        raise RuntimeError("Keyboard injection is supported only on Windows")
    import keyboard
    getattr(keyboard, method)(value)


def _media_key(command: str) -> None:
    if os.name != "nt":
        raise RuntimeError("System media keys are supported only on Windows")
    user32 = ctypes.windll.user32
    key = _MEDIA_VKEYS[command]
    user32.keybd_event(key, 0, 0, 0)
    user32.keybd_event(key, 0, 2, 0)


def _clipboard_copy(text: str) -> None:
    if os.name != "nt":
        raise RuntimeError("PC clipboard is supported only on Windows")
    import pyperclip
    pyperclip.copy(text)


def _clipboard_paste() -> str:
    if os.name != "nt":
        raise RuntimeError("PC clipboard is supported only on Windows")
    import pyperclip
    value = pyperclip.paste()
    return value if isinstance(value, str) else ""


def _launch_app(app: str) -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("Application launching is supported only on Windows")
    if app == "browser":
        if not webbrowser.open("about:blank", new=2):
            raise RuntimeError("The default browser could not be opened")
    elif app == "explorer":
        subprocess.Popen(["explorer.exe"], shell=False)
    elif app == "calculator":
        subprocess.Popen(["calc.exe"], shell=False)
    elif app == "notepad":
        subprocess.Popen(["notepad.exe"], shell=False)
    elif app == "downloads":
        downloads = Path.home() / "Downloads"
        if not downloads.is_dir():
            raise RuntimeError("The Downloads folder does not exist")
        subprocess.Popen(["explorer.exe", str(downloads)], shell=False)
    else:
        raise ValueError("Unsupported application shortcut")
    return {"launched": app}


def _presentation(command: str) -> None:
    keys = {"next": "right", "previous": "left", "start": "f5", "end": "esc", "black_screen": "b"}
    if command not in keys:
        raise ValueError("Unsupported presentation action")
    _keyboard_call("send", keys[command])


def _power_action(command: str) -> None:
    if os.name != "nt":
        raise RuntimeError("Power actions are supported only on Windows")
    if command == "lock":
        if not ctypes.windll.user32.LockWorkStation():
            raise OSError("Windows could not lock the workstation")
        return
    if command == "sleep":
        if ctypes.windll.powrprof.SetSuspendState(False, True, False) == 0:
            raise OSError("Windows refused the sleep request")
        return
    if command == "display_off":
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        return
    args = {"logoff": ["/l"], "restart": ["/r", "/t", "0"], "shutdown": ["/s", "/t", "0"]}
    if command not in args:
        raise ValueError("Unsupported power action")
    subprocess.Popen(["shutdown.exe", *args[command]], shell=False)


def _pc_status(permissions: dict[str, bool]) -> dict[str, Any]:
    return {"computer_name": platform.node() or "Unknown PC", "operating_system": platform.system(), "local_time": datetime.now().astimezone().isoformat(timespec="seconds"), "capabilities": remote_capabilities(permissions)}


class RemoteActionSession:
    """Per-connection action dispatcher and held-modifier cleanup."""
    def __init__(self) -> None:
        self._held_modifiers: set[str] = set()
        self._lock = threading.RLock()

    def execute(self, request: dict[str, Any], permissions: dict[str, bool], *, adapters: dict[str, Any] | None = None) -> Any:
        validated = validate_remote_request(request)
        if validated is None:
            raise ValueError("Invalid remote action request")
        action, payload = validated["action"], validated["payload"]
        permission = ACTION_PERMISSION[action]
        if permission != "status" and not bool(permissions.get(permission, False)):
            raise PermissionError(f"{permission.replace('_', ' ').title()} actions are disabled on this PC")
        if adapters and action in adapters:
            return adapters[action](payload)
        if action == "keyboard_text":
            _keyboard_call("write", payload["text"])
            return {"sent_characters": len(payload["text"])}
        if action == "keyboard_key":
            _keyboard_call("send", KEY_NAMES[payload["key"]])
            return {"key": payload["key"]}
        if action == "keyboard_shortcut":
            _keyboard_call("send", SHORTCUTS[payload["shortcut"]])
            return {"shortcut": payload["shortcut"]}
        if action == "keyboard_modifier":
            key = MODIFIER_KEYS[payload["key"]]
            with self._lock:
                if payload["pressed"] and key not in self._held_modifiers:
                    _keyboard_call("press", key)
                    self._held_modifiers.add(key)
                elif not payload["pressed"] and key in self._held_modifiers:
                    _keyboard_call("release", key)
                    self._held_modifiers.remove(key)
            return {"key": payload["key"], "pressed": payload["pressed"]}
        if action == "media":
            _media_key(payload["command"])
            return {"command": payload["command"]}
        if action == "clipboard_set":
            _clipboard_copy(payload["text"])
            return {"characters": len(payload["text"])}
        if action == "clipboard_get":
            value = _clipboard_paste()
            return {"text": value[:3000], "truncated": len(value) > 3000}
        if action == "pc_status":
            return _pc_status(permissions)
        if action == "launch_app":
            return _launch_app(payload["app"])
        if action == "presentation":
            _presentation(payload["command"])
            return {"command": payload["command"]}
        if action == "power_action":
            _power_action(payload["command"])
            return {"command": payload["command"]}
        raise ValueError("Unsupported remote action")

    def close(self, *, adapters: dict[str, Any] | None = None) -> None:
        """Idempotently release any held modifiers when the session ends."""
        with self._lock:
            held = tuple(self._held_modifiers)
            self._held_modifiers.clear()
        for key in held:
            try:
                if adapters and "keyboard_modifier_release" in adapters:
                    adapters["keyboard_modifier_release"](key)
                else:
                    _keyboard_call("release", key)
            except Exception:
                pass
