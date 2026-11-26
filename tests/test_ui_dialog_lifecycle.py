"""Regression tests for safe modal accept/reject/close handling."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QTabBar, QWidget
)

from ui.pages.modal.add_controller import AddControllerDialog
from ui.pages.modal.mobile_pairing import MobilePairingDialog
from ui.notifications import StatusToast


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_status_toast_is_centered_at_top_below_navigation(qapp):
    parent = QWidget()
    parent.resize(1000, 700)

    navigation = QTabBar(parent)
    navigation.setObjectName("top_navigation")
    navigation.setGeometry(80, 84, 840, 40)

    toast = StatusToast(parent)
    toast._title.setText("Controller connected")
    toast._message.setText("The controller is ready.")

    toast.reposition()

    assert toast.x() == (parent.width() - toast.width()) // 2
    expected_top = navigation.mapTo(
        parent, navigation.rect().bottomLeft()
    ).y() + 16
    assert toast.y() == expected_top

    toast.deleteLater()
    parent.deleteLater()


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
