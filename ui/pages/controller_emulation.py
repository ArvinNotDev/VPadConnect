import logging
import threading
import time
from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget, QPushButton,
    QDialog, QListWidgetItem, QSizePolicy, QMessageBox, QFrame, QCheckBox,
    QColorDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QThread, QObject, QUrl
from PySide6.QtGui import QDesktopServices, QColor

from ui.pages.modal.add_controller import AddControllerDialog
from ui.pages.modal.mobile_pairing import MobilePairingDialog, MobileConnectedDialog
from core.mapper import Mapper
from core.settings import SettingsManager
from core.hid import HIDManager
from core import hid
from core.controller import stable_controller_id, is_preferred_sony_gamepad_interface
from core.dualsense_lightbar import (
    DEFAULT_LIGHTBAR_COLOR,
    DualSenseLightbar,
    is_dualsense_device,
    resolve_lightbar_color,
)
from ui.i18n import tr
from core.vigem import is_vigem_installed
from ui.vigem_gate import VigemGate

from core.hidhide import HIDHIDE_RELEASES_URL, HidHideError, HidHideManager

logger = logging.getLogger("vpadconnect.controller_emulation")


class HidHideWorker(QObject):
    finished = Signal(object)

    def __init__(self, manager: HidHideManager, action: str, devices: list[dict] | None = None):
        super().__init__()
        self.manager = manager
        self.action = action
        self.devices = devices or []

    def run(self):
        try:
            if self.action == "detect":
                result = ("detect", self.manager.detect())
            elif self.action == "states":
                result = ("states", self.manager.controller_states(self.devices))
            elif self.action == "hide":
                device = self.devices[0]
                target, added = self.manager.hide_hid_device(device)
                result = ("device", {
                    "operation": "hide",
                    "hid": device,
                    "target": target,
                    "added": added,
                    "hidden": True,
                })
            elif self.action == "unhide":
                device = self.devices[0]
                target, removed = self.manager.unhide_hid_device(device)
                result = ("device", {
                    "operation": "unhide",
                    "hid": device,
                    "target": target,
                    "removed": removed,
                    "hidden": False,
                })
            elif self.action == "unhide_all":
                removed = self.manager.unhide_all_hid_devices(self.devices)
                result = ("unhide_all", {"removed": removed})
            elif self.action == "cleanup":
                removed = self.manager.unhide_our_devices()
                result = ("cleanup", {"removed": removed})
            else:
                result = ("error", "Unknown HidHide operation.")
        except HidHideError as exc:
            result = ("error", str(exc))
        except Exception as exc:
            result = ("error", f"Unexpected HidHide error: {exc}")
        self.finished.emit(result)


class HidHideDeviceRow(QFrame):
    toggle_requested = Signal(object)

    def __init__(self, state: dict, parent=None):
        super().__init__(parent)
        self.state = state
        self.hid_device = state["hid"]
        self.hidden = bool(state.get("hidden", False))

        self.setObjectName("hidhideDeviceRow")
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(10)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)

        self.name = QLabel(str(state.get("label") or "Controller"))
        self.name.setObjectName("hidhideDeviceName")
        self.name.setWordWrap(True)
        text_box.addWidget(self.name)

        vendor = self.hid_device.get("manufacturer_string") or "Unknown"
        vid = self.hid_device.get("vendor_id")
        pid = self.hid_device.get("product_id")
        try:
            identity = f"{vendor} • VID {int(vid):04X} / PID {int(pid):04X}"
        except (TypeError, ValueError):
            identity = str(vendor)
        self.meta = QLabel(identity)
        self.meta.setObjectName("hidhideDeviceMeta")
        text_box.addWidget(self.meta)
        root.addLayout(text_box, 1)

        self.state_label = QLabel()
        self.state_label.setObjectName("hidhideDeviceState")
        root.addWidget(self.state_label)

        self.button = QPushButton()
        self.button.setObjectName("hidhideDeviceButton")
        self.button.setMinimumHeight(32)
        self.button.clicked.connect(self._request_toggle)
        root.addWidget(self.button)

        self.set_state(self.hidden)

    def set_state(self, hidden: bool):
        self.hidden = bool(hidden)
        if self.hidden:
            self.state_label.setText("Hidden")
            self.state_label.setProperty("state", "hidden")
            self.button.setText("Unhide")
            self.button.setToolTip("Remove this controller from the HidHide blacklist")
        else:
            self.state_label.setText("Visible")
            self.state_label.setProperty("state", "visible")
            self.button.setText("Hide")
            self.button.setToolTip("Hide this controller from other applications")
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)

    def set_busy(self, busy: bool):
        self.button.setEnabled(not busy)

    def _request_toggle(self):
        self.set_busy(True)
        self.toggle_requested.emit(self.hid_device)


