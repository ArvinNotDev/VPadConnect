"""Live raw DualSense gyroscope diagnostics."""

import time

import hid
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from core.dualsense_gyro import decode_dualsense_gyro, is_dualsense


class GyroTestPage(QWidget):
    """Inspect real raw gyro reports forwarded by the existing HID reader."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._devices: dict[str, dict] = {}
        self._last_report_at: dict[str, float] = {}
        self._report_counts: dict[str, int] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("DualSense Gyroscope Test")
        title.setStyleSheet("font-weight:700; font-size:20px;")
        root.addWidget(title)
        description = QLabel(
            "Displays the signed raw gyroscope values from real DualSense HID input reports. "
            "No stick values or estimated motion are used."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color:#91a2bc;")
        root.addWidget(description)

        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("PS5 controller"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(280)
        self.device_combo.currentIndexChanged.connect(self._select_device)
        selector_row.addWidget(self.device_combo, 1)
        root.addLayout(selector_row)

        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background:#1a2538; border:1px solid #344866; border-radius:14px; } "
            "QLabel { color:#dce8f8; }"
        )
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(12)
        self.connection_label = QLabel("Controller: scanning…")
        self.connection_label.setStyleSheet("font-weight:700; font-size:15px;")
        panel_layout.addWidget(self.connection_label)
        self.data_label = QLabel("Sensor data: waiting for an active input mapping")
        self.data_label.setStyleSheet("color:#91a2bc;")
        panel_layout.addWidget(self.data_label)

        self.axis_values: dict[str, QLabel] = {}
        self.axis_bars: dict[str, QProgressBar] = {}
        form = QFormLayout()
        form.setVerticalSpacing(12)
        for axis in ("X", "Y", "Z"):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            bar = QProgressBar()
            bar.setRange(-32768, 32767)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(16)
            value = QLabel("0")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setMinimumWidth(90)
            value.setStyleSheet("font-family:Consolas, monospace; font-weight:700;")
            row_layout.addWidget(bar, 1)
            row_layout.addWidget(value)
            form.addRow(QLabel(f"Gyro {axis}"), row)
            self.axis_values[axis] = value
            self.axis_bars[axis] = bar
        panel_layout.addLayout(form)
        self.packet_label = QLabel("Updated reports: 0")
        self.packet_label.setStyleSheet("color:#91a2bc;")
        panel_layout.addWidget(self.packet_label)
        root.addWidget(panel)

        hint = QLabel(
            "To receive live sensor values, connect the DualSense and start its mapping "
            "on the Controller Emulation page. The existing HID input reader supplies these reports."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#91a2bc;")
        root.addWidget(hint)
        root.addStretch(1)

        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.refresh_devices)
        self.scan_timer.start(1000)
        self.refresh_devices()

    def refresh_devices(self) -> None:
        try:
            devices = {
                self._path_key(device.get("path")): device
                for device in hid.enumerate()
                if is_dualsense(device.get("vendor_id"), device.get("product_id"))
                and device.get("path")
            }
        except Exception as exc:
            self.connection_label.setText(f"Controller scan failed: {exc}")
            return

        previous_path = self.device_combo.currentData()
        self._devices = devices
        current = {self.device_combo.itemData(i): self.device_combo.itemText(i)
                   for i in range(self.device_combo.count())}
        desired = {
            path: str(device.get("product_string") or device.get("manufacturer_string") or "DualSense")
            for path, device in devices.items()
        }
        if current != desired:
            self.device_combo.blockSignals(True)
            self.device_combo.clear()
            for path, name in desired.items():
                self.device_combo.addItem(name, path)
            index = self.device_combo.findData(previous_path)
            self.device_combo.setCurrentIndex(index if index >= 0 else (0 if desired else -1))
            self.device_combo.blockSignals(False)
        self._update_status()

    @staticmethod
    def _path_key(path) -> str:
        if isinstance(path, (bytes, bytearray)):
            return bytes(path).decode(errors="replace")
        return str(path or "")

    def receive_report(self, path: str, report: bytes) -> None:
        values = decode_dualsense_gyro(report)
        if values is None:
            return
        self._last_report_at[path] = time.monotonic()
        self._report_counts[path] = self._report_counts.get(path, 0) + 1
        if self.device_combo.currentData() == path:
            for axis, value in zip(("X", "Y", "Z"), values):
                self.axis_values[axis].setText(str(value))
                self.axis_bars[axis].setValue(value)
            self.packet_label.setText(f"Updated reports: {self._report_counts[path]}")
            self.data_label.setText("Sensor data: LIVE · raw HID reports are updating")
            self.data_label.setStyleSheet("color:#4ade80; font-weight:700;")

    def _select_device(self, _index: int) -> None:
        for axis in ("X", "Y", "Z"):
            self.axis_values[axis].setText("0")
            self.axis_bars[axis].setValue(0)
        self._update_status()

    def _update_status(self) -> None:
        path = self.device_combo.currentData()
        if not path:
            self.connection_label.setText("Controller: no DualSense detected")
            self.data_label.setText("Sensor data: unavailable")
            self.data_label.setStyleSheet("color:#91a2bc;")
            self.packet_label.setText("Updated reports: 0")
            return

        device = self._devices.get(path, {})
        name = device.get("product_string") or "DualSense"
        self.connection_label.setText(f"Controller: CONNECTED · {name}")
        last_report = self._last_report_at.get(path, 0.0)
        if time.monotonic() - last_report > 1.0:
            self.data_label.setText("Sensor data: waiting for reports from an active input mapping")
            self.data_label.setStyleSheet("color:#f4c37b;")
            self.packet_label.setText(f"Updated reports: {self._report_counts.get(path, 0)}")
