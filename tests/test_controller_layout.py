"""Tests for per-controller button routes, switch polarity, and persistence."""

from __future__ import annotations

import json

from core.input_actions import InputActionDispatcher
from core.input_layout import (
    decode_button_polarity,
    default_controller_layout,
    load_controller_profile,
    normalize_controller_layout,
    resolve_x360_button_states,
)
from core.profile_manager import ProfileManager
from core.settings import SettingsManager


def test_unojoy_default_layout_preserves_existing_x360_mapping():
    profile = load_controller_profile("Unojoy")
    layout = default_controller_layout(profile)

    assert layout["buttons"]["cross"]["target"] == "x360:a"
    assert layout["buttons"]["circle"]["target"] == "x360:b"
    assert layout["buttons"]["l1"]["target"] == "x360:lb"
    assert layout["buttons"]["dpad_up"]["target"] == "x360:dpad_up"
    assert layout["buttons"]["r3"]["normally"] == "open"


def test_normally_open_and_closed_polarity_are_independent():
    assert decode_button_polarity(False, "open") is False
    assert decode_button_polarity(True, "open") is True
    assert decode_button_polarity(False, "closed") is True
    assert decode_button_polarity(True, "closed") is False


def test_normally_closed_input_routes_to_x360_button():
    layout = {
        "buttons": {
            "cross": {"target": "x360:a"},
            "circle": {"target": "x360:b"},
            "square": {"target": "x360:a"},
        }
    }
    pressed_sources = {
        "cross": decode_button_polarity(False, "closed"),
        "circle": False,
        "square": False,
    }
    mapped = resolve_x360_button_states(pressed_sources, layout)

    assert mapped["a"] is True
    assert mapped["b"] is False


def test_layout_normalization_supports_mixed_polarities_and_output_types():
    profile = load_controller_profile("Unojoy")
    layout = normalize_controller_layout(
        {
            "buttons": {
                "cross": {
                    "target": "keyboard",
                    "key": "Space",
                    "normally": "normally_closed",
                },
                "circle": {
                    "target": "mouse:left",
                    "normally": "normally_open",
                },
                "square": {
                    "target": "x360:rb",
                    "normally": "open",
                },
                "triangle": {
                    "target": "not-an-output",
                    "normally": "closed",
                },
            }
        },
        profile,
    )

    assert layout["buttons"]["cross"] == {
        "target": "keyboard",
        "key": "space",
        "normally": "closed",
    }
    assert layout["buttons"]["circle"]["target"] == "mouse:left"
    assert layout["buttons"]["circle"]["normally"] == "open"
    assert layout["buttons"]["square"]["target"] == "x360:rb"
    assert layout["buttons"]["triangle"]["target"] == "disabled"
    assert layout["buttons"]["dpad_up"]["normally"] == "open"


def test_controller_layout_settings_are_isolated_and_persisted(tmp_path):
    settings_path = tmp_path / "settings.conf"
    settings = SettingsManager(path=settings_path)
    expected = {
        "version": 1,
        "buttons": {
            "cross": {
                "target": "keyboard",
                "key": "space",
                "normally": "closed",
            }
        },
    }

    settings.set_controller_layout_settings("unojoy-unit-a", expected)
    settings.save()

    reloaded = SettingsManager(path=settings_path)
    assert reloaded.get_controller_layout_settings("unojoy-unit-a") == expected
    assert reloaded.get_controller_layout_settings("unojoy-unit-b") == {}


