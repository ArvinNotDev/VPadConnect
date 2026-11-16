"""
Unit tests for core.profile_manager.ProfileManager.
"""

from __future__ import annotations

import json
import tempfile
import shutil
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeSettingsManager:
    """Minimal stand-in for SettingsManager used in tests."""

    def __init__(self):
        self.config = _make_config()
        self._saved = False

    def save(self):
        self._saved = True


def _make_config():
    """Build a configparser with sensible defaults."""
    import configparser
    cfg = configparser.ConfigParser()
    cfg["device"] = {
        "polling_rate": "1.0",
        "auto_reconnect": "true",
        "dpad_as_mouse": "true",
        "left_stick_deadzone": "0.100000",
        "right_stick_deadzone": "0.100000",
        "left_stick_invert_x": "false",
        "left_stick_invert_y": "true",
        "right_stick_invert_x": "false",
        "right_stick_invert_y": "false",
        "invert_buttons": "false",
        "mouse_mode": "false",
        "mouse_sensitivity": "1.000000",
    }
    cfg["ui"] = {"language": "eng", "theme": "dark"}
    cfg["developer"] = {
        "debug": "false",
        "raw_hid_debug": "false",
        "log_to_file": "false",
        "log_file_path": "logs/mapper.log",
    }
    return cfg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProfileManager:
    """Tests for ProfileManager CRUD operations."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.settings = FakeSettingsManager()
        # Patch data_path so profiles go into a temp directory
        self._patcher = mock.patch(
            "core.profile_manager.config_path",
            side_effect=lambda *parts: Path(self.tmpdir).joinpath(*parts),
        )
        self._patcher.start()
        from core.profile_manager import ProfileManager
        self.pm = ProfileManager(self.settings)

    def teardown_method(self):
        self._patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # -- Save / Load --

    def test_save_and_list(self):
        assert self.pm.save_profile("My Profile", description="Test")
        profiles = self.pm.list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "My Profile"

    def test_save_empty_name_fails(self):
        assert not self.pm.save_profile("", description="")
        assert not self.pm.save_profile("   ", description="")

    def test_save_duplicate_fails_without_overwrite(self):
        self.pm.save_profile("P1")
        assert not self.pm.save_profile("P1", overwrite=False)

    def test_save_duplicate_with_overwrite(self):
        self.pm.save_profile("P1", description="first")
        assert self.pm.save_profile("P1", description="second", overwrite=True)
        data = self.pm.get_profile("P1")
        assert data["_meta"]["description"] == "second"

    def test_load_nonexistent_returns_none(self):
        assert self.pm.get_profile("nope") is None

    # -- Delete --

    def test_delete(self):
        self.pm.save_profile("ToDelete")
        assert self.pm.delete_profile("ToDelete")
        assert self.pm.get_profile("ToDelete") is None

    def test_delete_nonexistent(self):
        assert not self.pm.delete_profile("nope")

    # -- Activate --

    def test_activate(self):
        self.pm.save_profile("Active")
        assert self.pm.activate_profile("Active")
        assert self.pm.get_active_profile_name() == "Active"

    def test_activate_nonexistent(self):
        assert not self.pm.activate_profile("missing")

    # -- Rename --

    def test_rename(self):
        self.pm.save_profile("Old")
        assert self.pm.rename_profile("Old", "New")
        assert self.pm.get_profile("New") is not None
        assert self.pm.get_profile("Old") is None

    def test_rename_to_existing_fails(self):
        self.pm.save_profile("A")
        self.pm.save_profile("B")
        assert not self.pm.rename_profile("A", "B")

    # -- Duplicate --

    def test_duplicate(self):
        self.pm.save_profile("Original", description="orig")
        assert self.pm.duplicate_profile("Original", "Copy")
        data = self.pm.get_profile("Copy")
        assert data is not None
        assert data["_meta"]["name"] == "Copy"

    def test_duplicate_nonexistent(self):
        assert not self.pm.duplicate_profile("nope", "copy")

    # -- Settings round-trip --

    def test_settings_round_trip(self):
        """Activating a profile should update the settings config."""
        self.settings.config.set("device", "poll_interval_ms", "5.0")
        self.settings.config["profile"] = {"active": "personal"}
        self.pm.save_profile("Custom")
        self.settings.config.set("device", "poll_interval_ms", "1.0")
        self.pm.activate_profile("Custom")
        assert self.settings.config.get("device", "poll_interval_ms") == "5.0"
        assert self.settings.config.get("profile", "active") == "Custom"

    def test_malformed_profile_root_is_ignored(self):
        bad_path = Path(self.tmpdir) / "profiles" / "user" / "Malformed.json"
        bad_path.write_text("[]", encoding="utf-8")
        assert self.pm.list_profiles() == []

    def test_profile_image_metadata_is_portable_and_cleanup_is_scoped(self):
        self.pm.save_profile("With Image")
        source = Path(self.tmpdir) / "source.png"
        source.write_bytes(b"not-a-real-image")

        assert self.pm.set_profile_image("With Image", str(source))
        profile_data = self.pm.get_profile("With Image")
        metadata = profile_data["_meta"]
        assert metadata["image"] == "With_Image.png"
        assert self.pm.get_profile_image_path("With Image") is not None

        outside = Path(self.tmpdir) / "outside.txt"
        outside.write_text("keep me", encoding="utf-8")
        metadata["image"] = str(outside)
        profile_path = Path(self.tmpdir) / "profiles" / "user" / "With_Image.json"
        profile_path.write_text(json.dumps(profile_data), encoding="utf-8")
        assert self.pm.remove_profile_image("With Image")
        assert outside.exists()

    # -- Default profile --

    def test_create_default_profile(self):
        self.pm.create_default_profile()
        profiles = self.pm.list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "Default"

    def test_create_default_profile_idempotent(self):
        self.pm.create_default_profile()
        self.pm.create_default_profile()
        assert len(self.pm.list_profiles()) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
