from __future__ import annotations

import os
import sys
from pathlib import Path

from core import settings as settings_module
from core.utils import paths


def _set_installed_app(
    monkeypatch,
    install_dir: Path,
    app_data: Path,
    local_data: Path,
    resources: Path,
    default_settings: str = "[ui]\ntheme = dark\n",
) -> None:
    install_dir.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    (resources / "config").mkdir(parents=True, exist_ok=True)
    (resources / "config" / "settings.conf").write_text(
        default_settings, encoding="utf-8"
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(install_dir / "VPadConnect.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(resources), raising=False)
    monkeypatch.setenv("APPDATA", str(app_data))
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))


def test_paths_use_roaming_and_local_appdata_and_ignore_cwd_and_meipass(
    monkeypatch, tmp_path
):
    install_dir = tmp_path / "Program Files" / "VPadConnect"
    resources = tmp_path / "_MEI12345"
    roaming = tmp_path / "Roaming AppData"
    local = tmp_path / "Local AppData"
    cwd = tmp_path / "unrelated-working-directory"
    cwd.mkdir()
    _set_installed_app(monkeypatch, install_dir, roaming, local, resources)
    monkeypatch.chdir(cwd)

    assert paths.config_path("settings.conf") == roaming / "VPadConnect" / "settings.conf"
    assert paths.local_path("logs", "mapper.log") == (
        local / "VPadConnect" / "logs" / "mapper.log"
    )
    assert paths.resource_path("config", "settings.conf") == (
        resources / "config" / "settings.conf"
    )
    assert paths.resolve_data_path("logs/mapper.log") == (
        local / "VPadConnect" / "logs" / "mapper.log"
    )
    assert paths.resolve_data_path(install_dir / "logs" / "mapper.log") == (
        local / "VPadConnect" / "logs" / "mapper.log"
    )
    assert paths.config_root() != cwd
    assert paths.local_root() != resources


def test_source_paths_are_independent_of_current_working_directory(monkeypatch, tmp_path):
    source_root = tmp_path / "checkout"
    (source_root / "config").mkdir(parents=True)
    (source_root / "config" / "settings.conf").write_text(
        "[ui]\ntheme = dark\n", encoding="utf-8"
    )
    roaming = tmp_path / "roaming"
    local = tmp_path / "local"
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(paths, "_source_root", lambda: source_root)
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.chdir(cwd)

    assert paths.config_path("settings.conf") == roaming / "VPadConnect" / "settings.conf"
    assert paths.local_path("logs") == local / "VPadConnect" / "logs"
    paths.initialize_storage()
    manager = settings_module.SettingsManager()
    assert manager.path == roaming / "VPadConnect" / "settings.conf"
    assert manager.path.is_file()
    assert not (cwd / "settings.conf").exists()
    assert not (source_root / "settings.conf").exists()


def test_appdata_fallback_is_sensible_when_windows_environment_is_missing(
    monkeypatch, tmp_path
):
    home = tmp_path / "home"
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))

    if os.name == "nt":
        assert paths.config_root() == home / "AppData" / "Roaming" / "VPadConnect"
        assert paths.local_root() == home / "AppData" / "Local" / "VPadConnect"
    else:
        assert paths.config_root() == home / ".config" / "VPadConnect"
        assert paths.local_root() == home / ".local" / "share" / "VPadConnect"


def test_bundled_default_is_copied_to_roaming_settings_and_never_modified(
    monkeypatch, tmp_path
):
    install_dir = tmp_path / "Program Files" / "VPadConnect"
    roaming = tmp_path / "Roaming"
    local = tmp_path / "Local"
    resources = tmp_path / "resources"
    default_text = "[ui]\ntheme = dark\nlanguage = eng\n"
    _set_installed_app(monkeypatch, install_dir, roaming, local, resources, default_text)

    paths.initialize_storage()
    manager = settings_module.SettingsManager()
    settings_file = roaming / "VPadConnect" / "settings.conf"
    assert settings_file.read_text(encoding="utf-8") == default_text

    manager.config.set("ui", "theme", "light")
    manager.save()
    manager.config.clear()
    reloaded = settings_module.SettingsManager()
    assert reloaded.config.get("ui", "theme") == "light"
    assert (resources / "config" / "settings.conf").read_text(encoding="utf-8") == default_text
    assert not (install_dir / "config" / "settings.conf").exists()


