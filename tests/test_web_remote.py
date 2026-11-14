from core.web_remote import validate_web_controller_state


def _install_mock_mappers(monkeypatch):
    """Provide pair-route mappers without importing Windows/HID dependencies."""
    import sys
    import types
    from types import SimpleNamespace

    import core.web_remote as web_remote
    # Existing route tests exercise the normal XInput path independently of the
    # machine running pytest; dedicated tests below cover the missing-driver path.
    monkeypatch.setattr(web_remote, "is_vigem_installed", lambda: True)

    instances = []

    class MockMapper:
        def __init__(self, uuid, emulate_to, _controllers_page, _hotkey_page, _settings):
            self.uuid = uuid
            self.emulate_to = emulate_to
            self.emulator = (
                None if emulate_to == "none" else SimpleNamespace(device_path=uuid)
            )
            self.calls = []
            self.hid_inputs = []
            self.mouse_inputs = []
            self.gamepad_state = None
            self.mouse_state = {"left": 0, "right": 0, "middle": 0}
            instances.append(self)

        def handle_hid_data(self, data):
            if self.emulator is None:
                return
            self.calls.append("hid")
            self.hid_inputs.append(data)
            self.gamepad_state = data

        def handle_mouse_data(self, data):
            self.calls.append("mouse")
            self.mouse_inputs.append(data)
            self.mouse_state = {key: data[key] for key in ("left", "right", "middle")}

        def reset_gamepad(self):
            self.calls.append("reset_gamepad")
            self.gamepad_state = {
                "buttons": {key: 0 for key in (
                    "A", "B", "X", "Y", "LB", "RB", "BACK", "START", "GUIDE",
                    "L3", "R3", "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
                )},
                "analog": {"L2": 0, "R2": 0},
                "joystick": {"left_x": 128, "left_y": 128, "right_x": 128, "right_y": 128},
            }

        def release_mouse_buttons(self):
            self.calls.append("release_mouse_buttons")
            self.mouse_state = {"left": 0, "right": 0, "middle": 0}

        def shutdown(self):
            self.calls.append("shutdown")

    mapper_module = types.ModuleType("core.mapper")
    mapper_module.Phone_mapper = MockMapper
    monkeypatch.setitem(sys.modules, "core.mapper", mapper_module)
    return instances


def _pair_browser(server, name="Test browser"):
    import time

    server.pairing_code = "123456"
    server.pairing_deadline = time.monotonic() + 60
    response = server.app.test_client().post(
        "/api/pair", json={"code": server.pairing_code, "name": name}
    )
    assert response.status_code == 200
    return response.get_json()["token"]


def _send_browser_state(server, token, state):
    return server.app.test_client().post(
        "/api/state", headers={"Authorization": f"Bearer {token}"}, json=state
    )


def test_browser_state_is_normalized_with_neutral_defaults():
    result = validate_web_controller_state({"mode": "gamepad", "buttons": {"A": True}, "joystick": {"left_x": 255}})
    assert result is not None
    assert result["buttons"]["A"] == 1 and result["buttons"]["B"] == 0
    assert result["analog"] == {"L2": 0, "R2": 0}
    assert result["joystick"] == {"left_x": 255, "left_y": 128, "right_x": 128, "right_y": 128}


def test_invalid_browser_input_is_rejected():
    values = [
        {"mode": "shell"}, {"buttons": {"SHELL": 1}}, {"buttons": {"A": 3}},
        {"joystick": {"left_x": 256}}, {"mode": "mouse", "mouse": {"dx": 2049}},
        {"mode": "mouse", "mouse": {"scroll": 21}}, {"mode": "mouse", "mouse": {"left": "yes"}},
        {"unexpected": True},
    ]
    for value in values:
        assert validate_web_controller_state(value) is None


def test_bounded_touch_mouse_state_accepts_boolean_button_values():
    result = validate_web_controller_state({"mode": "mouse", "mouse": {"dx": -2048, "dy": 2048, "scroll": -20, "left": True}})
    assert result is not None
    assert result["mouse"] == {"dx": -2048, "dy": 2048, "scroll": -20, "left": 1, "right": 0, "middle": 0}