class HidHideCard(QFrame):
    """Professional HidHide control with per-controller hide/unhide state."""

    def __init__(self, parent: "ControllerEmulation"):
        super().__init__(parent)
        self.page = parent
        self.manager = HidHideManager()
        self._thread: QThread | None = None
        self._worker: HidHideWorker | None = None
        self._loader_timer = QTimer(self)
        self._loader_timer.setInterval(180)
        self._loader_timer.timeout.connect(self._animate_loader)
        self._loader_index = 0
        self._busy = False
        self._rows: dict[str, HidHideDeviceRow] = {}
        self._states: list[dict] = []

        self.setObjectName("hidhideCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(156)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("HidHide")
        title.setObjectName("hidhideTitle")
        header.addWidget(title)

        self.status = QLabel("Click HidHide to detect the driver.")
        self.status.setObjectName("hidhideStatus")
        self.status.setWordWrap(True)
        header.addWidget(self.status, 1)
        root.addLayout(header)

        self.detail = QLabel(
            "Hide each physical controller independently. VPadConnect stays whitelisted so it can continue reading hidden controllers."
        )
        self.detail.setObjectName("hidhideDetail")
        self.detail.setWordWrap(True)
        root.addWidget(self.detail)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.detect_button = QPushButton("HidHide")
        self.detect_button.setObjectName("hidhidePrimary")
        self.detect_button.setMinimumHeight(36)
        self.detect_button.clicked.connect(self.start_detection)
        actions.addWidget(self.detect_button)

        self.unhide_all_button = QPushButton("Unhide All")
        self.unhide_all_button.setObjectName("hidhideSecondary")
        self.unhide_all_button.setMinimumHeight(36)
        self.unhide_all_button.setVisible(False)
        self.unhide_all_button.clicked.connect(self._unhide_all)
        actions.addWidget(self.unhide_all_button)

        self.open_link_button = QPushButton("Open Link")
        self.open_link_button.setObjectName("hidhideSecondary")
        self.open_link_button.setMinimumHeight(36)
        self.open_link_button.setVisible(False)
        self.open_link_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(HIDHIDE_RELEASES_URL))
        )
        actions.addWidget(self.open_link_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.devices_container = QWidget(self)
        self.devices_layout = QVBoxLayout(self.devices_container)
        self.devices_layout.setContentsMargins(0, 2, 0, 0)
        self.devices_layout.setSpacing(6)
        root.addWidget(self.devices_container)

        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(
            """
            QFrame#hidhideCard {
                background: rgba(255, 255, 255, 12%);
                border: 1px solid rgba(255, 255, 255, 20%);
                border-radius: 12px;
            }
            QLabel#hidhideTitle {
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#hidhideStatus {
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#hidhideDetail {
                font-size: 11px;
            }
            QFrame#hidhideDeviceRow {
                background: rgba(255, 255, 255, 7%);
                border: 1px solid rgba(255, 255, 255, 12%);
                border-radius: 9px;
            }
            QLabel#hidhideDeviceName {
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#hidhideDeviceMeta {
                font-size: 10px;
                color: rgba(255, 255, 255, 62%);
            }
            QLabel#hidhideDeviceState {
                font-size: 10px;
                font-weight: 700;
                padding: 4px 7px;
                border-radius: 7px;
            }
            QLabel#hidhideDeviceState[state="hidden"] {
                color: #a7f3d0;
                background: rgba(16, 185, 129, 18%);
            }
            QLabel#hidhideDeviceState[state="visible"] {
                color: #cbd5e1;
                background: rgba(148, 163, 184, 16%);
            }
            QPushButton#hidhidePrimary {
                background: #5390ff;
                color: white;
                border: 0;
                border-radius: 8px;
                padding: 7px 18px;
                font-weight: 700;
            }
            QPushButton#hidhidePrimary:hover { background: #6aa0ff; }
            QPushButton#hidhidePrimary:pressed { background: #3d7ce6; }
            QPushButton#hidhidePrimary:disabled {
                background: #666a73;
                color: #d5d7dc;
            }
            QPushButton#hidhideSecondary, QPushButton#hidhideDeviceButton {
                background: transparent;
                color: #85c1ff;
                border: 1px solid rgba(133, 193, 255, 55%);
                border-radius: 8px;
                padding: 7px 14px;
                font-weight: 600;
            }
            QPushButton#hidhideSecondary:hover, QPushButton#hidhideDeviceButton:hover {
                background: rgba(133, 193, 255, 10%);
            }
            QPushButton#hidhideSecondary:disabled, QPushButton#hidhideDeviceButton:disabled {
                color: #777b84;
                border-color: rgba(255, 255, 255, 12%);
            }
            """
        )

    def _set_status(self, text: str):
        self.status.setText(text)

    def _animate_loader(self):
        spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        glyph = spinner[self._loader_index % len(spinner)]
        self.detect_button.setText(f"Detecting HidHide {glyph}")
        self._loader_index += 1

    def _clear_rows(self):
        self._rows.clear()
        while self.devices_layout.count():
            item = self.devices_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _device_key(device: dict) -> str:
        path = device.get("path")
        if isinstance(path, bytes):
            path = path.decode("utf-8", errors="ignore")
        return str(path or id(device)).strip().lower()

    def _populate_devices(self, states: list[dict]):
        self._clear_rows()
        self._states = states

        for state in states:
            key = self._device_key(state["hid"])
            row = HidHideDeviceRow(state, self)
            row.toggle_requested.connect(self._toggle_device)
            self.devices_layout.addWidget(row)
            self._rows[key] = row

        self.unhide_all_button.setVisible(bool(states))
        if states:
            hidden = sum(bool(state.get("hidden")) for state in states)
            self._set_status(
                f"HidHide ready • {len(states)} controller(s) detected • {hidden} hidden."
            )
            self.detail.setText(
                "Use each controller's button to hide or unhide it independently. Unhide All only removes HidHide rules for the currently connected controllers."
            )
        else:
            self._set_status("HidHide detected, but no supported controller is connected.")
            self.detail.setText(
                "Connect a DualShock 4, DualSense, or UnoJoy controller and click HidHide again."
            )

    def _start_worker(self, action: str, devices: list[dict] | None = None):
        if self._busy:
            return
        self._busy = True
        self.open_link_button.setVisible(False)
        self.detect_button.setEnabled(False)
        self.unhide_all_button.setEnabled(False)
        self._loader_index = 0
        self._loader_timer.start()

        self._thread = QThread(self)
        self._worker = HidHideWorker(self.manager, action, devices or [])
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        thread = self._thread
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(lambda t=thread: self._clear_thread_refs(t))
        self._thread.start()

    def _clear_thread_refs(self, thread):
        if self._thread is thread:
            self._worker = None
            self._thread = None

    def _finish_busy(self):
        self._busy = False
        self._loader_timer.stop()
        self.detect_button.setEnabled(True)
        self.unhide_all_button.setEnabled(bool(self._states))
        for row in self._rows.values():
            row.set_busy(False)

    def _toggle_device(self, device: dict):
        if self._busy:
            return
        key = self._device_key(device)
        row = self._rows.get(key)
        if row:
            row.set_busy(True)
        action = "unhide" if row and row.hidden else "hide"
        self._start_worker(action, [device])

    def _unhide_all(self):
        if self._busy:
            return
        devices = self.page._get_hidhide_devices()
        if not devices:
            self._refresh_states()
            return
        self._start_worker("unhide_all", devices)

    def _refresh_states(self):
        devices = self.page._get_hidhide_devices()
        if not devices:
            self._clear_rows()
            self._states = []
            self.unhide_all_button.setVisible(False)
            self._set_status("HidHide detected, but no supported controller is connected.")
            self.detail.setText(
                "Connect a DualShock 4, DualSense, or UnoJoy controller and click HidHide again."
            )
            return
        self._start_worker("states", devices)

    def _on_worker_finished(self, result):
        self._finish_busy()
        action, payload = result

        if action == "detect":
            detection = payload
            if not detection.installed:
                self._clear_rows()
                self.unhide_all_button.setVisible(False)
                self._set_status("HidHide not found on this PC.")
                self.detail.setText(
                    "Install HidHide from the official Nefarius releases. After installation, click HidHide again to detect it."
                )
                self.open_link_button.setVisible(True)
                self.detect_button.setText("HidHide")
                return

            self.open_link_button.setVisible(False)
            if detection.message and detection.message != "HidHide detected.":
                self._set_status("HidHide detected, but the configuration interface is unavailable.")
                self.detail.setText(detection.message)
                self.detect_button.setText("HidHide")
                return

            version = f" • {detection.version}" if detection.version else ""
            self._set_status(f"HidHide detected{version} • reading connected controllers…")
            self.detail.setText(
                "Reading the current HidHide blacklist and resolving each connected controller."
            )
            self._refresh_states()
            return

        if action == "states":
            states = payload if isinstance(payload, list) else []
            self._populate_devices(states)
            self.detect_button.setText("Refresh HidHide")
            return

        if action == "device":
            if not isinstance(payload, dict):
                self._set_status("HidHide operation completed, but the device state could not be refreshed.")
                return
            operation = payload.get("operation")
            target = payload.get("target") or {}
            label = str(target.get("friendlyName") or target.get("product") or "Controller")
            if operation == "hide":
                self._set_status(f"Hidden • {label}")
                self.detail.setText(
                    "This controller is now hidden from non-whitelisted applications. VPadConnect remains allowed to access it."
                )
            else:
                self._set_status(f"Visible • {label}")
                self.detail.setText(
                    "This controller has been removed from the HidHide blacklist."
                )
            self._refresh_states()
            return

        if action == "unhide_all":
            removed = payload.get("removed", []) if isinstance(payload, dict) else []
            self._set_status(f"Unhidden {len(removed)} controller rule(s).")
            self.detail.setText(
                "HidHide rules for the currently connected supported controllers were removed."
            )
            self._refresh_states()
            return

        if action == "cleanup":
            return

        if action == "error":
            self._set_status("HidHide configuration failed.")
            self.detail.setText(str(payload))
            self.detect_button.setText("HidHide")

    def start_detection(self):
        if self._busy:
            return
        self._set_status("Detecting HidHide…")
        self.detail.setText(
            "Checking the official HidHide installation and configuration interface."
        )
        self._start_worker("detect")

    def shutdown(self):
        """Remove only the device rules created by this VPadConnect session."""
        self._loader_timer.stop()
        try:
            self.manager.unhide_our_devices()
        except HidHideError as exc:
            logger.exception("HidHide cleanup failed")
        except Exception as exc:
            logger.exception("Unexpected HidHide cleanup error")


class DualSenseLightbarDialog(QDialog):
    """Compact per-controller Lightbar settings using the app's active theme."""

    def __init__(self, controller_name: str, settings: dict, language="eng", parent=None):
        super().__init__(parent)
        self._language = language
        self._color = settings.get("color", DEFAULT_LIGHTBAR_COLOR)
        self.setWindowTitle(tr("Lightbar settings", language))
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        identity = QLabel(f"{tr('Controller', language)}: {controller_name}")
        identity.setWordWrap(True)
        identity.setProperty("_i18n_dynamic", True)
        root.addWidget(identity)

        self.enabled = QCheckBox(tr("Lightbar On", language))
        self.enabled.setChecked(bool(settings.get("enabled", False)))
        root.addWidget(self.enabled)

        color_row = QHBoxLayout()
        self.choose_color = QPushButton(tr("Choose color…", language))
        self.choose_color.clicked.connect(self._choose_color)
        color_row.addWidget(self.choose_color)
        self.preview = QFrame()
        self.preview.setObjectName("lightbar_preview")
        self.preview.setFixedSize(48, 26)
        color_row.addWidget(self.preview)
        color_row.addWidget(QLabel(tr("HEX", language)))
        self.hex_value = QLabel()
        self.hex_value.setMinimumWidth(82)
        self.hex_value.setProperty("_i18n_dynamic", True)
        color_row.addWidget(self.hex_value)
        color_row.addStretch(1)
        root.addLayout(color_row)

        self.battery_mode = QCheckBox(tr("Battery Lightbar", language))
        self.battery_mode.setChecked(bool(settings.get("battery_mode", False)))
        root.addWidget(self.battery_mode)

        self.charging_indication = QCheckBox(
            tr("Charging indication", language)
        )
        self.charging_indication.setChecked(
            bool(settings.get("charging_indication", False))
        )
        root.addWidget(self.charging_indication)

        self.enabled.toggled.connect(self._update_dependent_controls)
        self._update_dependent_controls(self.enabled.isChecked())
        self._update_color_preview()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            orientation=Qt.Horizontal,
        )
        buttons.button(QDialogButtonBox.Save).setText(tr("Save", language))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Cancel", language))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _choose_color(self):
        chosen = QColorDialog.getColor(QColor(self._color), self)
        if chosen.isValid():
            self._color = chosen.name().upper()
            self._update_color_preview()

    def _update_color_preview(self):
        self.preview.setStyleSheet(
            f"background-color: {self._color};"
        )
        self.hex_value.setText(self._color.upper())

    def _update_dependent_controls(self, enabled: bool):
        self.battery_mode.setEnabled(enabled)
        self.charging_indication.setEnabled(enabled)

    def get_settings(self) -> dict:
        return {
            "enabled": self.enabled.isChecked(),
            "color": self._color.upper(),
            "battery_mode": self.battery_mode.isChecked(),
            "charging_indication": self.charging_indication.isChecked(),
        }