def test_custom_legacy_settings_profiles_hotkeys_and_tls_identity_migrate_idempotently(
    monkeypatch, tmp_path
):
    install_dir = tmp_path / "Program Files" / "VPadConnect"
    roaming = tmp_path / "Roaming"
    local = tmp_path / "Local"
    resources = tmp_path / "resources"
    _set_installed_app(monkeypatch, install_dir, roaming, local, resources)

    old_settings = install_dir / "config" / "settings.conf"
    old_settings.parent.mkdir(parents=True)
    old_settings.write_text("[ui]\ntheme = light\n", encoding="utf-8")
    old_profiles = install_dir / "profiles" / "user"
    old_profiles.mkdir(parents=True)
    (old_profiles / "Racing.json").write_text(
        '{"_meta":{"name":"Racing"},"device":{"poll_interval_ms":"2"}}',
        encoding="utf-8",
    )
    (install_dir / "profiles" / "GenericGamepads.json").write_text(
        '{"Wheel":{"left_x":1}}', encoding="utf-8"
    )
    (install_dir / "hotkeys.json").write_text('{"start":"F8"}', encoding="utf-8")
    (install_dir / "trusted_clients.json").write_text(
        '{"client-hash":"Phone"}', encoding="utf-8"
    )
    (install_dir / "remote_permissions.json").write_text(
        '{"schema_version":2,"keyboard":false}', encoding="utf-8"
    )
    (install_dir / "logs").mkdir()
    (install_dir / "logs" / "mapper.log").write_text("old log", encoding="utf-8")
    security = install_dir / "remote_security"
    security.mkdir()
    (security / "server.crt").write_bytes(b"legacy certificate")
    (security / "server.key").write_bytes(b"legacy private key")
    (security / "web_server.crt").write_bytes(b"legacy web certificate")
    (security / "web_server.key").write_bytes(b"legacy web private key")

    paths.initialize_storage()
    expected_config = roaming / "VPadConnect"
    expected_local = local / "VPadConnect"
    assert (expected_config / "settings.conf").read_text(encoding="utf-8") == (
        "[ui]\ntheme = light\n"
    )
    assert (expected_config / "profiles" / "user" / "Racing.json").is_file()
    assert (expected_config / "profiles" / "GenericGamepads.json").is_file()
    assert (expected_config / "hotkeys.json").read_text(encoding="utf-8") == (
        '{"start":"F8"}'
    )
    assert (expected_local / "trusted_clients.json").is_file()
    assert (expected_local / "remote_permissions.json").is_file()
    assert (expected_local / "logs" / "mapper.log").read_text(encoding="utf-8") == (
        "old log"
    )
    for name, value in (
        ("server.crt", b"legacy certificate"),
        ("server.key", b"legacy private key"),
        ("web_server.crt", b"legacy web certificate"),
        ("web_server.key", b"legacy web private key"),
    ):
        assert (expected_local / "remote_security" / name).read_bytes() == value

    copied_profile = expected_config / "profiles" / "user" / "Racing.json"
    copied_key = expected_local / "remote_security" / "server.key"
    before = (copied_profile.stat().st_mtime_ns, copied_key.stat().st_mtime_ns)
    paths.initialize_storage()
    after = (copied_profile.stat().st_mtime_ns, copied_key.stat().st_mtime_ns)
    assert after == before
    assert old_settings.is_file()
    assert (old_profiles / "Racing.json").is_file()
    assert (security / "server.key").is_file()