def test_persistent_websocket_stream_applies_states_and_releases_inputs(monkeypatch):
    import json
    import threading
    import time

    from simple_websocket import Client
    from werkzeug.serving import make_server as make_test_server
    from core.web_remote import WebRemoteServer

    mappers = _install_mock_mappers(monkeypatch)
    app_server = WebRemoteServer(object(), object(), object())
    token = _pair_browser(app_server, "Stream test")
    http_server = make_test_server("127.0.0.1", 0, app_server.app, threaded=True)
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    client = None
    try:
        client = Client.connect(f"ws://127.0.0.1:{http_server.server_port}/api/stream")
        client.send(json.dumps({"type": "auth", "token": token}))
        ready = json.loads(client.receive(timeout=2))
        assert ready == {"type": "ready"}

        client.send(json.dumps({
            "type": "state",
            "state": {"mode": "gamepad", "buttons": {"A": 1}, "joystick": {"left_x": 205}},
        }))
        deadline = time.monotonic() + 2
        while not mappers[0].hid_inputs and time.monotonic() < deadline:
            time.sleep(0.01)
        assert mappers[0].hid_inputs
        assert mappers[0].hid_inputs[-1]["buttons"]["A"] == 1
        assert mappers[0].hid_inputs[-1]["joystick"]["left_x"] == 205

        client.send(json.dumps({"type": "ping"}))
        assert json.loads(client.receive(timeout=2)) == {"type": "pong"}

        client.close()
        client = None
        deadline = time.monotonic() + 2
        while "reset_gamepad" not in mappers[0].calls and time.monotonic() < deadline:
            time.sleep(0.01)
        assert "reset_gamepad" in mappers[0].calls
        assert "release_mouse_buttons" in mappers[0].calls
    finally:
        if client is not None:
            client.close()
        http_server.shutdown()
        http_server.server_close()
        thread.join(timeout=2)


def test_desktop_shutdown_notifies_active_browser_streams():
    import json
    from core.web_remote import WebRemoteServer

    class FakeStream:
        def __init__(self):
            self.messages = []
            self.closed = []

        def send(self, message):
            self.messages.append(json.loads(message))

        def close(self, **kwargs):
            self.closed.append(kwargs)

    server = WebRemoteServer(object(), object(), object())
    stream = FakeStream()
    server._sessions["active-token"] = {"stream_ws": stream}

    server._notify_streams_shutdown()

    assert stream.messages == [{"type": "error", "error": "server_shutdown"}]
    assert stream.closed == [{
        "reason": 1001,
        "message": b"Desktop application stopped",
    }]


def test_persistent_controller_stream_route_is_registered():
    from core.web_remote import WebRemoteServer

    server = WebRemoteServer(object(), object(), object())
    routes = {rule.rule: rule for rule in server.app.url_map.iter_rules()}
    assert "/api/stream" in routes
    assert routes["/api/stream"].endpoint.endswith("stream")
    assert getattr(routes["/api/stream"], "websocket", False) is True
    assert "GET" in routes["/api/stream"].methods
    assert "/api/state" in routes


def test_flask_serves_responsive_ui_and_security_headers():
    from core.web_remote import WebRemoteServer

    server = WebRemoteServer(object(), object(), object())
    client = server.app.test_client()
    page = client.get("/")
    assert page.status_code == 200
    assert b"Gamepad" in page.data and b"PC Remote" in page.data
    assert page.headers["Cache-Control"] == "no-store"
    assert "default-src 'self'" in page.headers["Content-Security-Policy"]
    assert page.headers["X-Frame-Options"] == "DENY"