class EmuListItemWidget(QWidget):
    emulate_requested = Signal(str, str, object)
    delete_requested = Signal(object)
    lightbar_requested = Signal(object)

    def __init__(self, hid: str, emu: str, device=None, parent=None):
        super().__init__(parent)
        self.hid = hid
        self.emu = emu
        self._running = False
        self._battery = None
        self.device = device

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.lbl_text = QLabel(f"{hid} → {emu}")
        self.lbl_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.lbl_text)

        self.lbl_battery = QLabel("Battery: --")
        self.lbl_battery.setMinimumWidth(115)
        self.lbl_battery.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_battery)

        self.btn_lightbar = QPushButton("Lightbar")
        self.btn_lightbar.setToolTip("Configure this controller's Lightbar")
        self.btn_lightbar.clicked.connect(lambda: self.lightbar_requested.emit(self))
        layout.addWidget(self.btn_lightbar)
        self.set_device(device)

        self.btn_emulate = QPushButton("Emulate")
        self.btn_emulate.setToolTip("Start/stop emulation for this mapping")
        self.btn_emulate.clicked.connect(self._on_emulate_clicked)
        layout.addWidget(self.btn_emulate)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setToolTip("Remove this mapping")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        layout.addWidget(self.btn_delete)

        self.status = QLabel()
        self.status.setFixedSize(12, 12)
        self.status.setToolTip("Running status")
        self._update_status_style(False)
        layout.addWidget(self.status, alignment=Qt.AlignRight)

    def _update_status_style(self, running: bool):
        if running:
            color = "#2ecc71"
        else:
            color = "#9aa0a6"
        self.status.setStyleSheet(
            f"border-radius: 6px; background-color: {color};"
        )

    def set_running(self, running: bool):
        self._running = bool(running)
        self._update_status_style(self._running)
        self.btn_emulate.setText("Stop" if self._running else "Emulate")

    def set_device(self, device):
        self.device = device
        supported = bool(
            device
            and is_dualsense_device(device.get("vendor_id"), device.get("product_id"))
        )
        self.btn_lightbar.setVisible(supported)

    def set_battery(self, percent: int | None, charging: bool = False):
        if percent is None:
            self._battery = None
            self.lbl_battery.setText("Battery: --")
            return
        self._battery = (int(percent), bool(charging))
        suffix = " ⚡" if charging else ""
        self.lbl_battery.setText(f"Battery: {int(percent)}%{suffix}")

    def set_connection_state(self, connected: bool):
        if connected:
            self._update_status_style(self._running)
            return
        self.status.setStyleSheet(
            "border-radius: 6px; background-color: #f59e0b;"
        )
        self.lbl_battery.setText("Waiting for reconnect…")

    def is_running(self) -> bool:
        return self._running

    def _on_emulate_clicked(self):
        self.set_running(not self._running)
        self.emulate_requested.emit(self.hid, self.emu, self)

    def _on_delete_clicked(self):
        self.delete_requested.emit(self)


