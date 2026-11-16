"""Regression tests for safe modal accept/reject/close handling."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from ui.pages.modal.add_controller import AddControllerDialog
from ui.pages.controllers import X360TestCard
from ui.pages.modal.mobile_pairing import MobilePairingDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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


class _FakeXInputInstance:
    def __init__(self, device_path):
        self.device_path = device_path
        self.supports_rumble = True
        self._last_monitor = None

    def set_xinput_vibration(self, _left, _right):
        pass


def test_input_test_hides_battery_and_vibration_for_web_gamepad(qapp):
    web_card = X360TestCard(_FakeXInputInstance("web-session-123"), "Phone", True)
    assert web_card.battery_icon.width() == 22
    assert web_card.battery_info.isHidden()
    assert web_card.vibration_button.isHidden()
    web_card.view_timer.stop()
    web_card.deleteLater()

    physical_card = X360TestCard(
        _FakeXInputInstance("physical-controller"), "DualSense", True
    )
    assert physical_card.battery_icon.width() == 22
    assert not physical_card.battery_info.isHidden()
    assert not physical_card.vibration_button.isHidden()
    physical_card.view_timer.stop()
    physical_card.deleteLater()


def test_add_controller_cancel_during_entrance_returns_rejected(qapp):
    dialog = AddControllerDialog()
    button_box = dialog.findChild(QDialogButtonBox)
    cancel = button_box.button(QDialogButtonBox.StandardButton.Cancel)

    # Trigger while the entrance fade is still running.
    QTimer.singleShot(25, cancel.click)
    assert dialog.exec() == QDialog.DialogCode.Rejected
    assert not dialog.isVisible()
    dialog.deleteLater()


def test_add_controller_accept_during_entrance_returns_accepted(qapp):
    dialog = AddControllerDialog()
    dialog.hid_list.addItem("DualSense")
    dialog.emu_list.addItem("Emulate Xbox")
    dialog.hid_list.setCurrentRow(0)
    dialog.emu_list.setCurrentRow(0)

    QTimer.singleShot(25, dialog._accept_button.click)
    assert dialog.exec() == QDialog.DialogCode.Accepted
    assert not dialog.isVisible()
    dialog.deleteLater()


class _FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot):
        if slot not in self._slots:
            raise TypeError("slot is not connected")
        self._slots.remove(slot)


class _FakeWebServer:
    running = False


class _FakePairingService:
    def __init__(self):
        self.server_state_changed = _FakeSignal()
        self.mobile_session_added = _FakeSignal()
        self.web_server = _FakeWebServer()
        self.end_calls = 0

    def sessions_snapshot(self):
        return []

    def begin_mobile_pairing_flow(self):
        return False

    def end_mobile_pairing_flow(self):
        self.end_calls += 1


def test_remote_companion_cancel_cleans_up_and_returns_rejected(qapp):
    service = _FakePairingService()
    dialog = MobilePairingDialog(service)

    # Exercise the actual Cancel button during the entrance fade.
    QTimer.singleShot(25, dialog.cancel.click)
    assert dialog.exec() == QDialog.DialogCode.Rejected
    assert service.end_calls == 1
    assert not dialog.isVisible()
    dialog.deleteLater()



def test_add_controller_window_close_returns_rejected(qapp):
    dialog = AddControllerDialog()
    QTimer.singleShot(25, dialog.close)

    assert dialog.exec() == QDialog.DialogCode.Rejected
    assert not dialog.isVisible()
    dialog.deleteLater()


def test_remote_companion_window_close_cleans_up_once(qapp):
    service = _FakePairingService()
    dialog = MobilePairingDialog(service)

    QTimer.singleShot(25, dialog.close)
    assert dialog.exec() == QDialog.DialogCode.Rejected
    assert service.end_calls == 1
    assert not dialog.isVisible()
    dialog.deleteLater()