def test_flask_serves_responsive_focus_and_touch_gesture_styles():
    from core.web_remote import WebRemoteServer

    client = WebRemoteServer(object(), object(), object()).app.test_client()
    css = client.get("/static/app.css")

    assert css.status_code == 200
    assert b"orientation:portrait" in css.data
    assert b"orientation:landscape" in css.data
    assert b"body.focus-mode" in css.data
    assert b"overflow-x:auto" in css.data
    assert b"overscroll-behavior-y:auto" in css.data
    assert b"touch-action:none" in css.data


def test_public_server_info_reports_the_tls_fingerprint_and_https_scheme():
    from core.web_remote import WebRemoteServer

    server = WebRemoteServer(object(), object(), object())
    server.fingerprint = "AA:" * 31 + "AA"
    response = server.app.test_client().get("/api/info", base_url="https://localhost")
    assert response.status_code == 200
    assert response.get_json()["fingerprint"] == server.fingerprint
    assert response.get_json()["secure"] is True


def test_connected_browser_names_are_sorted_for_the_desktop_list():
    from core.web_remote import WebRemoteServer

    server = WebRemoteServer(object(), object(), object())
    server._sessions = {
        "token-b": {"name": "Tablet"},
        "token-a": {"name": "Phone"},
    }
    assert server.connected_clients == ["Phone", "Tablet"]


def test_pairing_url_carries_code_and_public_fingerprint_in_the_fragment():
    from core.web_remote import WebRemoteServer

    server = WebRemoteServer(object(), object(), object(), host="192.168.1.20", port=8765)
    server._advertised_host = "192.168.1.20"
    server.pairing_code = "123456"
    server.fingerprint = "AB" * 32

    assert server.pairing_url() == (
        "https://192.168.1.20:8765/#pair=123456&fp=" + "AB" * 32
    )


def test_pairing_and_state_endpoints_reject_bad_or_missing_credentials():
    from core.web_remote import WebRemoteServer

    client = WebRemoteServer(object(), object(), object()).app.test_client()
    bad_code = client.post("/api/pair", json={"code": "123", "name": "Test"})
    assert bad_code.status_code == 400
    no_token = client.post("/api/state", json={"mode": "gamepad"})
    assert no_token.status_code == 401


def test_browser_keyboard_actions_keep_permissions_validation_and_session_state_isolated(monkeypatch):
    import core.remote_actions as remote_actions
    import core.web_remote as web_remote

    _install_mock_mappers(monkeypatch)
    permissions = {
        "keyboard": True, "media": False, "clipboard": False,
        "app_launch": False, "presentation": False, "power": False,
    }
    key_calls = []
    monkeypatch.setattr(web_remote, "load_remote_permissions", lambda: dict(permissions))
    monkeypatch.setattr(
        remote_actions, "_keyboard_call", lambda method, key: key_calls.append((method, key))
    )
    server = web_remote.WebRemoteServer(object(), object(), object())
    token_a = _pair_browser(server, "Browser A")
    token_b = _pair_browser(server, "Browser B")
    assert server._sessions[token_a]["remote"] is not server._sessions[token_b]["remote"]

    def action(token, request_id, name, payload):
        return server.app.test_client().post(
            "/api/action",
            headers={"Authorization": f"Bearer {token}"} if token else {},
            json={"request_id": request_id, "action": name, "payload": payload},
        )

    left = action(token_a, "left-arrow", "keyboard_key", {"key": "LEFT"})
    assert left.status_code == 200
    assert left.get_json()["result"] == {"key": "LEFT"}
    assert key_calls == [("send", "left")]

    assert action(token_a, "hold-ctrl", "keyboard_modifier", {
        "key": "CTRL", "pressed": True,
    }).status_code == 200
    assert action(token_b, "release-ctrl", "keyboard_modifier", {
        "key": "CTRL", "pressed": False,
    }).status_code == 200
    assert key_calls == [("send", "left"), ("press", "ctrl")]

    disconnected = server.app.test_client().post(
        "/api/disconnect", headers={"Authorization": f"Bearer {token_a}"}, json={}
    )
    assert disconnected.status_code == 200
    assert key_calls[-1] == ("release", "ctrl")
    assert action(token_a, "closed-key", "keyboard_key", {"key": "LEFT"}).status_code == 401
    assert action(token_b, "right-arrow", "keyboard_key", {"key": "RIGHT"}).status_code == 200
    assert key_calls[-1] == ("send", "right")

    malformed = action(token_b, "bad-key", "keyboard_key", {"key": "POWERSHELL"})
    assert malformed.status_code == 400
    permissions["keyboard"] = False
    denied = action(token_b, "denied-key", "keyboard_key", {"key": "UP"})
    assert denied.status_code == 403
    assert action("", "no-token", "keyboard_key", {"key": "DOWN"}).status_code == 401