class RemoteDeviceRow(QWidget):
    """Controller-list row for one independently managed browser session."""

    disconnect_requested = Signal(str)

    def __init__(self, session: dict, parent=None):
        super().__init__(parent)
        self.session_id = str(session.get("session_id") or "")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        identity = QVBoxLayout()
        identity.setSpacing(2)
        self.name_label = QLabel(f"📱  {session.get('name') or 'Mobile Device'}")
        self.name_label.setStyleSheet("font-weight:750; color:#eaf1ff;")
        identity.addWidget(self.name_label)

        capabilities = session.get("capabilities") or ["Touch mouse", "Keyboard / PC Remote"]
        self.capabilities_label = QLabel(" · ".join(str(item) for item in capabilities))
        self.capabilities_label.setStyleSheet("font-size:10px; color:#91a2bc;")
        self.capabilities_label.setWordWrap(True)
        identity.addWidget(self.capabilities_label)
        layout.addLayout(identity, 1)

        self.state_label = QLabel("●  Connected")
        self.state_label.setStyleSheet(
            "color:#39d98a; font-size:11px; font-weight:800; padding:4px 8px; "
            "background:rgba(39,190,125,24%); border-radius:8px;"
        )
        layout.addWidget(self.state_label)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setToolTip("Disconnect this phone and remove its virtual controller")
        self.delete_button.clicked.connect(
            lambda: self.disconnect_requested.emit(self.session_id)
        )
        layout.addWidget(self.delete_button)

        self.setStyleSheet(
            "QWidget { background:#172338; border:1px solid #30435f; border-radius:10px; }"
        )

    def set_busy(self, busy: bool) -> None:
        self.delete_button.setEnabled(not bool(busy))
        self.delete_button.setText("Disconnecting…" if busy else "Delete")


