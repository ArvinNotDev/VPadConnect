from __future__ import annotations

import sys
from types import SimpleNamespace

import main


def test_startup_splash_is_optional_in_source_execution(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyi_splash", None)

    assert main._get_bootloader_splash() is None


def test_disabled_bootloader_splash_is_ignored(monkeypatch):
    module = SimpleNamespace(is_alive=lambda: False)
    monkeypatch.setitem(sys.modules, "pyi_splash", module)

    assert main._get_bootloader_splash() is None


def test_active_bootloader_splash_updates_and_closes(monkeypatch):
    calls = []
    module = SimpleNamespace(
        is_alive=lambda: True,
        update_text=lambda message: calls.append(("update", message)),
        close=lambda: calls.append(("close", None)),
    )
    monkeypatch.setitem(sys.modules, "pyi_splash", module)

    splash = main._get_bootloader_splash()
    main._update_splash(splash, "Loading the main window...")
    main._close_splash(splash)

    assert calls == [
        ("update", "Loading the main window..."),
        ("close", None),
    ]


def test_splash_communication_errors_do_not_escape():
    class BrokenSplash:
        def update_text(self, _message):
            raise RuntimeError("bootloader pipe is closed")

        def close(self):
            raise RuntimeError("bootloader pipe is closed")

    main._update_splash(BrokenSplash(), "Starting")
    main._close_splash(BrokenSplash())