def test_paired_browsers_have_distinct_mappers_and_isolated_inputs(monkeypatch):
    from core.web_remote import WebRemoteServer

    mappers = _install_mock_mappers(monkeypatch)
    registered = []
    server = WebRemoteServer(object(), object(), object(), mapper_added=registered.append)
    token_a = _pair_browser(server, "Browser A")
    token_b = _pair_browser(server, "Browser B")

    assert token_a != token_b
    assert len(server._sessions) == 2
    assert server._sessions[token_a]["uuid"] != server._sessions[token_b]["uuid"]
    assert server._sessions[token_a]["mapper"] is not server._sessions[token_b]["mapper"]
    assert len(mappers) == len(registered) == 2
    assert registered[0] is mappers[0].emulator
    assert registered[1] is mappers[1].emulator

    state_a = {
        "mode": "gamepad",
        "buttons": {"A": True},
        "analog": {"L2": 180, "R2": 23},
        "joystick": {"left_x": 15, "right_y": 240},
    }
    state_b = {
        "mode": "gamepad",
        "buttons": {"B": True},
        "analog": {"L2": 7, "R2": 225},
        "joystick": {"left_y": 30, "right_x": 210},
    }
    assert _send_browser_state(server, token_a, state_a).status_code == 200
    assert _send_browser_state(server, token_b, state_b).status_code == 200
    assert _send_browser_state(server, token_a, {
        "mode": "mouse", "mouse": {"dx": 17, "dy": -6, "scroll": 2, "left": True}
    }).status_code == 200
    assert _send_browser_state(server, token_b, {
        "mode": "mouse", "mouse": {"dx": -9, "dy": 12, "scroll": -1, "right": True}
    }).status_code == 200

    assert len(mappers[0].hid_inputs) == len(mappers[1].hid_inputs) == 1
    assert mappers[0].hid_inputs[0]["buttons"]["A"] == 1
    assert mappers[0].hid_inputs[0]["buttons"]["B"] == 0
    assert mappers[0].hid_inputs[0]["analog"] == {"L2": 180, "R2": 23}
    assert mappers[0].hid_inputs[0]["joystick"]["left_x"] == 15
    assert mappers[0].hid_inputs[0]["joystick"]["right_y"] == 240
    assert mappers[1].hid_inputs[0]["buttons"]["B"] == 1
    assert mappers[1].hid_inputs[0]["buttons"]["A"] == 0
    assert mappers[1].hid_inputs[0]["analog"] == {"L2": 7, "R2": 225}
    assert mappers[1].hid_inputs[0]["joystick"]["left_y"] == 30
    assert mappers[1].hid_inputs[0]["joystick"]["right_x"] == 210
    assert mappers[0].mouse_inputs == [{
        "dx": 17, "dy": -6, "scroll": 2, "left": 1, "right": 0, "middle": 0,
    }]
    assert mappers[1].mouse_inputs == [{
        "dx": -9, "dy": 12, "scroll": -1, "left": 0, "right": 1, "middle": 0,
    }]