class ControllerEmulation(QWidget):
    vigem_recheck_requested = Signal()
    raw_hid_report = Signal(str, bytes)

    def __init__(
        self, settings, controllers_page, hotkey_page, *,
        vigem_available: bool | None = None,
    ):
        super().__init__()
        self._raw_hid_report_lock = threading.Lock()
        self._last_raw_hid_emit_at = 0.0
        self._raw_hid_monitor_active = False
        layout_dashboard = QVBoxLayout(self)
        self.controllers_page = controllers_page
        hid.hid_manager = HIDManager(settings.get_poll_interval_ms() / 1000.0)
        self.hotkey_page = hotkey_page
        self.mappers: dict = {}
        self._mapping_records: dict[int, dict] = {}
        self._path_records: dict[object, int] = {}
        self._lightbar_outputs: dict[object, DualSenseLightbar] = {}
        self._remote_device_items: dict[str, QListWidgetItem] = {}
        self._remote_device_widgets: dict[str, RemoteDeviceRow] = {}
        self.web_remote_service = None
        self.settings = settings
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(1000)
        self._reconnect_timer.timeout.connect(self._try_reconnect)
        self._reconnect_timer_active = False
        self.controllers_page.battery_updated.connect(self._on_battery_updated)
        hid.hid_manager.device_error.connect(self._on_device_error)
        gamepad_content = QWidget(self)
        gamepad_layout = QVBoxLayout(gamepad_content)
        gamepad_layout.setContentsMargins(0, 0, 0, 0)
        gamepad_layout.setSpacing(8)

        lbl_dashboard = QLabel("Controller Emulation Page\nPress {Share/Select/⚙️ + R3} to switch between mouse mode and controller mode")
        lbl_dashboard.setAlignment(Qt.AlignCenter)

        emu_label = QLabel("List of Emulated Devices")
        emu_label.setAlignment(Qt.AlignCenter)

        self.emu_list = QListWidget()
        self.emu_list.setStyleSheet("""
            QListWidget::item {
                padding: 0px;
                color: #000000;
                background-color: transparent;
        }
                                    """)

        self.hidhide_card = HidHideCard(self)

        add_btn = QPushButton("Add Controller")
        add_btn.clicked.connect(self.open_add_controller_dialog)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #5390ff;
                color: #000000;
                border: 2px solid #000000;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #f0f0f0;  /* same as normal to remove hover effect */
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        """)


        gamepad_layout.addWidget(lbl_dashboard)
        gamepad_layout.addWidget(emu_label)
        gamepad_layout.addWidget(self.emu_list)

        controller_actions = QHBoxLayout()
        controller_actions.setSpacing(8)
        controller_actions.addWidget(add_btn, 1)
        self.remote_permissions_button = QPushButton("Remote Permissions")
        self.remote_permissions_button.setToolTip(
            "Manage which Windows actions connected phones are allowed to perform."
        )
        self.remote_permissions_button.setEnabled(False)
        self.remote_permissions_button.clicked.connect(self._open_remote_permissions)
        controller_actions.addWidget(self.remote_permissions_button)
        gamepad_layout.addLayout(controller_actions)

        self.vigem_gate = VigemGate(gamepad_content)
        self.vigem_gate.recheck_requested.connect(self.vigem_recheck_requested.emit)
        self.vigem_gate.set_vigem_available(
            is_vigem_installed() if vigem_available is None else vigem_available
        )
        layout_dashboard.addWidget(self.vigem_gate, 1)
        # HidHide is an independent optional feature and stays usable without XInput.
        layout_dashboard.addWidget(self.hidhide_card)

    def set_vigem_available(self, available: bool) -> None:
        self.vigem_gate.set_vigem_available(available)

    def _get_hidhide_devices(self) -> list[dict]:
        """Return supported connected HID devices for HidHide integration."""
        devices = hid.hid_manager.scan_devices() or []
        supported = []
        seen_paths = set()

        for device in devices:
            vid = self._device_id(device.get("vendor_id"))
            pid = self._device_id(device.get("product_id"))
            is_supported = (
                (vid == 0x054C and pid in (0x05C4, 0x09CC, 0x0CE6, 0x0DF2))
                or (vid == 0x10C4 and pid == 0x82C0)
            )
            if not is_supported:
                continue
            path = str(device.get("path") or "")
            if path and path not in seen_paths:
                seen_paths.add(path)
                supported.append(device)

        return supported

    def open_add_controller_dialog(self):
        dialog = AddControllerDialog(self)

        hid_list_display = []
        hid_path_list = []

        devices = hid.hid_manager.scan_devices() or []

        name_counts = {}
        for dev in devices:
            if not is_preferred_sony_gamepad_interface(dev):
                logger.debug(
                    "Skipping non-gamepad Sony USB HID collection: "
                    "usage_page=%s usage=%s interface=%s",
                    dev.get("usage_page"),
                    dev.get("usage"),
                    dev.get("interface_number"),
                )
                continue

            vid = dev.get("vendor_id")
            pid = dev.get("product_id")

            try:
                vid_int = int(vid) if isinstance(vid, (int,)) else int(str(vid), 0)
            except Exception:
                try:
                    vid_int = int(vid)
                except Exception:
                    vid_int = None
            try:
                pid_int = int(pid) if isinstance(pid, (int,)) else int(str(pid), 0)
            except Exception:
                try:
                    pid_int = int(pid)
                except Exception:
                    pid_int = None

            if vid_int == 0x054C and pid_int in (0x05C4, 0x09CC):
                name = "Dualshock4 (PS4 Controller)"
            elif vid_int == 0x054C and pid_int == 0x0CE6:
                name = "Dualsense (PS5 Controller)"
            elif vid_int == 0x054C and pid_int == 0x0DF2:
                name = "DualSense Edge (PS5 Controller)"
            elif vid_int == 0x10C4 and pid_int == 0x82C0:
                name = "UnoJoy Controller (Arduino)"
            else:
                name = "Not Supported"
            
            # --- Skip unsupported devices entirely ---
            if name == "Not Supported":
                continue
            
            count = name_counts.get(name, 0)
            name_counts[name] = count + 1
            display = name if count == 0 else f"{name} ({count})"
            
            hid_list_display.append(display)
            hid_path_list.append(dev)

        hid_list_display.reverse()
        hid_path_list.reverse()
        dialog.hid_list.addItems(hid_list_display)
        dialog.emu_list.addItems(["Emulate Xbox"])
        dialog.add_mobile_device_option()

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if dialog.is_mobile_selected():
            self._start_mobile_pairing()
            return

        hid_choice, emu_choice = dialog.get_selections()
        if not (hid_choice and emu_choice):
            return

        selected_index = dialog.hid_list.currentRow()
        if selected_index is None or selected_index < 0:
            try:
                selected_index = hid_list_display.index(hid_choice)
            except ValueError:
                selected_index = -1

        device = None
        if 0 <= selected_index < len(hid_path_list):
            device = hid_path_list[selected_index]

        added = self.add_emulated_mapping(hid_choice, emu_choice, device)
        if not added:
            return

        if not device:
            logger.warning("Selected HID could not be mapped to a device entry")

    def set_web_remote_service(self, service) -> None:
        """Attach the embedded Web Companion service to the unified device list."""
        if self.web_remote_service is service:
            return
        if self.web_remote_service is not None:
            try:
                self.web_remote_service.mobile_session_added.disconnect(self._add_remote_device_row)
                self.web_remote_service.mobile_session_removed.disconnect(self._remove_remote_device_row)
            except (RuntimeError, TypeError):
                pass
        self.web_remote_service = service
        self.remote_permissions_button.setEnabled(service is not None)
        if service is None:
            return
        service.mobile_session_added.connect(self._add_remote_device_row)
        service.mobile_session_removed.connect(self._remove_remote_device_row)
        for session in service.sessions_snapshot():
            self._add_remote_device_row(session)

    def _open_remote_permissions(self) -> None:
        if self.web_remote_service is not None:
            self.web_remote_service.open_permissions_dialog()

    def _start_mobile_pairing(self) -> None:
        if self.web_remote_service is None:
            QMessageBox.warning(
                self, "Mobile connection unavailable",
                "The integrated Web Companion service is not available.",
            )
            return

        dialog = MobilePairingDialog(self.web_remote_service, self)
        result = dialog.exec()
        session = dialog.connected_session
        if result == QDialog.DialogCode.Accepted and session:
            self._add_remote_device_row(session)
            MobileConnectedDialog(
                str(session.get("name") or "Mobile Device"), self
            ).exec()

    def _add_remote_device_row(self, session: dict) -> None:
        session_id = str(session.get("session_id") or "")
        if not session_id or session_id in self._remote_device_items:
            return

        item = QListWidgetItem()
        widget = RemoteDeviceRow(session, self.emu_list)
        widget.disconnect_requested.connect(self._disconnect_remote_device)
        item.setSizeHint(widget.sizeHint())
        item.setData(
            Qt.ItemDataRole.UserRole,
            {"source": "remote", "session_id": session_id},
        )
        self.emu_list.addItem(item)
        self.emu_list.setItemWidget(item, widget)
        self._remote_device_items[session_id] = item
        self._remote_device_widgets[session_id] = widget

    def _remove_remote_device_row(self, session_id: str) -> None:
        session_id = str(session_id)
        item = self._remote_device_items.pop(session_id, None)
        self._remote_device_widgets.pop(session_id, None)
        if item is None:
            return
        for index in range(self.emu_list.count()):
            if self.emu_list.item(index) is item:
                self.emu_list.takeItem(index)
                break

    def _disconnect_remote_device(self, session_id: str) -> None:
        widget = self._remote_device_widgets.get(session_id)
        if widget is not None:
            widget.set_busy(True)
        if self.web_remote_service is None:
            self._remove_remote_device_row(session_id)
            return
        self.web_remote_service.disconnect_mobile_session(session_id)

    def add_emulated_mapping(self, hid_choice: str, emu: str, device: Optional[dict] = None) -> bool:
        new_path = device.get("path") if device else None

        for i in range(self.emu_list.count()):
            existing_item = self.emu_list.item(i)
            existing_data: Tuple[Optional[dict], Optional[str], Optional[str]] = existing_item.data(Qt.UserRole) or (None, None, None)
            existing_device = existing_data[0]
            existing_display = existing_data[1]

            if new_path and existing_device and existing_device.get("path") == new_path:
                self.emu_list.setCurrentItem(existing_item)
                existing_widget = self.emu_list.itemWidget(existing_item)
                if existing_widget:
                    existing_widget.setFocus()
                QMessageBox.information(self, "Already added",
                                        f"Device '{hid_choice}' is already in the emulated devices list.")
                return False

            if not new_path and existing_display == hid_choice:
                self.emu_list.setCurrentItem(existing_item)
                QMessageBox.information(self, "Already added",
                                        f"HID '{hid_choice}' is already in the emulated devices list.")
                return False

        item = QListWidgetItem()
        widget = EmuListItemWidget(hid_choice, emu, device=device)

        item.setSizeHint(widget.sizeHint())
        item.setData(Qt.UserRole, (device, hid_choice, emu))

        self.emu_list.addItem(item)
        self.emu_list.setItemWidget(item, widget)

        widget.emulate_requested.connect(self._on_emulate_requested)
        widget.delete_requested.connect(lambda w=widget, i=item: self._on_delete_requested(w, i))
        widget.lightbar_requested.connect(self._on_lightbar_requested)

        return True

    def _find_item_by_widget(self, widget: EmuListItemWidget) -> Optional[QListWidgetItem]:
        for i in range(self.emu_list.count()):
            it = self.emu_list.item(i)
            if self.emu_list.itemWidget(it) is widget:
                return it
        return None

    def _find_device_by_display_name(self, display_name: str) -> Optional[dict]:
        devices = getattr(hid.hid_manager, "devices", None) or hid.hid_manager.scan_devices() or []
        base_name = display_name.split(" (")[0]
        for dev in devices:
            if not is_preferred_sony_gamepad_interface(dev):
                continue
            name = dev.get("product_string") or f"VID_{dev.get('vendor_id')}_PID_{dev.get('product_id')}"
            if base_name == name:
                return dev
        return None

    @staticmethod
    def _device_id(value) -> Optional[int]:
        try:
            return int(value) if isinstance(value, int) else int(str(value), 0)
        except (TypeError, ValueError):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

    def _controller_type(self, device: dict) -> str:
        vid = self._device_id(device.get("vendor_id"))
        pid = self._device_id(device.get("product_id"))
        if vid == 0x054C and pid in (0x05C4, 0x09CC):
            return "Dualshock4"
        if vid == 0x054C and pid in (0x0CE6, 0x0DF2):
            return "Dualsense"
        if vid == 0x10C4 and pid == 0x82C0:
            return "Unojoy"
        return "Generic"

    def _auto_reconnect_enabled(self) -> bool:
        try:
            return bool(self.settings.get_auto_reconnect())
        except Exception:
            return True

    def _lightbar_settings_for_device(self, device: dict) -> tuple[str, dict]:
        stable_id = stable_controller_id(
            device.get("vendor_id"),
            device.get("product_id"),
            device.get("path"),
            device.get("serial_number"),
        )
        return stable_id, self.settings.get_controller_lightbar_settings(stable_id)

    def _get_lightbar_output(self, device: dict, stable_id=None):
        if not is_dualsense_device(
            device.get("vendor_id"), device.get("product_id")
        ):
            return None
        path = device.get("path")
        if not path:
            return None
        current = self._lightbar_outputs.get(path)
        if current is not None:
            return current

        if stable_id is None:
            stable_id, _ = self._lightbar_settings_for_device(device)
        if not self.settings.has_controller_lightbar_settings(stable_id):
            return None

        output = DualSenseLightbar(
            path,
            transport=device.get("transport") or device.get("bus_type"),
            controller_key=stable_id,
            device_info=device,
            debug=self.settings.get_developer_debug(),
        )
        self._lightbar_outputs[path] = output
        return output

    def _on_lightbar_requested(self, widget: EmuListItemWidget) -> None:
        item = self._find_item_by_widget(widget)
        stored = item.data(Qt.UserRole) if item is not None else None
        device = (stored or (None,))[0]
        if not device:
            key = id(item) if item is not None else None
            record = self._mapping_records.get(key)
            device = (record or {}).get("last_device")
        if not device:
            return

        stable_id, current = self._lightbar_settings_for_device(device)
        dialog = DualSenseLightbarDialog(
            widget.hid,
            current,
            language=self.settings.get_ui_language(),
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        updated = dialog.get_settings()
        self.settings.set_controller_lightbar_settings(stable_id, updated)
        self.settings.save()
        output = self._get_lightbar_output(device, stable_id)
        if output is None:
            return

        path = device.get("path")
        mapper = self.mappers.get(path)
        if mapper is not None:
            mapper.configure_lightbar(updated)
        else:
            battery_state = getattr(self.controllers_page, "battery_states", {}).get(path)
            color, enabled = resolve_lightbar_color(updated, battery_state)
            output.set_color(color, enabled=enabled)

    @Slot(bool)
    def set_raw_hid_monitor_active(self, active: bool) -> None:
        """Enable report delivery only while the live terminal is visible."""
        with self._raw_hid_report_lock:
            self._raw_hid_monitor_active = bool(active)
            if not active:
                self._last_raw_hid_emit_at = 0.0

    def _publish_raw_hid_report(self, controller_name: str, report: bytes) -> None:
        """Rate-limit cross-thread GUI updates to 30 reports per second globally."""
        now = time.monotonic()
        with self._raw_hid_report_lock:
            if not self._raw_hid_monitor_active:
                return
            if now - self._last_raw_hid_emit_at < (1.0 / 30.0):
                return
            self._last_raw_hid_emit_at = now
        # Emitting a Qt signal is thread-safe. Connected widgets receive the
        # queued signal on their own thread; this method never touches widgets.
        self.raw_hid_report.emit(str(controller_name), bytes(report))

    def _start_mapping(
        self,
        item: QListWidgetItem,
        widget: EmuListItemWidget,
        device: dict,
        record: Optional[dict] = None,
    ) -> bool:
        path = device.get("path")
        if not path or path in self.mappers:
            return False

        try:
            controller = hid.hid_manager.start_polling(
                device.get("vendor_id"),
                device.get("product_id"),
                path,
                transport=device.get("transport") or device.get("bus_type"),
                serial_number=device.get("serial_number"),
            )
            stable_id, _ = self._lightbar_settings_for_device(device)
            lightbar_output = self._get_lightbar_output(device, stable_id)
            mapper = Mapper(
                controller,
                self._controller_type(device),
                "x360",
                self.settings,
                self.controllers_page,
                self.hotkey_page,
                lightbar_output=lightbar_output,
                raw_hid_report_callback=self._publish_raw_hid_report,
            )
        except Exception as exc:
            logger.exception("Failed to start controller mapping")
            try:
                hid.hid_manager.stop_polling(path)
            except Exception:
                pass
            return False

        key = id(item)
        record = record or {
            "item": item,
            "widget": widget,
            "hid_choice": item.data(Qt.UserRole)[1],
            "emu": item.data(Qt.UserRole)[2],
            "last_device": device,
            "path": path,
            "waiting": False,
        }
        record["last_device"] = device
        record["path"] = path
        record["waiting"] = False
        self._mapping_records[key] = record
        self._path_records[path] = key
        self.mappers[path] = mapper
        item.setData(
            Qt.UserRole,
            (device, record["hid_choice"], record["emu"]),
        )
        widget.set_device(device)

        wtuple = getattr(hid.hid_manager, "_workers", {}).get(path)
        if wtuple:
            _, worker, _ = wtuple
            try:
                worker.data_received.connect(mapper.handle_hid_data)
                if mapper.gyro_steering is not None:
                    worker.sensor_calibration.connect(mapper.set_gyro_factory_calibration)
                    calibration = getattr(controller, "sensor_calibration", None)
                    if calibration:
                        mapper.set_gyro_factory_calibration(calibration)
            except RuntimeError:
                logger.warning("HID worker for %s was deleted before connecting signals", path)

        mapper.start()
        widget.set_connection_state(True)
        widget.set_battery(None)
        return True

    def _stop_mapping(self, path: str) -> None:
        mapper = self.mappers.pop(path, None)
        self._path_records.pop(path, None)
        if mapper is not None:
            try:
                mapper.stop()
            except Exception:
                pass
        try:
            hid.hid_manager.stop_polling(path)
        except Exception:
            pass

    def _on_emulate_requested(self, hid_choice: str, emu: str, widget: EmuListItemWidget):
        item = self._find_item_by_widget(widget)
        if item is None:
            logger.warning("Could not locate QListWidgetItem for controller widget")
            widget.set_running(False)
            return
        stored = item.data(Qt.UserRole) or (None, None, None)
        device = stored[0]
        display_name = stored[1] or hid_choice

        if not device:
            device = self._find_device_by_display_name(display_name)
            if not device:
                logger.warning("Could not match selected HID to a device")
                widget.set_running(False)
                return

        path = device.get("path")
        running = widget.is_running()
        key = id(item)

        if running:
            if key in self._mapping_records and self._mapping_records[key].get("waiting"):
                self._ensure_reconnect_timer()
                return
            if path in self.mappers:
                return
            if self._start_mapping(item, widget, device):
                self._ensure_reconnect_timer()
            else:
                widget.set_running(False)

        else:
            record = self._mapping_records.pop(key, None)
            actual_path = record.get("path") if record else path
            if actual_path:
                self._stop_mapping(actual_path)
            widget.set_battery(None)
            widget.set_connection_state(True)
            self._maybe_stop_reconnect_timer()

    def _on_battery_updated(self, path, percent: int, charging: bool) -> None:
        key = self._path_records.get(path)
        if key is None:
            return
        record = self._mapping_records.get(key)
        if record:
            record["widget"].set_battery(percent, charging)

    def _on_device_error(self, path: str, message: str) -> None:
        key = self._path_records.get(path)
        if key is None:
            return

        record = self._mapping_records.get(key)
        if not record:
            return

        logger.warning("Controller device lost at %s: %s", path, message)
        self._stop_mapping(path)
        self._stop_lightbar_output(path)
        record["waiting"] = True
        record["path"] = None
        record["widget"].set_connection_state(False)
        record["widget"].set_battery(None)
        if self._auto_reconnect_enabled():
            self._ensure_reconnect_timer()

    def _ensure_reconnect_timer(self) -> None:
        if not self._reconnect_timer_active:
            self._reconnect_timer.start()
            self._reconnect_timer_active = True

    def _maybe_stop_reconnect_timer(self) -> None:
        if any(record.get("waiting") for record in self._mapping_records.values()):
            return
        if self._reconnect_timer_active:
            self._reconnect_timer.stop()
            self._reconnect_timer_active = False

    def _is_matching_device(self, expected: dict, candidate: dict) -> bool:
        if self._device_id(expected.get("vendor_id")) != self._device_id(candidate.get("vendor_id")):
            return False
        if self._device_id(expected.get("product_id")) != self._device_id(candidate.get("product_id")):
            return False

        serial = expected.get("serial_number")
        candidate_serial = candidate.get("serial_number")
        return not serial or not candidate_serial or serial == candidate_serial

    def _try_reconnect(self) -> None:
        waiting = [
            record for record in self._mapping_records.values()
            if record.get("waiting") and record["widget"].is_running()
        ]
        if not waiting:
            self._maybe_stop_reconnect_timer()
            return

        try:
            devices = hid.hid_manager.scan_devices() or []
        except Exception as exc:
            logger.exception("Controller reconnect scan failed")
            return

        occupied_paths = set(self.mappers)
        for record in waiting:
            expected = record.get("last_device") or {}
            candidate = next(
                (
                    dev for dev in devices
                    if dev.get("path") not in occupied_paths
                    and is_preferred_sony_gamepad_interface(dev)
                    and self._is_matching_device(expected, dev)
                ),
                None,
            )
            if candidate is None:
                continue

            if self._start_mapping(
                record["item"], record["widget"], candidate, record=record
            ):
                occupied_paths.add(candidate.get("path"))

        self._maybe_stop_reconnect_timer()

    def _on_delete_requested(self, widget: EmuListItemWidget, item: QListWidgetItem):
        stored_data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(stored_data, dict) and stored_data.get("source") == "remote":
            self._disconnect_remote_device(str(stored_data.get("session_id") or ""))
            return

        key = id(item)
        record = self._mapping_records.pop(key, None)
        stored = item.data(Qt.UserRole) or (None, None, None)
        device = stored[0] or (record or {}).get("last_device")
        path = (record or {}).get("path") or (device or {}).get("path")
        if path:
            self._stop_mapping(path)
            self._stop_lightbar_output(path)

        for i in range(self.emu_list.count()):
            if self.emu_list.item(i) is item:
                self.emu_list.takeItem(i)
                break
        self._maybe_stop_reconnect_timer()

    def shutdown(self) -> None:
        for path in list(self.mappers):
            self._stop_mapping(path)
        for path in list(self._lightbar_outputs):
            self._stop_lightbar_output(path)
        self._mapping_records.clear()
        self._path_records.clear()
        self._reconnect_timer.stop()
        self._reconnect_timer_active = False
        try:
            self.hidhide_card.shutdown()
        except Exception as exc:
            logger.exception("HidHide cleanup failed during controller-emulation shutdown")
        try:
            hid.hid_manager.stop_all()
        except Exception:
            pass

    def _stop_lightbar_output(self, path) -> None:
        output = self._lightbar_outputs.pop(path, None)
        if output is not None:
            output.stop()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
