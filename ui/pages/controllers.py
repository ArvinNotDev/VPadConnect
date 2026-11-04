from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QDialog, QGridLayout, QFrame, QPushButton, QSpinBox,
    QScrollArea, QSlider, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen

from core import emulator
from core.vigem import is_vigem_installed
from ui.vigem_gate import VigemGate


class X360MonitorDialog(QDialog):
    def __init__(self, instance, name):
        super().__init__()
        self.instance = instance
        self.setWindowTitle(f"Monitoring: {name}")
        self.resize(500, 400)

        # ====== Global style for the dialog ======
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
            }
            QLabel {
                color: #f0f0f0;
                font-size: 11px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ====== Title ======
        title = QLabel(f"Xbox 360 Controller Monitor - {name}")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        main_layout.addWidget(title)

        # ====== Frame (border) around controller grid ======
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { border: 1px solid #555; border-radius: 6px; }")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(6)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        frame_layout.addLayout(grid)

        # ====== Labels ======
        # Face Buttons
        self.lbl_a = QLabel("A")
        self.lbl_b = QLabel("B")
        self.lbl_x = QLabel("X")
        self.lbl_y = QLabel("Y")

        # Bumpers
        self.lbl_lb = QLabel("LB")
        self.lbl_rb = QLabel("RB")

        # Triggers (analog)
        self.lbl_lt = QLabel("LT: 0")
        self.lbl_rt = QLabel("RT: 0")

        # D-Pad
        self.lbl_up = QLabel("↑")
        self.lbl_down = QLabel("↓")
        self.lbl_left = QLabel("←")
        self.lbl_right = QLabel("→")

        # Start/Back (option)
        self.lbl_start = QLabel("START")
        self.lbl_back = QLabel("BACK")

        # Joysticks (analog position)
        self.lbl_lj = QLabel("LJ: 0 , 0")
        self.lbl_rj = QLabel("RJ: 0 , 0")

        # Joystick click buttons (digital)
        self.lbl_l3 = QLabel("L3")
        self.lbl_r3 = QLabel("R3")

        # Binary display
        self.lbl_binary = QLabel("Buttons: 000000000000")
        self.lbl_binary.setAlignment(Qt.AlignCenter)
        self.lbl_binary.setStyleSheet("font-family: Consolas, monospace;")

        # Common style for button labels (digital)
        button_widgets = [
            self.lbl_a, self.lbl_b, self.lbl_x, self.lbl_y,
            self.lbl_lb, self.lbl_rb,
            self.lbl_up, self.lbl_down, self.lbl_left, self.lbl_right,
            self.lbl_start, self.lbl_back,
            self.lbl_l3, self.lbl_r3
        ]
        for w in button_widgets:
            w.setAlignment(Qt.AlignCenter)
            w.setMinimumWidth(40)
            w.setStyleSheet("""
                background:#444;
                color:white;
                border-radius:6px;
                padding:4px 6px;
            """)

        # Joysticks + triggers styling (analog info)
        for w in [self.lbl_lj, self.lbl_rj, self.lbl_lt, self.lbl_rt]:
            w.setAlignment(Qt.AlignCenter)
            w.setStyleSheet("""
                background:#333;
                color:#f0f0f0;
                border-radius:6px;
                padding:4px 6px;
            """)

        # ====== Layout (controller-like) ======

        # D-Pad block (left side)
        grid.addWidget(self.lbl_up,    1, 1, Qt.AlignCenter)
        grid.addWidget(self.lbl_left,  2, 0, Qt.AlignCenter)
        grid.addWidget(self.lbl_right, 2, 2, Qt.AlignCenter)
        grid.addWidget(self.lbl_down,  3, 1, Qt.AlignCenter)

        # Start / Back in the middle (shifted a bit to the right)
        grid.addWidget(self.lbl_back,  2, 3, Qt.AlignCenter)   # option/back (bit 5)
        grid.addWidget(self.lbl_start, 2, 4, Qt.AlignCenter)   # start (bit 4)

        # Face buttons block (right side)
        #   Y
        # X   B
        #   A
        grid.addWidget(self.lbl_y, 1, 6, Qt.AlignCenter)
        grid.addWidget(self.lbl_x, 2, 5, Qt.AlignCenter)
        grid.addWidget(self.lbl_b, 2, 7, Qt.AlignCenter)
        grid.addWidget(self.lbl_a, 3, 6, Qt.AlignCenter)

        # Row 0: LT / LB ...... RB / RT (shifted to match new columns)
        grid.addWidget(self.lbl_lt, 0, 0, 1, 2, Qt.AlignLeft)
        grid.addWidget(self.lbl_lb, 0, 2, 1, 1, Qt.AlignLeft)
        grid.addWidget(self.lbl_rb, 0, 5, 1, 1, Qt.AlignRight)
        grid.addWidget(self.lbl_rt, 0, 7, 1, 1, Qt.AlignRight)

        # Joysticks row (analog labels)
        grid.addWidget(self.lbl_lj, 4, 0, 1, 3, Qt.AlignLeft)
        grid.addWidget(self.lbl_rj, 4, 5, 1, 3, Qt.AlignRight)

        # L3 / R3 near sticks
        grid.addWidget(self.lbl_l3, 5, 0, 1, 1, Qt.AlignLeft)
        grid.addWidget(self.lbl_r3, 5, 6, 1, 1, Qt.AlignRight)

        # Add frame and binary line
        main_layout.addWidget(frame)
        main_layout.addWidget(self.lbl_binary)

        # ====== Monitor loop ======
        self.instance.is_monitoring = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_view)
        self.timer.start(30)

    def closeEvent(self, event):
        self.instance.is_monitoring = False
        self.timer.stop()
        super().closeEvent(event)

    def update_view(self):
        """
        Mapper calls emulator.update()
        when monitoring it returns:
        binary, rt, lt, ljx, ljy, rjx, rjy
        """
        try:
            data = getattr(self.instance, "_last_monitor", None)
            if not data:
                return

            binary, rt, lt, ljx, ljy, rjx, rjy = data

            self.lbl_binary.setText(f"Buttons: {binary}")
            self.lbl_rt.setText(f"RT: {rt}")
            self.lbl_lt.setText(f"LT: {lt}")
            self.lbl_lj.setText(f"LJ: {ljx} , {ljy}")
            self.lbl_rj.setText(f"RJ: {rjx} , {rjy}")

            # === Binary bit mapping ===
            # cls, a, b, y, x, start, option, r3, l3,
            # dpu, dpd, dpr, dpl, rb, lb, rt, lt, jlx, jly, jrx, jry
            # indices: 0     1  2  3  4    5      6    7   8   9   10  11  12  13  ...
            # You mapped:
            # a: 0, b: 1, y: 2, x: 3, start: 4, back(option): 5,
            # r3: 6, l3: 7, dpu: 8, dpd: 9, dpr: 10, dpl: 11, rb: 12, lb: 13
            mapping = [
                (self.lbl_a,    0),
                (self.lbl_b,    1),
                (self.lbl_y,    2),
                (self.lbl_x,    3),
                (self.lbl_start, 4),
                (self.lbl_back,  5),
                (self.lbl_r3,   6),
                (self.lbl_l3,   7),
                (self.lbl_up,   8),
                (self.lbl_down, 9),
                (self.lbl_right, 10),
                (self.lbl_left,  11),
                (self.lbl_rb,   12),
                (self.lbl_lb,   13),
            ]

            for label, index in mapping:
                pressed = len(binary) > index and binary[index] == "1"
                self._set_pressed(label, pressed)

        except Exception:
            pass

    def _set_pressed(self, label, pressed: bool):
        if pressed:
            label.setStyleSheet("""
                background:#2ecc71;
                color:black;
                border-radius:6px;
                padding:4px 6px;
            """)
        else:
            label.setStyleSheet("""
                background:#444;
                color:white;
                border-radius:6px;
                padding:4px 6px;
            """)


class X360TestRow(QWidget):
    """Per-controller XInput vibration controls for the test page."""

    def __init__(self, instance, name: str, parent=None):
        super().__init__(parent)
        self.instance = instance

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(5)

        header = QHBoxLayout()
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("font-weight: bold;")
        header.addWidget(self.name_label)

        self.battery_label = QLabel("Battery: —")
        self.battery_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.battery_label)
        root.addLayout(header)

        motor_row = QHBoxLayout()
        motor_row.setSpacing(6)

        motor_row.addWidget(QLabel("Left Motor"))
        self.left_spin = self._make_value_spin()
        motor_row.addWidget(self.left_spin)
        self.left_button = QPushButton("Test Left")
        self.left_button.clicked.connect(self._test_left)
        motor_row.addWidget(self.left_button)

        motor_row.addSpacing(10)
        motor_row.addWidget(QLabel("Right Motor"))
        self.right_spin = self._make_value_spin()
        motor_row.addWidget(self.right_spin)
        self.right_button = QPushButton("Test Right")
        self.right_button.clicked.connect(self._test_right)
        motor_row.addWidget(self.right_button)
        root.addLayout(motor_row)

        action_row = QHBoxLayout()
        self.both_button = QPushButton("Both Motors")
        self.both_button.clicked.connect(self._test_both)
        action_row.addWidget(self.both_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop)
        action_row.addWidget(self.stop_button)
        action_row.addStretch(1)
        root.addLayout(action_row)

        self.set_rumble_enabled(bool(getattr(instance, "supports_rumble", False)))

    @staticmethod
    def _make_value_spin() -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 0xFFFF)
        spin.setSingleStep(4096)
        spin.setValue(0xFFFF)
        spin.setMaximumWidth(95)
        return spin

    def set_name(self, name: str) -> None:
        self.name_label.setText(name)

    def set_battery(self, percent: int | None, charging: bool = False) -> None:
        if percent is None:
            self.battery_label.setText("Battery: —")
            return
        suffix = " (charging)" if charging else ""
        self.battery_label.setText(f"Battery: {percent}%{suffix}")

    def set_rumble_enabled(self, enabled: bool) -> None:
        for widget in (
            self.left_spin,
            self.right_spin,
            self.left_button,
            self.right_button,
            self.both_button,
            self.stop_button,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self.battery_label.setToolTip("Rumble output is available for DualSense controllers.")

    def _send(self, left: int, right: int) -> None:
        try:
            self.instance.set_xinput_vibration(left, right)
        except Exception as exc:
            print(f"[ControllersPage] Vibration test failed: {exc}")

    def _test_left(self) -> None:
        self._send(self.left_spin.value(), 0)

    def _test_right(self) -> None:
        self._send(0, self.right_spin.value())

    def _test_both(self) -> None:
        self._send(self.left_spin.value(), self.right_spin.value())

    def _stop(self) -> None:
        self._send(0, 0)


class StickIndicator(QWidget):
    """Live circular XInput joystick visual that never touches the input path."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.x_value = 0
        self.y_value = 0
        self.pressed = False
        self.setFixedSize(112, 128)

    def set_state(self, x_value: int, y_value: int, pressed: bool) -> None:
        state = (int(x_value), int(y_value), bool(pressed))
        if state == (self.x_value, self.y_value, self.pressed):
            return
        self.x_value, self.y_value, self.pressed = state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        circle = self.rect().adjusted(14, 25, -14, -14)
        painter.setPen(QPen(QColor("#60708d"), 2))
        painter.setBrush(QColor("#172033"))
        painter.drawEllipse(circle)
        painter.setPen(QPen(QColor("#35445f"), 1))
        painter.drawLine(circle.center().x(), circle.top() + 7, circle.center().x(), circle.bottom() - 7)
        painter.drawLine(circle.left() + 7, circle.center().y(), circle.right() - 7, circle.center().y())

        radius = circle.width() / 2
        knob_radius = 14
        x = circle.center().x() + (self.x_value / 32768.0) * (radius - knob_radius - 5)
        y = circle.center().y() - (self.y_value / 32768.0) * (radius - knob_radius - 5)
        painter.setPen(QPen(QColor("#b7c9e6"), 2))
        painter.setBrush(QColor("#72d5ff") if self.pressed else QColor("#4d82d9"))
        painter.drawEllipse(int(x - knob_radius), int(y - knob_radius), knob_radius * 2, knob_radius * 2)
        painter.setPen(QColor("#d8e2f2"))
        painter.drawText(self.rect().adjusted(0, 0, 0, -98), Qt.AlignCenter, self.title)
        painter.end()


class ControllerButton(QLabel):
    def __init__(self, text: str, active_color="#5e83ba", parent=None):
        super().__init__(text, parent)
        self.active_color = active_color
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(38, 38)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        self.setStyleSheet(
            f"background:{self.active_color if active else '#263348'}; "
            f"color:{'#06111f' if active else '#d5e1f3'}; "
            f"border:2px solid {'#eaf5ff' if active else '#53637f'}; "
            "border-radius:19px; font-weight:700;"
        )


class VibrationTestDialog(QDialog):
    """Separate motor test panel for one active XInput controller."""

    def __init__(self, instance, name: str, enabled: bool, parent=None):
        super().__init__(parent)
        self.instance = instance
        self.setWindowTitle(f"Vibration Test — {name}")
        self.setMinimumWidth(480)
        self.setStyleSheet("QDialog { background:#151d2c; } QLabel { color:#dbe7f7; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        title = QLabel("Xbox / XInput Vibration Test")
        title.setStyleSheet("font-size:16px; font-weight:700;")
        root.addWidget(title)
        detail = QLabel("Use independent 0–65535 motor values. The selected test stays active until you press Stop.")
        detail.setWordWrap(True)
        detail.setStyleSheet("color:#91a2bc;")
        root.addWidget(detail)

        self.left_slider, self.left_spin = self._add_motor(root, "Left motor · deep / strong")
        self.right_slider, self.right_spin = self._add_motor(root, "Right motor · light / high frequency")

        actions = QHBoxLayout()
        self.left_button = QPushButton("Test Left")
        self.left_button.clicked.connect(lambda: self._send(self.left_spin.value(), 0))
        actions.addWidget(self.left_button)
        self.right_button = QPushButton("Test Right")
        self.right_button.clicked.connect(lambda: self._send(0, self.right_spin.value()))
        actions.addWidget(self.right_button)
        self.both_button = QPushButton("Test Both")
        self.both_button.clicked.connect(lambda: self._send(self.left_spin.value(), self.right_spin.value()))
        actions.addWidget(self.both_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(lambda: self._send(0, 0))
        actions.addWidget(self.stop_button)
        root.addLayout(actions)

        self.status = QLabel()
        self.status.setStyleSheet("color:#8db5ff;")
        root.addWidget(self.status)
        self.set_vibration_enabled(enabled)

    @staticmethod
    def _add_motor(root, title: str):
        label = QLabel(title)
        label.setStyleSheet("font-weight:600;")
        root.addWidget(label)
        row = QHBoxLayout()
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 0xFFFF)
        slider.setSingleStep(256)
        slider.setPageStep(4096)
        slider.setValue(0xFFFF)
        row.addWidget(slider, 1)
        spin = QSpinBox()
        spin.setRange(0, 0xFFFF)
        spin.setSingleStep(4096)
        spin.setValue(0xFFFF)
        spin.setFixedWidth(105)
        row.addWidget(spin)
        root.addLayout(row)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        return slider, spin

    def set_vibration_enabled(self, enabled: bool) -> None:
        for widget in (self.left_slider, self.left_spin, self.right_slider, self.right_spin,
                       self.left_button, self.right_button, self.both_button, self.stop_button):
            widget.setEnabled(enabled)
        self.status.setText("Vibration is ready." if enabled else "Vibration is disabled in Settings.")

    def _send(self, left: int, right: int) -> None:
        try:
            self.instance.set_xinput_vibration(left, right)
            self.status.setText(f"Left: {left}   Right: {right}")
        except Exception as exc:
            self.status.setText(f"Could not send vibration: {exc}")

    def closeEvent(self, event):
        self._send(0, 0)
        event.accept()


class X360TestCard(QFrame):
    """Xbox-style live controller surface with a separate vibration menu."""

    gyro_state_changed = Signal(object, bool)

    def __init__(self, instance, name: str, vibration_enabled: bool, settings=None, parent=None):
        super().__init__(parent)
        self.instance = instance
        self._settings = settings
        self.controller_name = name
        self._vibration_enabled = vibration_enabled
        self._vibration_dialog = None
        self._gyro = getattr(instance, "gyro_steering", None)
        self.setStyleSheet(
            "QFrame { background:#1a2538; border:1px solid #344866; border-radius:16px; } "
            "QLabel { color:#dce8f8; } QPushButton { min-height:30px; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(10)

        header = QHBoxLayout()
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("font-size:15px; font-weight:700;")
        header.addWidget(self.name_label)
        header.addStretch(1)
        self.battery_label = QLabel("Battery: —")
        self.battery_label.setStyleSheet("color:#aabbd2;")
        header.addWidget(self.battery_label)
        self.gyro_toggle = QCheckBox("Gyro Steering")
        self.gyro_toggle.setToolTip(
            "When enabled, gyro controls left-stick horizontal steering. "
            "Left-stick vertical and other controls are unchanged."
        )
        self.gyro_toggle.setVisible(self._gyro is not None)
        if self._gyro is not None:
            self.gyro_toggle.setChecked(self._gyro.enabled)
        self.gyro_toggle.toggled.connect(self._set_gyro_enabled)
        header.addWidget(self.gyro_toggle)
        self.gyro_calibrate_button = QPushButton("Calibrate Center")
        self.gyro_calibrate_button.setToolTip("Hold the controller in its neutral pose, then calibrate.")
        self.gyro_calibrate_button.setVisible(self._gyro is not None)
        self.gyro_calibrate_button.clicked.connect(self._calibrate_gyro_center)
        header.addWidget(self.gyro_calibrate_button)
        self.vibration_button = QPushButton("Vibration Test")
        self.vibration_button.clicked.connect(self.open_vibration_test)
        header.addWidget(self.vibration_button)
        root.addLayout(header)

        self.gyro_settings_row = QWidget()
        self.gyro_settings_row.setObjectName("gyroSettingsRow")
        self.gyro_settings_row.setStyleSheet("""
            QWidget#gyroSettingsRow {
                background: #142136;
                border: 1px solid #304461;
                border-radius: 10px;
            }
            QWidget#gyroSettingsRow QLabel {
                color: #aec0d9;
                font-size: 11px;
                font-weight: 600;
            }
            QWidget#gyroSettingsRow QSlider::groove:horizontal {
                height: 4px;
                background: #334761;
                border-radius: 2px;
            }
            QWidget#gyroSettingsRow QSlider::handle:horizontal {
                width: 13px;
                margin: -5px 0;
                border-radius: 6px;
                background: #79c9ff;
                border: 1px solid #c8eaff;
            }
        """)
        gyro_settings = QHBoxLayout(self.gyro_settings_row)
        gyro_settings.setContentsMargins(10, 6, 10, 6)
        gyro_settings.setSpacing(8)
        gyro_settings.addWidget(QLabel("Sensitivity"))
        self.gyro_sensitivity_slider = QSlider(Qt.Horizontal)
        self.gyro_sensitivity_slider.setRange(25, 400)
        self.gyro_sensitivity_slider.setSingleStep(5)
        self.gyro_sensitivity_slider.setPageStep(25)
        self.gyro_sensitivity_slider.setFixedWidth(145)
        self.gyro_sensitivity_value = QLabel("1.00×")
        self.gyro_sensitivity_value.setMinimumWidth(44)
        gyro_settings.addWidget(self.gyro_sensitivity_slider)
        gyro_settings.addWidget(self.gyro_sensitivity_value)
        gyro_settings.addSpacing(8)
        gyro_settings.addWidget(QLabel("Deadzone"))
        self.gyro_deadzone_slider = QSlider(Qt.Horizontal)
        self.gyro_deadzone_slider.setRange(0, 150)
        self.gyro_deadzone_slider.setSingleStep(1)
        self.gyro_deadzone_slider.setPageStep(10)
        self.gyro_deadzone_slider.setFixedWidth(125)
        self.gyro_deadzone_value = QLabel("2.0°")
        self.gyro_deadzone_value.setMinimumWidth(42)
        gyro_settings.addWidget(self.gyro_deadzone_slider)
        gyro_settings.addWidget(self.gyro_deadzone_value)
        gyro_settings.addSpacing(10)
        self.gyro_live_label = QLabel("OFF  ·  ROLL +0.0°  ·  STEER +0%")
        self.gyro_live_label.setObjectName("gyroLiveStatus")
        self.gyro_live_label.setAlignment(Qt.AlignCenter)
        self.gyro_live_label.setMinimumWidth(265)
        self.gyro_live_label.setToolTip(
            "Live roll angle, steering output, and the measured controller sensor report rate."
        )
        self.gyro_live_label.setStyleSheet(
            "QLabel#gyroLiveStatus { background:#102b30; color:#83e6c5; "
            "border:1px solid #2d665f; border-radius:8px; padding:6px 9px; "
            "font-family:Consolas; font-size:10px; font-weight:700; }"
        )
        gyro_settings.addWidget(self.gyro_live_label)
        gyro_settings.addStretch(1)
        self.gyro_settings_row.setVisible(self._gyro is not None)
        if self._gyro is not None:
            self.gyro_sensitivity_slider.setValue(round(self._gyro.sensitivity * 100))
            self.gyro_deadzone_slider.setValue(round(self._gyro.deadzone_degrees * 10))
        self.gyro_sensitivity_slider.valueChanged.connect(self._update_gyro_parameters)
        self.gyro_deadzone_slider.valueChanged.connect(self._update_gyro_parameters)
        self.gyro_sensitivity_slider.sliderReleased.connect(self._save_gyro_settings)
        self.gyro_deadzone_slider.sliderReleased.connect(self._save_gyro_settings)
        root.addWidget(self.gyro_settings_row)

        surface = QFrame()
        surface.setStyleSheet("background:#111a29; border:1px solid #2b3e5b; border-radius:28px;")
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(24, 14, 24, 18)
        layout.setSpacing(8)

        top = QGridLayout()
        self.lt_label = self._status_label("LT  0")
        self.lb = self._status_label("LB")
        self.rb = self._status_label("RB")
        self.rt_label = self._status_label("RT  0")
        top.addWidget(self.lt_label, 0, 0)
        top.addWidget(self.lb, 0, 1)
        top.setColumnStretch(2, 1)
        top.addWidget(self.rb, 0, 3)
        top.addWidget(self.rt_label, 0, 4)
        layout.addLayout(top)

        body = QGridLayout()
        body.setHorizontalSpacing(16)
        for column in (0, 1, 3, 4):
            body.setColumnStretch(column, 2)
        body.setColumnStretch(2, 1)

        dpad = QWidget()
        dpad_layout = QGridLayout(dpad)
        dpad_layout.setSpacing(3)
        self.up, self.down = ControllerButton("▲"), ControllerButton("▼")
        self.left, self.right = ControllerButton("◀"), ControllerButton("▶")
        dpad_layout.addWidget(self.up, 0, 1)
        dpad_layout.addWidget(self.left, 1, 0)
        dpad_layout.addWidget(self.right, 1, 2)
        dpad_layout.addWidget(self.down, 2, 1)
        body.addWidget(dpad, 0, 0, alignment=Qt.AlignCenter)

        self.left_stick = StickIndicator("LEFT STICK")
        body.addWidget(self.left_stick, 0, 1, alignment=Qt.AlignCenter)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        self.back = self._status_label("BACK")
        self.start = self._status_label("START")
        center_layout.addWidget(self.back)
        center_layout.addWidget(self.start)
        body.addWidget(center, 0, 2, alignment=Qt.AlignCenter)

        face = QWidget()
        face_layout = QGridLayout(face)
        face_layout.setSpacing(3)
        self.y = ControllerButton("Y", "#d7b838")
        self.x = ControllerButton("X", "#4192de")
        self.b = ControllerButton("B", "#d85b58")
        self.a = ControllerButton("A", "#57b87a")
        face_layout.addWidget(self.y, 0, 1)
        face_layout.addWidget(self.x, 1, 0)
        face_layout.addWidget(self.b, 1, 2)
        face_layout.addWidget(self.a, 2, 1)
        body.addWidget(face, 0, 3, alignment=Qt.AlignCenter)

        self.right_stick = StickIndicator("RIGHT STICK")
        body.addWidget(self.right_stick, 0, 4, alignment=Qt.AlignCenter)
        layout.addLayout(body)
        root.addWidget(surface)

        self.set_vibration_enabled(vibration_enabled)
        self.view_timer = QTimer(self)
        self.view_timer.timeout.connect(self.update_view)
        self.view_timer.start(30)

    def _set_gyro_enabled(self, enabled: bool) -> None:
        if self._gyro is None:
            return
        self._gyro.set_enabled(enabled)
        self._save_gyro_settings()
        self.gyro_state_changed.emit(self.instance.device_path, bool(enabled))

    def set_gyro_enabled(self, enabled: bool) -> None:
        if self._gyro is None:
            return
        self.gyro_toggle.setChecked(bool(enabled))

    def toggle_gyro(self) -> bool | None:
        if self._gyro is None:
            return None
        self.set_gyro_enabled(not self._gyro.enabled)
        return self._gyro.enabled

    def _update_gyro_parameters(self, _value: int) -> None:
        if self._gyro is None:
            return
        sensitivity = self.gyro_sensitivity_slider.value() / 100.0
        deadzone = self.gyro_deadzone_slider.value() / 10.0
        self.gyro_sensitivity_value.setText(f"{sensitivity:.2f}×")
        self.gyro_deadzone_value.setText(f"{deadzone:.1f}°")
        self._gyro.set_parameters(sensitivity, deadzone)

    def _calibrate_gyro_center(self) -> None:
        if self._gyro is None:
            return
        center = self._gyro.calibrate_center()
        if center is not None:
            self._save_gyro_settings()
            self.gyro_calibrate_button.setText("Center Calibrated")
            QTimer.singleShot(1600, lambda: self.gyro_calibrate_button.setText("Calibrate Center"))
        else:
            self.gyro_calibrate_button.setText("Waiting for Sensor")
            QTimer.singleShot(1600, lambda: self.gyro_calibrate_button.setText("Calibrate Center"))

    def _save_gyro_settings(self) -> None:
        if self._gyro is None or self._settings is None:
            return
        controller_id = getattr(self.instance, "gyro_controller_id", None)
        if not controller_id:
            return
        self._settings.set_controller_gyro_settings(controller_id, {
            "enabled": self._gyro.enabled,
            "sensitivity": self._gyro.sensitivity,
            "deadzone_degrees": self._gyro.deadzone_degrees,
            "center_gravity": self._gyro.calibrated_center,
        })
        self._settings.save()

    @staticmethod
    def _status_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumWidth(58)
        label.setStyleSheet("background:#263348; border:1px solid #53637f; border-radius:8px; padding:5px 9px; font-weight:700;")
        return label

    @staticmethod
    def _set_active(label: QLabel, active: bool) -> None:
        label.setStyleSheet(
            "background:#75a0df; color:#07111e; border:1px solid #e8f4ff; border-radius:8px; padding:5px 9px; font-weight:700;"
            if active else
            "background:#263348; border:1px solid #53637f; border-radius:8px; padding:5px 9px; font-weight:700;"
        )

    def set_name(self, name: str) -> None:
        self.controller_name = name
        self.name_label.setText(name)

    def set_instance(self, instance) -> None:
        """Replace a reconnecting emulator and its per-connection gyro state."""
        self.instance = instance
        self._gyro = getattr(instance, "gyro_steering", None)
        available = self._gyro is not None
        self.gyro_toggle.setVisible(available)
        self.gyro_calibrate_button.setVisible(available)
        self.gyro_settings_row.setVisible(available)
        if not available:
            return
        self.gyro_toggle.blockSignals(True)
        self.gyro_toggle.setChecked(self._gyro.enabled)
        self.gyro_toggle.blockSignals(False)
        self.gyro_sensitivity_slider.blockSignals(True)
        self.gyro_sensitivity_slider.setValue(round(self._gyro.sensitivity * 100))
        self.gyro_sensitivity_slider.blockSignals(False)
        self.gyro_deadzone_slider.blockSignals(True)
        self.gyro_deadzone_slider.setValue(round(self._gyro.deadzone_degrees * 10))
        self.gyro_deadzone_slider.blockSignals(False)
        self._update_gyro_parameters(0)

    def set_battery(self, percent: int | None, charging: bool = False) -> None:
        if percent is None:
            self.battery_label.setText("🔋 Battery: —")
            self.battery_label.setStyleSheet("color:#aabbd2;")
            return

        percent = max(0, min(100, int(percent)))
        if charging:
            self.battery_label.setText(f"🔋 {percent}%  ⚡ Charging")
            self.battery_label.setStyleSheet("color:#4ade80; font-weight:700;")
        elif percent >= 100:
            self.battery_label.setText("🔋 100%  ✓ Fully charged")
            self.battery_label.setStyleSheet("color:#75e0ad; font-weight:700;")
        else:
            self.battery_label.setText(f"🔋 {percent}%")
            self.battery_label.setStyleSheet("color:#aabbd2;")

    def set_vibration_enabled(self, enabled: bool) -> None:
        self._vibration_enabled = bool(enabled)
        available = bool(getattr(self.instance, "supports_rumble", False))
        self.vibration_button.setEnabled(available and self._vibration_enabled)
        if self._vibration_dialog is not None:
            self._vibration_dialog.set_vibration_enabled(available and self._vibration_enabled)

    def open_vibration_test(self) -> None:
        if self._vibration_dialog is None:
            self._vibration_dialog = VibrationTestDialog(
                self.instance, self.controller_name,
                bool(getattr(self.instance, "supports_rumble", False)) and self._vibration_enabled,
                self,
            )
            self._vibration_dialog.finished.connect(lambda _: setattr(self, "_vibration_dialog", None))
        self._vibration_dialog.show()
        self._vibration_dialog.raise_()
        self._vibration_dialog.activateWindow()

    def update_view(self) -> None:
        if self._gyro is not None:
            try:
                angle = self._gyro.current_angle_degrees
                output = self._gyro.steering_value
                state = "ON" if self._gyro.enabled else "OFF"
                percent = int(round(output * 100.0 / 32767.0))
                rate = self._gyro.sample_rate_hz
                rate_text = f"{rate:.0f}Hz" if rate is not None else "--Hz"
                status = (
                    f"{state}  ·  ROLL {angle:+.1f}°  ·  "
                    f"STEER {percent:+d}%  ·  {rate_text}"
                )
                if self.gyro_live_label.text() != status:
                    self.gyro_live_label.setText(status)
            except Exception:
                pass

        data = getattr(self.instance, "_last_monitor", None)
        if not data:
            return
        try:
            binary, rt, lt, ljx, ljy, rjx, rjy = data
            pressed = lambda index: len(binary) > index and binary[index] == "1"
            self.lt_label.setText(f"LT  {lt}")
            self.rt_label.setText(f"RT  {rt}")
            self.a.set_active(pressed(0)); self.b.set_active(pressed(1))
            self.y.set_active(pressed(2)); self.x.set_active(pressed(3))
            self._set_active(self.start, pressed(4)); self._set_active(self.back, pressed(5))
            self.right_stick.set_state(rjx, rjy, pressed(6)); self.left_stick.set_state(ljx, ljy, pressed(7))
            self.up.set_active(pressed(8)); self.down.set_active(pressed(9))
            self.right.set_active(pressed(10)); self.left.set_active(pressed(11))
            self._set_active(self.rb, pressed(12)); self._set_active(self.lb, pressed(13))
        except Exception:
            pass


class ControllersPage(QWidget):
    battery_updated = Signal(object, int, bool)  # path, percent, charging
    vigem_recheck_requested = Signal()

    def __init__(self, settings=None, *, vigem_available: bool | None = None):
        super().__init__()
        self.settings = settings
        try:
            self._vibration_enabled = bool(settings.get_vibration_enabled())
        except Exception:
            self._vibration_enabled = True

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(8)

        title = QLabel("XInput Controller Test")
        title.setStyleSheet("font-weight:700; font-size:20px;")
        subtitle = QLabel(
            "Live controller state is visualized without interrupting normal input forwarding."
        )
        subtitle.setStyleSheet("color:#91a2bc;")

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 8, 0, 8)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(self.cards_container)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        shortcut_row = QHBoxLayout()
        shortcut_row.addWidget(QLabel("Gyro shortcut target"))
        self.gyro_target_combo = QComboBox()
        self.gyro_target_combo.setMinimumWidth(210)
        self.gyro_target_combo.setEnabled(False)
        shortcut_row.addWidget(self.gyro_target_combo)
        self.gyro_shortcut_status = QLabel("Ctrl+Shift+G · no supported controller selected")
        self.gyro_shortcut_status.setStyleSheet("color:#91a2bc;")
        shortcut_row.addWidget(self.gyro_shortcut_status)
        shortcut_row.addStretch(1)
        layout.addLayout(shortcut_row)
        self.gyro_target_combo.currentIndexChanged.connect(self._update_gyro_shortcut_status)
        layout.addWidget(self.scroll, 1)

        self.vigem_gate = VigemGate(content)
        self.vigem_gate.recheck_requested.connect(self.vigem_recheck_requested.emit)
        self.vigem_gate.set_vigem_available(
            is_vigem_installed() if vigem_available is None else vigem_available
        )
        page_layout.addWidget(self.vigem_gate, 1)

        self.empty_label = QLabel(
            "No active XInput controllers. Start controller emulation to inspect one here."
        )
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color:#91a2bc; padding:28px;")
        self.cards_layout.insertWidget(0, self.empty_label)

        self.x360_instances = {}
        self.battery_states = {}
        self._cards = {}
        self.battery_updated.connect(self._store_battery)
        self._gyro_shortcut_available = False

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_list)
        self.refresh_timer.start(1000)

    def set_vigem_available(self, available: bool) -> None:
        self.vigem_gate.set_vigem_available(available)

    def add_x360_instance(self, instance):
        if hasattr(instance, 'device_path'):
            self.x360_instances[instance.device_path] = instance
        self.refresh_list()

    def update_battery(self, device_path: str, percent: int, charging: bool) -> None:
        self.battery_states[device_path] = (int(percent), bool(charging))
        self.battery_updated.emit(device_path, int(percent), bool(charging))
        self.refresh_list()

    def _store_battery(self, device_path: str, percent: int, charging: bool) -> None:
        self.battery_states[device_path] = (int(percent), bool(charging))
        self.refresh_list()

    def clear_battery(self, device_path) -> None:
        self.battery_states.pop(device_path, None)
        card = self._cards.get(device_path)
        if card is not None:
            card.set_battery(None)
        self.refresh_list()

    def set_vibration_enabled(self, enabled: bool) -> None:
        """Apply the Settings toggle to every active controller immediately."""
        self._vibration_enabled = bool(enabled)
        for instance in self.x360_instances.values():
            setter = getattr(instance, "set_vibration_enabled", None)
            if setter is not None:
                setter(self._vibration_enabled)
        for card in self._cards.values():
            card.set_vibration_enabled(self._vibration_enabled)

    def refresh_list(self):
        with emulator.ListOfAllControllers.lock:
            active_paths = list(emulator.ListOfAllControllers.controllers_path)
            active_names = list(emulator.ListOfAllControllers.controllers_name)

        active = {
            path: active_names[index]
            for index, path in enumerate(active_paths)
            if index < len(active_names)
        }

        for path in set(self._cards) - set(active):
            card = self._cards.pop(path)
            card.setParent(None)
            card.deleteLater()
            self.x360_instances.pop(path, None)

        for path, name in active.items():
            instance = self.x360_instances.get(path)
            if instance is None:
                continue

            card = self._cards.get(path)
            if card is None:
                card = X360TestCard(instance, name, self._vibration_enabled, settings=self.settings)
                card.gyro_state_changed.connect(self._on_gyro_state_changed)
                self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
                self._cards[path] = card
            else:
                if card.instance is not instance:
                    card.set_instance(instance)
                card.set_name(name)
                card.set_vibration_enabled(self._vibration_enabled)

            battery = self.battery_states.get(path)
            if battery is None:
                card.set_battery(None)
            else:
                card.set_battery(*battery)

        self.empty_label.setVisible(not self._cards)
        self._refresh_gyro_targets(active)

    def _refresh_gyro_targets(self, active: dict) -> None:
        previous = self.gyro_target_combo.currentData()
        targets = [
            (path, active[path])
            for path in active
            if path in self.x360_instances
            and getattr(self.x360_instances[path], "gyro_steering", None) is not None
        ]
        existing = [self.gyro_target_combo.itemData(i) for i in range(self.gyro_target_combo.count())]
        desired = [path for path, _name in targets]
        if existing != desired:
            self.gyro_target_combo.blockSignals(True)
            self.gyro_target_combo.clear()
            for path, name in targets:
                self.gyro_target_combo.addItem(name, path)
            selected = self.gyro_target_combo.findData(previous)
            self.gyro_target_combo.setCurrentIndex(selected if selected >= 0 else (0 if targets else -1))
            self.gyro_target_combo.blockSignals(False)
        self.gyro_target_combo.setEnabled(bool(targets))
        self._update_gyro_shortcut_status()

    def _update_gyro_shortcut_status(self, _index: int = -1) -> None:
        path = self.gyro_target_combo.currentData()
        card = self._cards.get(path)
        shortcut = "Ctrl+Shift+G" if self._gyro_shortcut_available else "Gyro shortcut unavailable"
        if card is None or card._gyro is None:
            self.gyro_shortcut_status.setText(f"{shortcut} · no DualSense selected")
            return
        state = "ON" if card._gyro.enabled else "OFF"
        self.gyro_shortcut_status.setText(f"{shortcut} · {card.controller_name}: {state}")

    def set_gyro_shortcut_available(self, available: bool) -> None:
        self._gyro_shortcut_available = bool(available)
        self._update_gyro_shortcut_status()

    def _on_gyro_state_changed(self, _path, _enabled: bool) -> None:
        self._update_gyro_shortcut_status()

    def toggle_selected_gyro(self) -> bool:
        path = self.gyro_target_combo.currentData()
        card = self._cards.get(path)
        if card is None:
            return False
        card.toggle_gyro()
        return True