def test_switching_one_browser_mode_does_not_reset_the_other_mapper(monkeypatch):
    from core.web_remote import WebRemoteServer

    mappers = _install_mock_mappers(monkeypatch)
    server = WebRemoteServer(object(), object(), object())
    token_a = _pair_browser(server, "Browser A")
    token_b = _pair_browser(server, "Browser B")

    assert _send_browser_state(server, token_a, {"mode": "mouse"}).status_code == 200
    assert mappers[0].calls == ["reset_gamepad", "mouse"]
    assert mappers[1].calls == []

    assert _send_browser_state(server, token_b, {"mode": "mouse"}).status_code == 200
    assert _send_browser_state(server, token_b, {"mode": "gamepad"}).status_code == 200
    assert mappers[0].calls == ["reset_gamepad", "mouse"]
    assert mappers[1].calls == ["reset_gamepad", "mouse", "release_mouse_buttons", "hid"]


def test_disconnect_releases_only_its_browser_and_other_browser_remains_active(monkeypatch):
    from core.web_remote import WebRemoteServer

    mappers = _install_mock_mappers(monkeypatch)
    server = WebRemoteServer(object(), object(), object())
    token_a = _pair_browser(server, "Browser A")
    token_b = _pair_browser(server, "Browser B")

    assert _send_browser_state(server, token_a, {"mode": "mouse", "mouse": {"left": True}}).status_code == 200
    assert _send_browser_state(server, token_b, {"buttons": {"Y": True}}).status_code == 200
    response = server.app.test_client().post(
        "/api/disconnect", headers={"Authorization": f"Bearer {token_a}"}, json={}
    )

    assert response.status_code == 200
    assert token_a not in server._sessions and token_b in server._sessions
    assert mappers[0].calls[-3:] == ["reset_gamepad", "release_mouse_buttons", "shutdown"]
    assert mappers[0].gamepad_state["buttons"]["A"] == 0
    assert mappers[0].mouse_state == {"left": 0, "right": 0, "middle": 0}
    assert "shutdown" not in mappers[1].calls
    assert mappers[1].gamepad_state["buttons"]["Y"] == 1
    calls_before = list(mappers[1].calls)
    assert _send_browser_state(server, token_b, {"buttons": {"X": True}}).status_code == 200
    assert mappers[1].calls == calls_before + ["hid"]
    assert _send_browser_state(server, token_a, {"buttons": {"A": True}}).status_code == 401


def test_expired_browser_session_is_closed_and_cannot_send_more_commands(monkeypatch):
    import time
    from core.web_remote import SESSION_IDLE_SECONDS, WebRemoteServer

    mappers = _install_mock_mappers(monkeypatch)
    server = WebRemoteServer(object(), object(), object())
    token_a = _pair_browser(server, "Browser A")
    token_b = _pair_browser(server, "Browser B")
    with server._lock:
        server._sessions[token_a]["last_seen"] = time.monotonic() - SESSION_IDLE_SECONDS - 1

    expired = _send_browser_state(server, token_a, {"buttons": {"A": True}})
    assert expired.status_code == 401
    assert token_a not in server._sessions and token_b in server._sessions
    assert mappers[0].calls == ["reset_gamepad", "release_mouse_buttons", "shutdown"]
    assert mappers[0].gamepad_state["buttons"]["A"] == 0
    assert mappers[0].mouse_state == {"left": 0, "right": 0, "middle": 0}
    assert _send_browser_state(server, token_a, {"mode": "mouse"}).status_code == 401
    action = server.app.test_client().post(
        "/api/action",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"request_id": "expired-request", "action": "pc_status", "payload": {}},
    )
    assert action.status_code == 401
    assert mappers[0].calls == ["reset_gamepad", "release_mouse_buttons", "shutdown"]
    assert _send_browser_state(server, token_b, {"buttons": {"B": True}}).status_code == 200
    assert mappers[1].hid_inputs[-1]["buttons"]["B"] == 1


