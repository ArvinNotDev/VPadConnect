"""Low-overhead keyboard and mouse actions for physical controller layouts."""

from __future__ import annotations

import logging
import threading
from typing import Any

try:
    import keyboard as _keyboard
except Exception:  # pragma: no cover - optional native backend
    _keyboard = None

logger = logging.getLogger("vpadconnect.input_actions")
_DEFAULT_MOUSE_BACKEND = object()


class InputActionDispatcher:
    """Dispatch held physical controls to keyboard and mouse outputs.

    Hold ownership is shared between instances, so two controllers mapped to
    the same key or mouse button cannot release each other's held output.
    """

    _lock = threading.RLock()
    _keyboard_holders: dict[str, set[object]] = {}
    _mouse_holders: dict[str, set[object]] = {}

    def __init__(
        self,
        keyboard_backend: Any = _keyboard,
        mouse_backend: Any = _DEFAULT_MOUSE_BACKEND,
    ) -> None:
        self.keyboard_backend = keyboard_backend
        if mouse_backend is _DEFAULT_MOUSE_BACKEND:
            try:
                from core.mouse import Mouse
            except Exception:
                Mouse = None
            mouse_backend = Mouse
        self.mouse_backend = mouse_backend
        self._owner = object()
        self._active_keys: set[str] = set()
        self._active_mouse_buttons: set[str] = set()

    def update(self, source_states: dict[str, bool], layout: dict[str, Any]) -> None:
        """Apply only state transitions; repeated HID reports do not spam events."""
        desired_keys: set[str] = set()
        desired_mouse_buttons: set[str] = set()
        button_layout = layout.get("buttons", {}) if isinstance(layout, dict) else {}

        if isinstance(button_layout, dict):
            for source, entry in button_layout.items():
                if not source_states.get(source, False) or not isinstance(entry, dict):
                    continue

                target = str(entry.get("target", "disabled")).lower()
                if target == "keyboard":
                    key = str(entry.get("key", "")).strip().lower()
                    if key and self.keyboard_backend is not None:
                        desired_keys.add(key)
                elif target.startswith("mouse:"):
                    button = target.partition(":")[2]
                    if button in {"left", "right", "middle"} and self.mouse_backend is not None:
                        desired_mouse_buttons.add(button)

        with self._lock:
            self._apply_transitions(
                self._keyboard_holders,
                self._active_keys,
                desired_keys,
                self.keyboard_backend,
                "press",
                "release",
            )
            self._apply_transitions(
                self._mouse_holders,
                self._active_mouse_buttons,
                desired_mouse_buttons,
                self.mouse_backend,
                "buttonDown",
                "buttonUp",
            )

    def release_all(self) -> None:
        """Release every key and mouse button currently owned by this mapper."""
        with self._lock:
            self._apply_transitions(
                self._keyboard_holders,
                self._active_keys,
                set(),
                self.keyboard_backend,
                "press",
                "release",
            )
            self._apply_transitions(
                self._mouse_holders,
                self._active_mouse_buttons,
                set(),
                self.mouse_backend,
                "buttonDown",
                "buttonUp",
            )

    def _apply_transitions(
        self,
        holders: dict[str, set[object]],
        active: set[str],
        desired: set[str],
        backend: Any,
        press_method: str,
        release_method: str,
    ) -> None:
        for value in active - desired:
            owners = holders.get(value)
            if owners is None:
                continue
            owners.discard(self._owner)
            if not owners:
                holders.pop(value, None)
                self._call_backend(backend, release_method, value)

        for value in desired - active:
            owners = holders.setdefault(value, set())
            if not owners:
                self._call_backend(backend, press_method, value)
            owners.add(self._owner)

        active.clear()
        active.update(desired)

    @staticmethod
    def _call_backend(backend: Any, method: str, value: str) -> None:
        if backend is None:
            return
        try:
            getattr(backend, method)(value)
        except Exception:
            logger.warning(
                "Could not send %s action for %s", method, value, exc_info=True
            )