def test_existing_appdata_wins_and_profile_collisions_keep_both_copies(
    monkeypatch, tmp_path
):
    install_dir = tmp_path / "Program Files" / "VPadConnect"
    roaming = tmp_path / "Roaming"
    local = tmp_path / "Local"
    resources = tmp_path / "resources"
    _set_installed_app(monkeypatch, install_dir, roaming, local, resources)

    config_root = roaming / "VPadConnect"
    profiles = config_root / "profiles" / "user"
    profiles.mkdir(parents=True)
    (config_root / "settings.conf").write_text(
        "[ui]\ntheme = dark\n", encoding="utf-8"
    )
    (profiles / "Default.json").write_text("current profile", encoding="utf-8")
    legacy_config = install_dir / "config" / "settings.conf"
    legacy_config.parent.mkdir(parents=True)
    legacy_config.write_text("[ui]\ntheme = light\n", encoding="utf-8")
    legacy_profiles = install_dir / "profiles" / "user"
    legacy_profiles.mkdir(parents=True)
    (legacy_profiles / "Default.json").write_text("older profile", encoding="utf-8")
    (legacy_profiles / "New.json").write_text("new profile", encoding="utf-8")

    paths.initialize_storage()

    assert (config_root / "settings.conf").read_text(encoding="utf-8") == (
        "[ui]\ntheme = dark\n"
    )
    assert (profiles / "Default.json").read_text(encoding="utf-8") == "current profile"
    assert (profiles / "New.json").read_text(encoding="utf-8") == "new profile"
    assert (legacy_profiles / "Default.json").read_text(encoding="utf-8") == "older profile"


def test_previous_local_appdata_layout_moves_preferences_to_roaming(monkeypatch, tmp_path):
    install_dir = tmp_path / "Program Files" / "VPadConnect"
    roaming = tmp_path / "Roaming"
    local = tmp_path / "Local"
    resources = tmp_path / "resources"
    _set_installed_app(monkeypatch, install_dir, roaming, local, resources)

    old_root = local / "VPadConnect"
    old_settings = old_root / "config" / "settings.conf"
    old_settings.parent.mkdir(parents=True)
    old_settings.write_text("[ui]\ntheme = light\n", encoding="utf-8")
    old_profile = old_root / "profiles" / "user" / "Arcade.json"
    old_profile.parent.mkdir(parents=True)
    old_profile.write_text('{"_meta":{"name":"Arcade"}}', encoding="utf-8")
    old_identity = old_root / "remote_security" / "server.key"
    old_identity.parent.mkdir(parents=True)
    old_identity.write_bytes(b"existing TLS private key")

    paths.initialize_storage()

    new_root = roaming / "VPadConnect"
    assert (new_root / "settings.conf").read_text(encoding="utf-8") == (
        "[ui]\ntheme = light\n"
    )
    assert (new_root / "profiles" / "user" / "Arcade.json").read_text(
        encoding="utf-8"
    ) == '{"_meta":{"name":"Arcade"}}'
    assert old_identity.read_bytes() == b"existing TLS private key"
    assert old_settings.is_file()
    assert old_profile.is_file()


def test_bundled_settings_template_is_not_migrated_as_user_preferences(
    monkeypatch, tmp_path
):
    install_dir = tmp_path / "Program Files" / "VPadConnect"
    roaming = tmp_path / "Roaming"
    local = tmp_path / "Local"
    resources = tmp_path / "resources"
    default = "[ui]\ntheme = dark\n"
    _set_installed_app(monkeypatch, install_dir, roaming, local, resources, default)
    bundled_at_install = install_dir / "config" / "settings.conf"
    bundled_at_install.parent.mkdir(parents=True)
    bundled_at_install.write_text(default, encoding="utf-8")

    paths.initialize_storage()
    settings_file = roaming / "VPadConnect" / "settings.conf"
    assert not settings_file.exists()

    manager = settings_module.SettingsManager()
    assert manager.path == settings_file
    assert settings_file.read_text(encoding="utf-8") == default
    assert bundled_at_install.read_text(encoding="utf-8") == default


def test_mouse_settings_json_is_not_referenced_as_runtime_storage():
    source = Path(__file__).resolve().parents[1]
    references = []
    for path in (*source.joinpath("core").rglob("*.py"), *source.joinpath("ui").rglob("*.py")):
        if "mouse_settings.json" in path.read_text(encoding="utf-8"):
            references.append(path)
    assert references == []