def test_repeated_pair_and_disconnect_cycles_leave_no_live_sessions_or_mappers(monkeypatch):
    from core.web_remote import WebRemoteServer

    mappers = _install_mock_mappers(monkeypatch)
    server = WebRemoteServer(object(), object(), object())
    for index in range(4):
        token = _pair_browser(server, f"Browser {index}")
        assert server.client_count == 1
        assert _send_browser_state(server, token, {"buttons": {"A": True}}).status_code == 200
        response = server.app.test_client().post(
            "/api/disconnect", headers={"Authorization": f"Bearer {token}"}, json={}
        )
        assert response.status_code == 200
        assert server.client_count == 0
        assert token not in server._sessions
        assert mappers[index].gamepad_state["buttons"]["A"] == 0
        assert mappers[index].mouse_state == {"left": 0, "right": 0, "middle": 0}

    assert len(mappers) == 4
    for mapper in mappers:
        assert mapper.calls.count("shutdown") == 1
        assert mapper.calls[-3:] == ["reset_gamepad", "release_mouse_buttons", "shutdown"]


def test_concurrent_mode_changes_on_one_browser_are_serialized(monkeypatch):
    import threading
    from core.web_remote import WebRemoteServer

    mappers = _install_mock_mappers(monkeypatch)
    server = WebRemoteServer(object(), object(), object())
    token = _pair_browser(server, "Browser A")
    mapper = mappers[0]
    mouse_entered = threading.Event()
    allow_mouse_finish = threading.Event()
    second_authorized = threading.Event()
    hid_entered = threading.Event()
    original_authorize = server._authorize
    original_hid = mapper.handle_hid_data

    def blocked_mouse(data):
        mouse_entered.set()
        assert allow_mouse_finish.wait(2)
        mapper.calls.append("mouse")
        mapper.mouse_inputs.append(data)
        mapper.mouse_state = {key: data[key] for key in ("left", "right", "middle")}

    def tracked_hid(data):
        hid_entered.set()
        original_hid(data)

    def tracked_authorize(header):
        result = original_authorize(header)
        if threading.current_thread().name == "second-state-request":
            second_authorized.set()
        return result

    mapper.handle_mouse_data = blocked_mouse
    mapper.handle_hid_data = tracked_hid
    server._authorize = tracked_authorize
    statuses = {}

    def post(name, state):
        with server.app.test_client() as client:
            statuses[name] = client.post(
                "/api/state", headers={"Authorization": f"Bearer {token}"}, json=state
            ).status_code

    first = threading.Thread(
        name="first-state-request",
        target=post,
        args=("mouse", {"mode": "mouse", "mouse": {"left": True}}),
    )
    second = threading.Thread(
        name="second-state-request",
        target=post,
        args=("gamepad", {"mode": "gamepad", "buttons": {"A": False}}),
    )
    first.start()
    try:
        assert mouse_entered.wait(2)
        second.start()
        assert second_authorized.wait(2)
        assert not hid_entered.wait(0.05)
    finally:
        allow_mouse_finish.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert statuses == {"mouse": 200, "gamepad": 200}
    assert mapper.calls == ["reset_gamepad", "mouse", "release_mouse_buttons", "hid"]
    assert mapper.mouse_state == {"left": 0, "right": 0, "middle": 0}
    assert server._sessions[token]["mode"] == "gamepad"


