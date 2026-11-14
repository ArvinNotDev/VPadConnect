"""HTTPS browser companion: multiple independent virtual gamepads plus permission-gated PC actions."""
from __future__ import annotations

import ipaddress
import json
import os
import logging
import secrets
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from flask import Flask, jsonify, render_template, request
from simple_websocket import ConnectionClosed, Server as WebSocketServer
from werkzeug.serving import make_server

from core.remote_actions import RemoteActionSession, load_remote_permissions
from core.remote_protocol import PROTOCOL_VERSION
from core.remote_security import create_web_server_ssl_context
from core.vigem import is_vigem_installed

BUTTON_KEYS = {"A", "B", "X", "Y", "LB", "RB", "BACK", "START", "GUIDE", "L3", "R3",
               "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT"}
ANALOG_KEYS = {"L2", "R2"}
JOYSTICK_KEYS = {"left_x", "left_y", "right_x", "right_y"}
MOUSE_BUTTON_KEYS = {"left", "right", "middle"}
SESSION_IDLE_SECONDS = 300.0
PAIRING_LIFETIME_SECONDS = 300.0
MAX_WEB_SESSIONS = 8


def _bounded_map(value: Any, allowed: set[str], low: int, high: int, *, booleans: bool = False) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, int] = {}
    for key, item in value.items():
        if key not in allowed:
            return None
        if booleans and isinstance(item, bool):
            result[key] = int(item)
        elif type(item) is int and low <= item <= high:
            result[key] = item
        else:
            return None
    return result


def validate_web_controller_state(candidate: Any) -> dict[str, Any] | None:
    """Bound browser input before it reaches the Windows mapper."""
    if not isinstance(candidate, dict) or set(candidate) - {"mode", "buttons", "analog", "joystick", "mouse"}:
        return None
    mode = candidate.get("mode", "gamepad")
    if mode not in ("gamepad", "mouse"):
        return None
    buttons = _bounded_map(candidate.get("buttons", {}), BUTTON_KEYS, 0, 1, booleans=True)
    analog = _bounded_map(candidate.get("analog", {}), ANALOG_KEYS, 0, 255)
    joystick = _bounded_map(candidate.get("joystick", {}), JOYSTICK_KEYS, 0, 255)
    mouse_raw = candidate.get("mouse", {})
    if buttons is None or analog is None or joystick is None or not isinstance(mouse_raw, dict):
        return None
    if set(mouse_raw) - ({"dx", "dy", "scroll"} | MOUSE_BUTTON_KEYS):
        return None
    mouse = {"dx": 0, "dy": 0, "scroll": 0, "left": 0, "right": 0, "middle": 0}
    for key in ("dx", "dy"):
        value = mouse_raw.get(key, 0)
        if type(value) is not int or abs(value) > 2048:
            return None
        mouse[key] = value
    scroll = mouse_raw.get("scroll", 0)
    if type(scroll) is not int or not -20 <= scroll <= 20:
        return None
    mouse["scroll"] = scroll
    for key in MOUSE_BUTTON_KEYS:
        value = mouse_raw.get(key, 0)
        if isinstance(value, bool):
            mouse[key] = int(value)
        elif type(value) is int and value in (0, 1):
            mouse[key] = value
        else:
            return None
    full_buttons = {key: 0 for key in BUTTON_KEYS}
    full_buttons.update(buttons)
    full_analog = {key: 0 for key in ANALOG_KEYS}
    full_analog.update(analog)
    full_sticks = {key: 128 for key in JOYSTICK_KEYS}
    full_sticks.update(joystick)
    return {"mode": mode, "buttons": full_buttons, "analog": full_analog,
            "joystick": full_sticks, "mouse": mouse}


