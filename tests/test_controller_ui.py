"""Headless regressions for controller UI behavior and theme palettes."""

from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib
import sys
import types
from unittest.mock import patch

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QListWidget, QWidget
from ui.notifications import StatusToast
from ui.pages.raw_hid_terminal import RawHidTerminalDialog

from ui.pages.modal.add_controller import AddControllerDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _native_input_stubs():
    pyautogui = types.ModuleType("pyautogui")
    pyautogui.PAUSE = 0.0
    pyautogui.FAILSAFE = True
    pyautogui.FailSafeException = type("FailSafeException", (Exception,), {})
    return {
        "vgamepad": types.ModuleType("vgamepad"),
        "keyboard": types.ModuleType("keyboard"),
        "pyautogui": pyautogui,
    }


def _flush_deferred_deletes(qapp):
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_add_controller_refresh_action_and_empty_state(qapp):
    dialog = AddControllerDialog()
    refresh_calls = []
    dialog.refresh_requested.connect(lambda: refresh_calls.append(True))

    dialog.emu_list.addItem("Emulate Xbox")
    dialog.emu_list.setCurrentRow(0)
    dialog.set_hid_devices(["DualSense", "DualShock 4"])
    assert dialog.hid_list.count() == 2
    assert dialog.hid_list.currentRow() == 0
    assert dialog._accept_button.isEnabled()

    dialog.refresh_button.click()
    assert refresh_calls == [True]

    dialog.set_hid_devices([])
    assert dialog.hid_list.count() == 1
    assert dialog.hid_list.currentRow() == -1
    assert not dialog._accept_button.isEnabled()
    assert dialog.get_selections()[0] is None

    dialog.deleteLater()
    _flush_deferred_deletes(qapp)


class _FakeXInputInstance:
    def __init__(self, device_path):
        self.device_path = device_path
        self.supports_rumble = True
        self._last_monitor = None

    def set_xinput_vibration(self, _left, _right):
        pass


def test_input_test_uses_light_palette_and_hides_web_only_fields(qapp):
    with patch.dict(sys.modules, _native_input_stubs()):
        page_module = importlib.import_module("ui.pages.controllers")
        web_card = page_module.X360TestCard(
            _FakeXInputInstance("web-session-123"), "Phone", True
        )
        assert web_card.battery_icon.width() == 22
        assert web_card.battery_info.isHidden()
        assert web_card.vibration_button.isHidden()
        web_card.apply_theme("light")
        assert "#ffffff" in web_card.styleSheet()
        assert "#edf3fc" in web_card.surface.styleSheet()
        web_card.view_timer.stop()
        web_card.deleteLater()

        physical_card = page_module.X360TestCard(
            _FakeXInputInstance("physical-controller"), "DualSense", True
        )
        assert physical_card.battery_icon.width() == 22
        assert not physical_card.battery_info.isHidden()
        assert not physical_card.vibration_button.isHidden()
        physical_card.apply_theme("light")
        assert "#ffffff" in physical_card.styleSheet()
        physical_card.view_timer.stop()
        physical_card.deleteLater()

        page = page_module.ControllersPage(None, vigem_available=False)
        page.apply_theme("light")
        assert "#eaf1fb" in page.cards_container.styleSheet()
        page.refresh_timer.stop()
        page.deleteLater()

        _flush_deferred_deletes(qapp)


def test_raw_hid_terminal_and_notifications_use_light_palette(qapp):
    terminal = RawHidTerminalDialog()
    terminal.apply_theme("light")
    assert "#f3f6fc" in terminal.styleSheet()
    assert "#ffffff" in terminal.styleSheet()
    terminal._metrics_timer.stop()
    terminal.deleteLater()

    parent = QWidget()
    toast = StatusToast(parent)
    toast.apply_theme("light")
    assert "#ffffff" in toast.styleSheet()
    assert "#263650" in toast.styleSheet()
    toast.deleteLater()
    parent.deleteLater()
    _flush_deferred_deletes(qapp)


def test_new_controller_mapping_starts_emulation_immediately(qapp):
    with patch.dict(sys.modules, _native_input_stubs()):
        module = importlib.import_module("ui.pages.controller_emulation")
        calls = []

        class _FakePage:
            def __init__(self):
                self.emu_list = QListWidget()

            def _on_emulate_requested(self, hid, emu, widget):
                calls.append((hid, emu, widget.is_running()))

            def _on_delete_requested(self, *_args):
                pass

            def _on_lightbar_requested(self, *_args):
                pass

        page = _FakePage()
        assert module.ControllerEmulation.add_emulated_mapping(
            page,
            "DualSense",
            "Emulate Xbox",
            {"path": "test-hid-path"},
        )
        item = page.emu_list.item(0)
        widget = page.emu_list.itemWidget(item)
        assert widget.is_running()
        assert widget.btn_emulate.text() == "Stop"
        assert calls == [("DualSense", "Emulate Xbox", True)]

        widget.btn_emulate.click()
        assert not widget.is_running()
        assert widget.btn_emulate.text() == "Emulate"
        assert calls[-1] == ("DualSense", "Emulate Xbox", False)
