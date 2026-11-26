"""Reusable per-controller digital input mapping rules."""

from __future__ import annotations

import re
from typing import Any

from core.utils.paths import resource_path


X360_BUTTON_NAMES = (
    "a", "b", "x", "y",
    "lb", "rb",
    "back", "start",
    "l3", "r3",
    "dpad_up", "dpad_down", "dpad_left", "dpad_right",
)

DEFAULT_X360_TARGETS = {
    "cross": "x360:a",
    "circle": "x360:b",
    "square": "x360:x",
    "triangle": "x360:y",
    "l1": "x360:lb",
    "r1": "x360:rb",
    "share": "x360:back",
    "option": "x360:start",
    "l3": "x360:l3",
    "r3": "x360:r3",
    "dpad_up": "x360:dpad_up",
    "dpad_down": "x360:dpad_down",
    "dpad_left": "x360:dpad_left",
    "dpad_right": "x360:dpad_right",
}

_KEY_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 _-]{1,32}$")
_ALLOWED_TARGETS = {
    "disabled",
    "keyboard",
    *(f"x360:{name}" for name in X360_BUTTON_NAMES),
    "mouse:left",
    "mouse:right",
    "mouse:middle",
}
_DPAD_SOURCES = {"dpad_up", "dpad_down", "dpad_left", "dpad_right"}


def load_controller_profile(controller_type: str) -> dict[str, Any]:
    """Load a built-in HID profile without exposing mutable shared state."""
    try:
        with resource_path("profiles", f"{controller_type}.json").open(
            "r", encoding="utf-8"
        ) as config:
            import json

            value = json.load(config)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def profile_button_sources(profile: dict[str, Any]) -> list[str]:
    """Return the digital controls described by a static HID profile."""
    buttons = profile.get("buttons", {})
    sources = [
        str(name)
        for name, config in buttons.items()
        if isinstance(name, str) and isinstance(config, dict)
    ] if isinstance(buttons, dict) else []

    if isinstance(profile.get("dpad_hat"), dict):
        sources.extend(sorted(_DPAD_SOURCES))

    return list(dict.fromkeys(sources))


def default_controller_layout(profile: dict[str, Any]) -> dict[str, Any]:
    """Build a backwards-compatible layout that preserves existing X360 mappings."""
    buttons: dict[str, dict[str, str]] = {}
    for source in profile_button_sources(profile):
        buttons[source] = {
            "target": DEFAULT_X360_TARGETS.get(source, "disabled"),
            "key": "",
            "normally": "open",
        }
    return {"version": 1, "buttons": buttons}


def is_valid_keyboard_key(value: Any) -> bool:
    """Return whether a value is a single key name accepted by the backend."""
    return bool(_KEY_NAME_PATTERN.fullmatch(str(value).strip()))


def normalize_controller_layout(
    layout: Any,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Validate a saved layout and fill newly introduced profile controls."""
    defaults = default_controller_layout(profile)
    stored_buttons = layout.get("buttons", {}) if isinstance(layout, dict) else {}
    if not isinstance(stored_buttons, dict):
        stored_buttons = {}

    normalized: dict[str, dict[str, str]] = {}
    for source, default in defaults["buttons"].items():
        configured = stored_buttons.get(source, {})
        if not isinstance(configured, dict):
            configured = {}

        target = str(configured.get("target", default["target"])).strip().lower()
        if target not in _ALLOWED_TARGETS:
            target = "disabled"

        key = str(configured.get("key", "")).strip().lower()
        if not is_valid_keyboard_key(key):
            key = ""

        polarity = str(
            configured.get("normally", configured.get("polarity", "open"))
        ).strip().lower().replace("-", "_").replace(" ", "_")
        if polarity in {"closed", "nc", "normally_closed"}:
            polarity = "closed"
        else:
            polarity = "open"

        # Hat-switch directions are mutually encoded positions, not independent
        # electrical contacts. Inverting a neutral hat would falsely press all
        # four directions, so NO/NC is not applicable to those sources.
        if source in _DPAD_SOURCES:
            polarity = "open"

        normalized[source] = {
            "target": target,
            "key": key if target == "keyboard" else "",
            "normally": polarity,
        }

    return {"version": 1, "buttons": normalized}


def resolve_x360_button_states(
    source_states: dict[str, bool],
    layout: dict[str, Any],
) -> dict[str, bool]:
    """Combine all physical inputs routed to each virtual Xbox 360 control."""
    mapped = {name: False for name in X360_BUTTON_NAMES}
    button_layout = layout.get("buttons", {}) if isinstance(layout, dict) else {}
    if not isinstance(button_layout, dict):
        return mapped

    for source, entry in button_layout.items():
        if not source_states.get(source, False) or not isinstance(entry, dict):
            continue
        target = str(entry.get("target", "disabled"))
        if target.startswith("x360:"):
            output_name = target.partition(":")[2]
            if output_name in mapped:
                mapped[output_name] = True
    return mapped


def decode_button_polarity(raw_pressed: bool, normally: str = "open") -> bool:
    """Convert an active-high or active-low raw switch state to pressed=True."""
    is_pressed = bool(raw_pressed)
    return not is_pressed if str(normally).strip().lower() in {
        "closed", "nc", "normally_closed", "normally closed"
    } else is_pressed