def _ensure_windows_firewall_rule(port: int) -> None:
    """Request a narrowly scoped private-network rule when Windows Firewall lacks one."""
    if os.name != "nt":
        return
    rule_name = "VPadConnect Web Companion"
    try:
        check = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        details = (check.stdout + check.stderr).lower()
        if rule_name.lower() in details and "no rules match" not in details:
            return
        rule_args = (
            "advfirewall firewall add rule "
            f'name="{rule_name}" dir=in action=allow protocol=TCP '
            f"localport={port} profile=private enable=yes"
        )
        if hasattr(__import__("ctypes").windll.shell32, "IsUserAnAdmin") and __import__("ctypes").windll.shell32.IsUserAnAdmin():
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={rule_name}", "dir=in", "action=allow", "protocol=TCP",
                 f"localport={port}", "profile=private", "enable=yes"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        else:
            # Windows displays the standard UAC prompt; no elevation is requested without consent.
            command = (
                "Start-Process -FilePath 'netsh.exe' "
                f"-ArgumentList 'advfirewall firewall add rule name=\"{rule_name}\" "
                f"dir=in action=allow protocol=TCP localport={port} profile=private enable=yes' "
                "-Verb RunAs -WindowStyle Hidden -Wait"
            )
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                capture_output=True, text=True, timeout=60, check=False,
            )
    except (OSError, subprocess.SubprocessError, AttributeError):
        # The listener can still be used locally if the optional firewall change is unavailable.
        return