def test_disconnect_releases_the_browser_controller_session():
    import time
    from core.web_remote import WebRemoteServer

    class Mapper:
        def __init__(self):
            self.calls = []

        def reset_gamepad(self):
            self.calls.append("reset_gamepad")

        def release_mouse_buttons(self):
            self.calls.append("release_mouse_buttons")

        def shutdown(self):
            self.calls.append("shutdown")

    class Remote:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    server = WebRemoteServer(object(), object(), object())
    mapper, remote, token = Mapper(), Remote(), "test-browser-token"
    with server._lock:
        server._sessions[token] = {
            "uuid": "web-test", "name": "Test browser", "mapper": mapper,
            "remote": remote, "last_seen": time.monotonic(), "mode": "gamepad",
        }

    response = server.app.test_client().post(
        "/api/disconnect", headers={"Authorization": f"Bearer {token}"}, json={}
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert token not in server._sessions
    assert mapper.calls == ["reset_gamepad", "release_mouse_buttons", "shutdown"]
    assert remote.closed is True


def test_web_tls_certificate_covers_advertised_lan_ip_and_reuses_matching_identity(tmp_path):
    import ssl
    from cryptography import x509
    from core.remote_security import create_web_server_ssl_context

    certificate_path = tmp_path / "web_server.crt"
    key_path = tmp_path / "web_server.key"
    context, fingerprint = create_web_server_ssl_context(
        ["192.168.77.21"], certificate_path, key_path
    )
    certificate = x509.load_pem_x509_certificate(certificate_path.read_bytes())
    sans = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    ip_names = {str(value) for value in sans.get_values_for_type(x509.IPAddress)}
    assert "192.168.77.21" in ip_names
    assert "127.0.0.1" in ip_names
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
    assert len(fingerprint.replace(":", "")) == 64

    _context_again, fingerprint_again = create_web_server_ssl_context(
        ["192.168.77.21"], certificate_path, key_path
    )
    assert fingerprint_again == fingerprint

    _new_context, fingerprint_new_host = create_web_server_ssl_context(
        ["192.168.77.22"], certificate_path, key_path
    )
    assert fingerprint_new_host != fingerprint
    new_cert = x509.load_pem_x509_certificate(certificate_path.read_bytes())
    new_sans = new_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "192.168.77.22" in {str(value) for value in new_sans.get_values_for_type(x509.IPAddress)}



def test_pairing_without_vigem_keeps_mouse_and_pc_remote_available(monkeypatch):
    import core.web_remote as web_remote

    mappers = _install_mock_mappers(monkeypatch)
    monkeypatch.setattr(web_remote, "is_vigem_installed", lambda: False)
    registered = []
    server = web_remote.WebRemoteServer(
        object(), object(), object(), mapper_added=registered.append
    )

    token = _pair_browser(server, "Mouse-only browser")
    mapper = mappers[0]
    session = server._sessions[token]

    assert mapper.emulate_to == "none"
    assert mapper.emulator is None
    assert session["gamepad_available"] is False
    assert registered == []
    assert server.app.test_client().get("/api/info").get_json()["gamepad_available"] is False

    response = _send_browser_state(
        server,
        token,
        {"mode": "mouse", "mouse": {"dx": 11, "dy": -4, "scroll": 0, "left": True}},
    )
    assert response.status_code == 200
    assert mapper.mouse_inputs[-1]["dx"] == 11
    assert mapper.mouse_inputs[-1]["dy"] == -4

    action = server.app.test_client().post(
        "/api/action",
        headers={"Authorization": f"Bearer {token}"},
        json={"request_id": "remote-status", "action": "pc_status", "payload": {}},
    )
    assert action.status_code == 200


def test_desktop_mobile_session_events_and_targeted_disconnect(monkeypatch):
    from core.web_remote import WebRemoteServer

    mappers = _install_mock_mappers(monkeypatch)
    added = []
    removed = []
    registered = []
    server = WebRemoteServer(
        object(),
        object(),
        object(),
        mapper_added=registered.append,
        session_added=added.append,
        session_removed=removed.append,
    )

    token_a = _pair_browser(server, "Phone A")
    token_b = _pair_browser(server, "Phone B")
    session_a = server._sessions[token_a]
    session_b = server._sessions[token_b]

    assert len(added) == 2
    assert added[0]["session_id"] == session_a["uuid"]
    assert added[0]["name"] == "Phone A"
    assert "Touch mouse" in added[0]["capabilities"]
    assert "Keyboard / PC Remote" in added[0]["capabilities"]
    assert added[0]["gamepad_available"] is True
    assert {item["session_id"] for item in server.sessions_snapshot()} == {
        session_a["uuid"], session_b["uuid"]
    }

    assert server.disconnect_session(session_a["uuid"]) is True
    assert server.disconnect_session(session_a["uuid"]) is False
    assert token_a not in server._sessions
    assert token_b in server._sessions
    assert removed == [added[0]]
    assert mappers[0].calls[-3:] == [
        "reset_gamepad", "release_mouse_buttons", "shutdown"
    ]
    assert "shutdown" not in mappers[1].calls
