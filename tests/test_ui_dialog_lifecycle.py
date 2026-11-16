"""Regression tests for safe modal accept/reject/close handling."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from ui.pages.modal.add_controller import AddControllerDialog
from ui.pages.modal.mobile_pairing import MobilePairingDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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