def get_lan_ip() -> str:
    """Resolve the preferred LAN IPv4 address without sending application data."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as stream:
            stream.connect(("192.0.2.1", 80))
            address = stream.getsockname()[0]
            ipaddress.ip_address(address)
            return address
    except (OSError, ValueError):
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                address = info[4][0]
                if not address.startswith("127."):
                    return address
        except OSError:
            pass
    return "127.0.0.1"


class WebRemoteServer:
    """Embedded threaded HTTPS server; each paired browser gets its own XInput device."""

    def __init__(
        self, settings, controllers_page, hotkey_page,
        mapper_added: Callable[[Any], None] | None = None,
        session_added: Callable[[dict[str, Any]], None] | None = None,
        session_removed: Callable[[dict[str, Any]], None] | None = None,
        *, host: str = "0.0.0.0", port: int = 8765,
    ):
        self.settings = settings
        self.controllers_page = controllers_page
        self.hotkey_page = hotkey_page
        self.mapper_added = mapper_added
        self.session_added = session_added
        self.session_removed = session_removed
        self.host = host
        self.port = int(port)
        self.fingerprint = ""
        self._advertised_host = ""
        self.pairing_code = ""
        self.pairing_deadline = 0.0
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._pending_pairs = 0
        self._pair_failures: dict[str, list[float]] = {}
        self._server = None
        self._thread: threading.Thread | None = None
        self._watchdog: threading.Thread | None = None
        self._stop_event = threading.Event()
        root = Path(__file__).resolve().parent.parent / "ui" / "web"
        self.app = Flask("vpadconnect_web_remote", template_folder=str(root / "templates"),
                         static_folder=str(root / "static"), static_url_path="/static")
        self.app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
        self._register_routes()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    @property
    def connected_clients(self) -> list[str]:
        """Return stable, display-safe names for the currently paired browsers."""
        with self._lock:
            return sorted(
                session["name"] for session in self._sessions.values()
                if isinstance(session.get("name"), str)
            )

    def sessions_snapshot(self) -> list[dict[str, Any]]:
        """Return display-safe metadata for currently paired browser sessions."""
        with self._lock:
            return [
                self._session_event_payload(session)
                for session in self._sessions.values()
            ]

    @staticmethod
    def _session_event_payload(session: dict[str, Any]) -> dict[str, Any]:
        gamepad_available = bool(session.get("gamepad_available", False))
        capabilities = ["Touch mouse", "Keyboard / PC Remote"]
        if gamepad_available:
            capabilities.insert(0, "Gamepad")
        return {
            "session_id": str(session.get("uuid") or ""),
            "name": str(session.get("name") or "Mobile Device"),
            "gamepad_available": gamepad_available,
            "capabilities": capabilities,
        }

    def _notify_session_added(self, session: dict[str, Any]) -> None:
        callback = self.session_added
        if callback is None:
            return
        try:
            callback(self._session_event_payload(session))
        except Exception:
            self.app.logger.exception("Could not publish a newly paired mobile session")

    def _notify_session_removed(self, session: dict[str, Any]) -> None:
        callback = self.session_removed
        if callback is None:
            return
        try:
            callback(self._session_event_payload(session))
        except Exception:
            self.app.logger.exception("Could not publish a disconnected mobile session")

    def _remove_session_token(self, token: str) -> bool:
        with self._lock:
            session = self._sessions.pop(token, None)
        if session is None:
            return False
        self._close_session(session)
        self._notify_session_removed(session)
        return True

    def disconnect_session(self, session_id: str) -> bool:
        """Disconnect exactly one paired browser session by its stable session ID."""
        with self._lock:
            token = next(
                (
                    key for key, session in self._sessions.items()
                    if session.get("uuid") == session_id
                ),
                None,
            )
        return self._remove_session_token(token) if token is not None else False

    @property
    def local_url(self) -> str:
        host = self._advertised_host or get_lan_ip()
        return "https://" + host + ":" + str(self.port) + "/"

    def pairing_url(self) -> str:
        # Pairing data is in the URL fragment, so the code is not sent in HTTP requests or logs.
        return self.local_url + "#pair=" + self.pairing_code + "&fp=" + self.fingerprint if self.pairing_code else self.local_url

    def rotate_pairing_code(self) -> str:
        with self._lock:
            self.pairing_code = str(secrets.randbelow(900000) + 100000)
            self.pairing_deadline = time.monotonic() + PAIRING_LIFETIME_SECONDS
            self._pair_failures.clear()
            return self.pairing_code

    def start(self, port: int | None = None) -> None:
        if self.running:
            return
        if port is not None:
            if type(port) is not int or not 1024 <= port <= 65535:
                raise ValueError("The HTTPS port must be between 1024 and 65535.")
            self.port = port
        self._advertised_host = get_lan_ip()
        _ensure_windows_firewall_rule(self.port)
        tls_context, self.fingerprint = create_web_server_ssl_context([self._advertised_host])
        self._stop_event.clear()
        self.rotate_pairing_code()
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        # Bind synchronously so the UI can report errors immediately.
        self._server = make_server(self.host, self.port, self.app, threaded=True, ssl_context=tls_context)
        self._thread = threading.Thread(target=self._server.serve_forever, name="VPadConnectWebHTTPS", daemon=True)
        self._watchdog = threading.Thread(target=self._watch_expired_sessions, name="VPadConnectWebWatchdog", daemon=True)
        self._thread.start()
        self._watchdog.start()

    def stop(self) -> None:
        self._notify_streams_shutdown()
        self._stop_event.set()
        server, thread, watchdog = self._server, self._thread, self._watchdog
        self._server = None
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
        current = threading.current_thread()
        if thread is not None and thread is not current:
            thread.join(timeout=2)
        if watchdog is not None and watchdog is not current:
            watchdog.join(timeout=1)
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            self._close_session(session)
            self._notify_session_removed(session)
        self.pairing_code = ""
        self.pairing_deadline = 0

    def _notify_streams_shutdown(self) -> None:
        """Tell paired browsers that the desktop app is stopping intentionally."""
        with self._lock:
            streams = []
            seen: set[int] = set()
            for session in self._sessions.values():
                stream = session.get("stream_ws")
                if stream is not None and id(stream) not in seen:
                    seen.add(id(stream))
                    streams.append(stream)
        for stream in streams:
            try:
                stream.send(json.dumps({"type": "error", "error": "server_shutdown"}))
            except Exception:
                pass
            try:
                stream.close(reason=1001, message=b"Desktop application stopped")
            except Exception:
                pass

    def _watch_expired_sessions(self) -> None:
        while not self._stop_event.wait(1):
            now = time.monotonic()
            with self._lock:
                expired = [key for key, item in self._sessions.items() if now - item["last_seen"] > SESSION_IDLE_SECONDS]
                sessions = [self._sessions.pop(key) for key in expired]
            for session in sessions:
                self._close_session(session)
                self._notify_session_removed(session)

    @staticmethod
    def _close_session(session: dict[str, Any]) -> None:
        # Serialize cleanup with any request already using this session's
        # mapper. The closed flag also makes cleanup idempotent when disconnect,
        # expiry, and server shutdown race with one another.
        lock = session.get("lock")
        if lock is None:
            lock = threading.RLock()
            session["lock"] = lock
        with lock:
            if session.get("closed", False):
                return
            session["closed"] = True
            mapper = session.get("mapper")
            if mapper is not None:
                for method_name in ("reset_gamepad", "release_mouse_buttons", "shutdown"):
                    try:
                        getattr(mapper, method_name)()
                    except Exception:
                        pass
            stream = session.get("stream_ws")
            if stream is not None:
                try:
                    stream.close(reason=1001, message=b"Session disconnected")
                except Exception:
                    pass
            try:
                session.get("remote").close()
            except Exception:
                pass

    def _authorize(self, header: str) -> tuple[str | None, dict[str, Any] | None]:
        token = header.removeprefix("Bearer ").strip()
        if not token:
            return None, None
        now = time.monotonic()
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None, None
            expired = now - session["last_seen"] > SESSION_IDLE_SECONDS
            if expired:
                session = self._sessions.pop(token, None)
            else:
                session["last_seen"] = now
        if expired:
            if session:
                self._close_session(session)
                self._notify_session_removed(session)
            return None, None
        return token, session

    @staticmethod
    def _apply_controller_state(session: dict[str, Any], data: dict[str, Any]) -> bool:
        """Apply one validated state snapshot without an HTTP round trip."""
        with session["lock"]:
            if session.get("closed", False):
                return False
            mapper, previous, current = session["mapper"], session.get("mode"), data["mode"]
            if previous != current:
                if previous == "gamepad":
                    mapper.reset_gamepad()
                if previous == "mouse":
                    mapper.release_mouse_buttons()
                session["mode"] = current
            if current == "mouse":
                mapper.handle_mouse_data(data["mouse"])
            else:
                mapper.handle_hid_data({
                    "buttons": data["buttons"],
                    "analog": data["analog"],
                    "joystick": data["joystick"],
                })
        return True

    def _touch_stream_session(self, token: str, session: dict[str, Any]) -> bool:
        """Keep a live WebSocket session alive without periodic HTTP heartbeats."""
        with self._lock:
            if self._sessions.get(token) is not session or session.get("closed", False):
                return False
            session["last_seen"] = time.monotonic()
            return True

    @staticmethod
    def _release_stream_inputs(session: dict[str, Any]) -> None:
        """Release any held controls if the persistent input channel closes."""
        with session["lock"]:
            if session.get("closed", False):
                return
            mapper = session.get("mapper")
            if mapper is not None:
                try:
                    mapper.reset_gamepad()
                except Exception:
                    pass
                try:
                    mapper.release_mouse_buttons()
                except Exception:
                    pass
            session["mode"] = "gamepad"

    def _register_routes(self) -> None:
        app = self.app

        @app.after_request
        def security_headers(response):
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"
            response.headers["Cache-Control"] = "no-store"
            return response

        @app.get("/")
        def index():
            return render_template("index.html")

        @app.get("/api/info")
        def info():
            return jsonify({"app": "VPadConnect Web Companion", "protocol_version": PROTOCOL_VERSION,
                            "fingerprint": self.fingerprint,
                            "pairing_seconds": max(0, int(self.pairing_deadline - time.monotonic())),
                            "gamepad_available": is_vigem_installed(),
                            "secure": request.is_secure})

        @app.post("/api/pair")
        def pair():
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict) or set(payload) - {"code", "name"}:
                return jsonify({"ok": False, "error": "Invalid pairing request."}), 400
            code, name = payload.get("code"), payload.get("name", "Web Controller")
            if not isinstance(code, str) or len(code) != 6 or not code.isdigit():
                return jsonify({"ok": False, "error": "Enter the six-digit code shown on the PC."}), 400
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 64 or any(ord(c) < 32 for c in name):
                return jsonify({"ok": False, "error": "Device name must be 1–64 printable characters."}), 400
            addr, now = request.remote_addr or "unknown", time.monotonic()
            with self._lock:
                attempts = [stamp for stamp in self._pair_failures.get(addr, []) if now - stamp < 60]
                if len(attempts) >= 12:
                    self._pair_failures[addr] = attempts
                    return jsonify({"ok": False, "error": "Too many attempts. Wait a minute and try again."}), 429
                attempts.append(now)
                self._pair_failures[addr] = attempts
                if len(self._sessions) + self._pending_pairs >= MAX_WEB_SESSIONS:
                    return jsonify({"ok": False, "error": "The web companion already has the maximum of eight active browser controllers."}), 429
                valid = bool(self.pairing_code and now < self.pairing_deadline and secrets.compare_digest(code, self.pairing_code))
                if valid:
                    self._pending_pairs += 1
            if not valid:
                return jsonify({"ok": False, "error": "Pairing code is wrong or expired. Create a fresh QR code on the PC."}), 403
            session_uuid = "web-" + uuid.uuid4().hex
            gamepad_available = is_vigem_installed()
            try:
                # Import platform-specific input handling only when a browser
                # pairs. A failed XInput initialization must not prevent the
                # independent touch-mouse and PC Remote features from working.
                from core.mapper import Phone_mapper
                if gamepad_available:
                    try:
                        mapper = Phone_mapper(
                            session_uuid, "x360", self.controllers_page,
                            self.hotkey_page, self.settings,
                        )
                    except Exception:
                        app.logger.exception(
                            "ViGEmBus was detected but XInput initialization failed; "
                            "falling back to a mouse/PC-Remote-only session"
                        )
                        gamepad_available = False
                        mapper = Phone_mapper(
                            session_uuid, "none", self.controllers_page,
                            self.hotkey_page, self.settings,
                        )
                else:
                    mapper = Phone_mapper(
                        session_uuid, "none", self.controllers_page,
                        self.hotkey_page, self.settings,
                    )
            except Exception:
                with self._lock:
                    self._pending_pairs = max(0, self._pending_pairs - 1)
                app.logger.exception("Could not initialize browser session")
                return jsonify({"ok": False, "error": "Could not initialize this browser session on the PC."}), 500
            token = secrets.token_urlsafe(32)
            session = {"uuid": session_uuid, "name": name.strip(), "mapper": mapper,
                       "remote": RemoteActionSession(), "last_seen": time.monotonic(),
                       "mode": "gamepad", "gamepad_available": gamepad_available,
                       "lock": threading.RLock(), "closed": False, "stream_ws": None}
            with self._lock:
                self._pending_pairs = max(0, self._pending_pairs - 1)
                if self._stop_event.is_set() or len(self._sessions) >= MAX_WEB_SESSIONS:
                    rejected = True
                else:
                    self._sessions[token] = session
                    rejected = False
            if rejected:
                self._close_session(session)
                return jsonify({"ok": False, "error": "The web server stopped or reached its controller limit. Try again."}), 503
            if self.mapper_added is not None and mapper.emulator is not None:
                try:
                    self.mapper_added(mapper.emulator)
                except Exception:
                    with self._lock:
                        self._sessions.pop(token, None)
                    self._close_session(session)
                    return jsonify({"ok": False, "error": "Could not register this controller with the desktop UI."}), 500
            self._notify_session_added(session)
            return jsonify({"ok": True, "token": token, "name": session["name"],
                            "gamepad_available": gamepad_available})

        @app.route("/api/stream", methods=["GET"], websocket=True)
        def stream():
            # One authenticated persistent channel carries state snapshots. This
            # avoids a TLS/HTTP request-response round trip for every touch move.
            try:
                ws = WebSocketServer.accept(
                    request.environ, ping_interval=15, max_message_size=8192
                )
            except Exception:
                return jsonify({"ok": False, "error": "WebSocket upgrade required."}), 426

            token = None
            session = None
            try:
                first = ws.receive(timeout=5)
                if not isinstance(first, str):
                    ws.close(reason=1008, message=b"Authentication required")
                    return ""
                try:
                    hello = json.loads(first)
                except (TypeError, ValueError):
                    hello = None
                if not isinstance(hello, dict) or hello.get("type") != "auth":
                    ws.close(reason=1008, message=b"Authentication required")
                    return ""
                token_value = hello.get("token")
                if not isinstance(token_value, str) or not token_value:
                    ws.close(reason=1008, message=b"Authentication required")
                    return ""
                token = token_value
                with self._lock:
                    candidate = self._sessions.get(token)
                    if (
                        candidate is not None
                        and not candidate.get("closed", False)
                        and not self._stop_event.is_set()
                        and time.monotonic() - candidate["last_seen"] <= SESSION_IDLE_SECONDS
                    ):
                        session = candidate
                        session["last_seen"] = time.monotonic()
                        session["stream_ws"] = ws
                if session is None:
                    error_type = "server_shutdown" if self._stop_event.is_set() else "session_expired"
                    ws.send(json.dumps({"type": "error", "error": error_type}))
                    ws.close(reason=1001 if error_type == "server_shutdown" else 1008,
                             message=b"Desktop application stopped" if error_type == "server_shutdown" else b"Session expired")
                    return ""

                ws.send(json.dumps({"type": "ready"}))
                while not self._stop_event.is_set():
                    try:
                        raw = ws.receive(timeout=1)
                    except ConnectionClosed:
                        break
                    if raw is None:
                        # The socket itself is the liveness signal. No browser
                        # timer needs to send a separate HTTP heartbeat.
                        if not self._touch_stream_session(token, session):
                            break
                        continue
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="strict")
                    try:
                        message = json.loads(raw)
                    except (UnicodeDecodeError, TypeError, ValueError):
                        continue
                    if not isinstance(message, dict):
                        continue
                    if message.get("type") == "ping":
                        if not self._touch_stream_session(token, session):
                            break
                        try:
                            ws.send(json.dumps({"type": "pong"}))
                        except (ConnectionClosed, OSError, RuntimeError, ValueError):
                            break
                        continue
                    if message.get("type") != "state":
                        continue
                    data = validate_web_controller_state(message.get("state"))
                    if data is None:
                        continue
                    if not self._apply_controller_state(session, data):
                        break
                    if not self._touch_stream_session(token, session):
                        break
            except (ConnectionClosed, OSError, RuntimeError, ValueError):
                pass
            finally:
                if session is not None:
                    with self._lock:
                        if session.get("stream_ws") is ws:
                            session["stream_ws"] = None
                    self._release_stream_inputs(session)
                try:
                    ws.close()
                except Exception:
                    pass
            return ""

        @app.post("/api/state")
        def state():
            _token, session = self._authorize(request.headers.get("Authorization", ""))
            if session is None:
                return jsonify({"ok": False, "error": "Session expired. Pair this browser again."}), 401
            data = validate_web_controller_state(request.get_json(silent=True))
            if data is None:
                return jsonify({"ok": False, "error": "Invalid controller state."}), 400
            if not self._apply_controller_state(session, data):
                return jsonify({"ok": False, "error": "Session expired. Pair this browser again."}), 401
            return jsonify({"ok": True})

        @app.post("/api/action")
        def action():
            _token, session = self._authorize(request.headers.get("Authorization", ""))
            if session is None:
                return jsonify({"ok": False, "error": "Session expired. Pair this browser again."}), 401
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict) or set(payload) != {"request_id", "action", "payload"}:
                return jsonify({"ok": False, "error": "Invalid remote-action request."}), 400
            name = payload.get("action")
            try:
                with session["lock"]:
                    if session.get("closed", False):
                        return jsonify({"ok": False, "error": "Session expired. Pair this browser again."}), 401
                    result = session["remote"].execute({
                        "protocol_version": PROTOCOL_VERSION, "request_id": payload.get("request_id"),
                        "action": name, "payload": payload.get("payload")
                    }, load_remote_permissions())
                return jsonify({"ok": True, "action": name, "result": result})
            except PermissionError as exc:
                return jsonify({"ok": False, "action": name, "error": str(exc)}), 403
            except (ValueError, TypeError) as exc:
                return jsonify({"ok": False, "action": name, "error": str(exc) or "Invalid request"}), 400
            except Exception:
                app.logger.exception("Browser remote action failed")
                return jsonify({"ok": False, "action": name, "error": "The desktop could not complete this action."}), 500

        @app.post("/api/disconnect")
        def disconnect():
            token, _session = self._authorize(request.headers.get("Authorization", ""))
            if token is None:
                return jsonify({"ok": True})
            self._remove_session_token(token)
            return jsonify({"ok": True})