def test_active_profile_stores_layout_and_missing_profile_layout_is_cleared(
    tmp_path, monkeypatch
):
    settings = SettingsManager(path=tmp_path / "settings.conf")
    monkeypatch.setattr(
        "core.profile_manager.config_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    manager = ProfileManager(settings)
    section = settings._controller_layout_section("unojoy-unit-a")
    saved_layout = {
        "version": 1,
        "buttons": {
            "cross": {
                "target": "keyboard",
                "key": "space",
                "normally": "closed",
            }
        },
    }

    settings.set_controller_layout_settings("unojoy-unit-a", saved_layout)
    assert manager.save_profile("UnoJoy Game")
    assert manager.activate_profile("UnoJoy Game")

    changed_layout = {
        "version": 1,
        "buttons": {
            "cross": {
                "target": "mouse:left",
                "key": "",
                "normally": "open",
            }
        },
    }
    assert manager.save_controller_layout(
        "unojoy-unit-a", changed_layout, profile_name="UnoJoy Game"
    )
    profile = manager.get_profile("UnoJoy Game")
    assert json.loads(profile[section]["layout"]) == changed_layout

    settings.config.remove_section(section)
    assert manager.save_profile("Clean Profile")
    settings.set_controller_layout_settings("unojoy-unit-a", changed_layout)
    assert manager.activate_profile("Clean Profile")
    assert settings.get_controller_layout_settings("unojoy-unit-a") == {}


def test_controller_layout_is_included_in_named_profiles(tmp_path, monkeypatch):
    settings = SettingsManager(path=tmp_path / "settings.conf")
    monkeypatch.setattr(
        "core.profile_manager.config_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    manager = ProfileManager(settings)
    original = {
        "version": 1,
        "buttons": {
            "cross": {
                "target": "keyboard",
                "key": "space",
                "normally": "closed",
            }
        },
    }
    changed = {
        "version": 1,
        "buttons": {
            "cross": {
                "target": "mouse:right",
                "key": "",
                "normally": "open",
            }
        },
    }

    settings.set_controller_layout_settings("unojoy-unit-a", original)
    assert manager.save_profile("UnoJoy Racing", description="Per-game mapping")
    settings.set_controller_layout_settings("unojoy-unit-a", changed)
    assert manager.activate_profile("UnoJoy Racing")

    assert settings.get_controller_layout_settings("unojoy-unit-a") == original


class _FakeKeyboard:
    def __init__(self):
        self.events = []

    def press(self, key):
        self.events.append(("press", key))

    def release(self, key):
        self.events.append(("release", key))


class _FakeMouse:
    def __init__(self):
        self.events = []

    def buttonDown(self, button):
        self.events.append(("down", button))

    def buttonUp(self, button):
        self.events.append(("up", button))


def test_keyboard_and_mouse_routes_are_edge_triggered_and_released():
    keyboard = _FakeKeyboard()
    mouse = _FakeMouse()
    dispatcher = InputActionDispatcher(
        keyboard_backend=keyboard,
        mouse_backend=mouse,
    )
    layout = {
        "buttons": {
            "cross": {"target": "keyboard", "key": "space"},
            "circle": {"target": "mouse:left"},
        }
    }

    dispatcher.update({"cross": True, "circle": True}, layout)
    dispatcher.update({"cross": True, "circle": True}, layout)
    dispatcher.update({"cross": False, "circle": True}, layout)
    dispatcher.update({"cross": False, "circle": False}, layout)

    assert keyboard.events == [("press", "space"), ("release", "space")]
    assert mouse.events == [("down", "left"), ("up", "left")]


def test_shared_keyboard_key_is_not_released_until_last_controller_releases():
    keyboard = _FakeKeyboard()
    first = InputActionDispatcher(keyboard_backend=keyboard, mouse_backend=_FakeMouse())
    second = InputActionDispatcher(keyboard_backend=keyboard, mouse_backend=_FakeMouse())
    layout_a = {"buttons": {"cross": {"target": "keyboard", "key": "f1"}}}
    layout_b = {"buttons": {"circle": {"target": "keyboard", "key": "f1"}}}

    first.update({"cross": True}, layout_a)
    second.update({"circle": True}, layout_b)
    first.release_all()
    assert keyboard.events == [("press", "f1")]

    second.release_all()
    assert keyboard.events == [("press", "f1"), ("release", "f1")]
