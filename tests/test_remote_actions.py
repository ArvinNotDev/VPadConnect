import pytest
from core.remote_actions import DEFAULT_REMOTE_PERMISSIONS, RemoteActionSession, remote_capabilities


def _request(action, payload=None, request_id="req_01"):
    return {"protocol_version": 1, "request_id": request_id, "action": action, "payload": payload or {}}


def test_remote_permissions_are_enabled_by_default():
    assert all(value is True for value in DEFAULT_REMOTE_PERMISSIONS.values())
    assert all(value is True for name, value in remote_capabilities().items() if name != "pc_status")
    assert remote_capabilities()["pc_status"] is True


def test_status_is_available_and_reports_real_machine_values():
    result = RemoteActionSession().execute(_request("pc_status"), DEFAULT_REMOTE_PERMISSIONS)
    assert result["computer_name"]
    assert result["operating_system"]
    assert result["capabilities"]["pc_status"] is True
    assert "volume_level" not in result


def test_permission_denied_before_adapter_runs():
    called = []
    with pytest.raises(PermissionError):
        RemoteActionSession().execute(
            _request("clipboard_set", {"text": "do not copy"}),
            dict(DEFAULT_REMOTE_PERMISSIONS, clipboard=False),
            adapters={"clipboard_set": lambda payload: called.append(payload)},
        )
    assert called == []


def test_allowlisted_action_uses_adapter_for_testability():
    seen = []
    result = RemoteActionSession().execute(
        _request("media", {"command": "mute"}),
        dict(DEFAULT_REMOTE_PERMISSIONS, media=True),
        adapters={"media": lambda payload: seen.append(payload["command"]) or {"done": True}},
    )
    assert result == {"done": True}
    assert seen == ["mute"]


def test_invalid_request_fails_before_adapter_runs():
    with pytest.raises(ValueError):
        RemoteActionSession().execute(
            _request("launch_app", {"app": "powershell"}),
            DEFAULT_REMOTE_PERMISSIONS,
            adapters={"launch_app": lambda payload: {"launched": True}},
        )


def test_legacy_permission_file_migrates_to_enabled_defaults_once(tmp_path):
    import json
    from core.remote_actions import load_remote_permissions, save_remote_permissions

    path = tmp_path / "remote_permissions.json"
    path.write_text(json.dumps({name: False for name in DEFAULT_REMOTE_PERMISSIONS}), encoding="utf-8")

    migrated = load_remote_permissions(path)
    assert all(value is True for value in migrated.values())
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 2

    save_remote_permissions({"keyboard": False}, path)
    restored = load_remote_permissions(path)
    assert restored["keyboard"] is False
    assert all(value is True for name, value in restored.items() if name != "keyboard")


def test_permissions_persist_atomically_and_invalid_values_use_defaults(tmp_path):
    from core.remote_actions import load_remote_permissions, save_remote_permissions
    path = tmp_path / "remote_permissions.json"
    save_remote_permissions({"power": False, "clipboard": "yes"}, path)
    restored = load_remote_permissions(path)
    assert restored["power"] is False
    assert restored["clipboard"] is True
    assert restored["keyboard"] is True

def test_device_permissions_are_isolated_and_persisted(tmp_path, monkeypatch):
    import core.remote_actions as remote_actions
    from core.remote_actions import (
        DEFAULT_REMOTE_PERMISSIONS,
        load_device_remote_permissions,
        save_device_remote_permissions,
    )

    monkeypatch.setattr(
        remote_actions, "load_remote_permissions",
        lambda: dict(DEFAULT_REMOTE_PERMISSIONS),
    )
    path = tmp_path / "remote_device_permissions.json"
    phone_a = "a" * 32
    phone_b = "b" * 32
    updated_a = dict(DEFAULT_REMOTE_PERMISSIONS, keyboard=False, power=False, screen_view=True)

    save_device_remote_permissions(phone_a, updated_a, path)
    restored_a = load_device_remote_permissions(phone_a, path)
    restored_b = load_device_remote_permissions(phone_b, path)

    assert restored_a == dict(DEFAULT_REMOTE_PERMISSIONS, keyboard=False, power=False)
    assert restored_b == DEFAULT_REMOTE_PERMISSIONS
    assert load_device_remote_permissions(phone_a, path)["keyboard"] is False


def test_device_permission_store_rejects_invalid_identity(tmp_path, monkeypatch):
    import core.remote_actions as remote_actions
    from core.remote_actions import (
        DEFAULT_REMOTE_PERMISSIONS,
        load_device_remote_permissions,
        save_device_remote_permissions,
    )

    monkeypatch.setattr(
        remote_actions, "load_remote_permissions",
        lambda: dict(DEFAULT_REMOTE_PERMISSIONS),
    )
    path = tmp_path / "remote_device_permissions.json"
    assert load_device_remote_permissions("invalid", path) == dict(DEFAULT_REMOTE_PERMISSIONS, screen_view=False)
    with pytest.raises(ValueError):
        save_device_remote_permissions("invalid", {"keyboard": False}, path)

