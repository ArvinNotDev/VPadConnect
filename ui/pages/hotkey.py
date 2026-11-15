import sys
from typing import Optional, List, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QGroupBox,
    QSpacerItem,
    QSizePolicy,
    QDialog,
    QListWidget,
    QListWidgetItem,
    QFrame,
)

from core import emulator
from ui.animations import AnimatedDialog


class PressTwoButtonsAtTheSameTime(AnimatedDialog):
    """
    Dialog for capturing a hotkey combination consisting of exactly two buttons.

    Logic:
    - Continuously monitor controller state via `instance._last_monitor`.
    - When exactly two buttons are pressed, the combination is locked.
    - After locking, Apply/Redo become enabled.
    - Result:
        selected_buttons : list[str] (e.g. ["A", "UP"])
        binary_string    : str      (bitmask for pressed buttons)
    """

    def __init__(self, instance):
        super().__init__()

        self.instance = instance

        self.selected_buttons: List[str] = []
        self.binary_string: Optional[str] = None

        self._locked: bool = False
        self._locked_buttons: List[str] = []
        self._locked_indices: List[int] = []

        self.setWindowTitle("Press Hotkey Combination")
        self.resize(520, 380)

        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
            }
            QLabel {
                color: #f0f0f0;
                font-size: 12px;
            }
            QLabel#TitleLabel {
                font-size: 16px;
                font-weight: bold;
            }
            QLabel#StepLabel {
                font-size: 13px;
            }
            QLabel#PressedLabel {
                font-size: 18px;
                font-weight: bold;
                color: #2ecc71;
            }
            QLabel#StatusLabel {
                font-size: 11px;
                color: #bbbbbb;
            }
            QPushButton {
                background-color: #444;
                color: white;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #777;
                border: 1px solid #444;
            }
            QFrame#OuterFrame {
                border: 1px solid #555;
                border-radius: 6px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(10)

        title_label = QLabel("Define Hotkey Combination")
        title_label.setObjectName("TitleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        step_label = QLabel("Press exactly two buttons on your controller at the same time.")
        step_label.setObjectName("StepLabel")
        step_label.setAlignment(Qt.AlignCenter)
        step_label.setWordWrap(True)
        main_layout.addWidget(step_label)

        outer_frame = QFrame()
        outer_frame.setObjectName("OuterFrame")
        outer_layout = QVBoxLayout(outer_frame)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(6)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        outer_layout.addLayout(grid)

        self.lbl_a = QLabel("A")
        self.lbl_b = QLabel("B")
        self.lbl_x = QLabel("X")
        self.lbl_y = QLabel("Y")

        self.lbl_lb = QLabel("LB")
        self.lbl_rb = QLabel("RB")

        self.lbl_up = QLabel("↑")
        self.lbl_down = QLabel("↓")
        self.lbl_left = QLabel("←")
        self.lbl_right = QLabel("→")

        self.lbl_start = QLabel("START")
        self.lbl_back = QLabel("BACK")

        self.lbl_l3 = QLabel("L3")
        self.lbl_r3 = QLabel("R3")

        self.button_widgets = [
            self.lbl_a, self.lbl_b, self.lbl_x, self.lbl_y,
            self.lbl_lb, self.lbl_rb,
            self.lbl_up, self.lbl_down, self.lbl_left, self.lbl_right,
            self.lbl_start, self.lbl_back,
            self.lbl_l3, self.lbl_r3,
        ]

        for w in self.button_widgets:
            w.setAlignment(Qt.AlignCenter)
            w.setMinimumWidth(40)
            w.setMinimumHeight(28)
            w.setStyleSheet("""
                background:#444;
                color:white;
                border-radius:6px;
                padding:4px 8px;
            """)

        grid.addWidget(self.lbl_up,    1, 1, Qt.AlignCenter)
        grid.addWidget(self.lbl_left,  2, 0, Qt.AlignCenter)
        grid.addWidget(self.lbl_right, 2, 2, Qt.AlignCenter)
        grid.addWidget(self.lbl_down,  3, 1, Qt.AlignCenter)

        grid.addWidget(self.lbl_back,  2, 3, Qt.AlignCenter)
        grid.addWidget(self.lbl_start, 2, 4, Qt.AlignCenter)

        grid.addWidget(self.lbl_y, 1, 6, Qt.AlignCenter)
        grid.addWidget(self.lbl_x, 2, 5, Qt.AlignCenter)
        grid.addWidget(self.lbl_b, 2, 7, Qt.AlignCenter)
        grid.addWidget(self.lbl_a, 3, 6, Qt.AlignCenter)

        grid.addWidget(self.lbl_lb, 0, 2, Qt.AlignLeft)
        grid.addWidget(self.lbl_rb, 0, 5, Qt.AlignRight)

        grid.addWidget(self.lbl_l3, 5, 0, Qt.AlignLeft)
        grid.addWidget(self.lbl_r3, 5, 6, Qt.AlignRight)

        main_layout.addWidget(outer_frame)

        self.pressed_label = QLabel("No buttons pressed")
        self.pressed_label.setObjectName("PressedLabel")
        self.pressed_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.pressed_label)

        self.status_label = QLabel("0 buttons pressed")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.redo_btn = QPushButton("Redo")
        self.apply_btn = QPushButton("Apply")

        self.redo_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)

        self.redo_btn.clicked.connect(self.on_redo)
        self.apply_btn.clicked.connect(self.on_apply)

        btn_layout.addWidget(self.redo_btn)
        btn_layout.addWidget(self.apply_btn)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        self.button_map = [
            ("A", self.lbl_a),         # 0
            ("B", self.lbl_b),         # 1
            ("Y", self.lbl_y),         # 2
            ("X", self.lbl_x),         # 3
            ("START", self.lbl_start), # 4
            ("BACK", self.lbl_back),   # 5
            ("R3", self.lbl_r3),       # 6
            ("L3", self.lbl_l3),       # 7
            ("UP", self.lbl_up),       # 8
            ("DOWN", self.lbl_down),   # 9
            ("RIGHT", self.lbl_right), # 10
            ("LEFT", self.lbl_left),   # 11
            ("RB", self.lbl_rb),       # 12
            ("LB", self.lbl_lb),       # 13
        ]

        self.instance.is_monitoring = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_view)
        self.timer.start(30)

    def _set_pressed_style(self, label: QLabel, pressed: bool) -> None:
        """
        Apply visual state to a button label.

        :param label: QLabel representing the button.
        :param pressed: True if the button should be shown as pressed.
        """
        if pressed:
            label.setStyleSheet("""
                background:#2ecc71;
                color:black;
                border-radius:6px;
                padding:4px 8px;
            """)
        else:
            label.setStyleSheet("""
                background:#444;
                color:white;
                border-radius:6px;
                padding:4px 8px;
            """)

    def _render_locked_state(self) -> None:
        """
        Render labels according to the locked combination, ignoring live input.
        """
        for idx, (_, label) in enumerate(self.button_map):
            self._set_pressed_style(label, idx in self._locked_indices)

        if self._locked_buttons:
            self.pressed_label.setText(" + ".join(self._locked_buttons))
            self.status_label.setText("Combination locked - click Apply or Redo")
        else:
            self.pressed_label.setText("No buttons pressed")
            self.status_label.setText("0 buttons pressed")

    def update_view(self) -> None:
        """
        Poll controller state, update UI, and lock combo when exactly two buttons are pressed.
        """
        if self._locked:
            self._render_locked_state()
            return

        try:
            data = getattr(self.instance, "_last_monitor", None)
            if not data:
                return

            binary = data[0]
            if len(binary) < len(self.button_map):
                binary = binary.ljust(len(self.button_map), "0")

            current_pressed: List[str] = []
            current_indices: List[int] = []

            for idx, (name, label) in enumerate(self.button_map):
                pressed = binary[idx] == "1"
                self._set_pressed_style(label, pressed)
                if pressed:
                    current_pressed.append(name)
                    current_indices.append(idx)

            if current_pressed:
                self.pressed_label.setText(" + ".join(current_pressed))
            else:
                self.pressed_label.setText("No buttons pressed")

            count = len(current_pressed)

            if count == 0:
                self.status_label.setText("0 buttons pressed")
            elif count == 1:
                self.status_label.setText("1 button pressed - press one more")
            elif count == 2:
                self.status_label.setText("2 buttons detected - releasing will keep this combo")

                self._locked = True
                self._locked_buttons = current_pressed[:]
                self._locked_indices = current_indices[:]
                self.selected_buttons = current_pressed[:]

                bits = ["0"] * len(self.button_map)
                for idx in current_indices:
                    bits[idx] = "1"
                self.binary_string = "".join(bits)

                self.apply_btn.setEnabled(True)
                self.redo_btn.setEnabled(True)
            else:
                self.status_label.setText(
                    f"{count} buttons pressed - release until only two remain"
                )

            if not self._locked:
                self.selected_buttons = []
                self.binary_string = None
                self.apply_btn.setEnabled(False)
                self.redo_btn.setEnabled(False)

        except Exception:
            # Keep UI responsive even if monitoring fails.
            pass

    def on_redo(self) -> None:
        """
        Clear locked combination and resume live monitoring.
        """
        self._locked = False
        self._locked_buttons = []
        self._locked_indices = []
        self.selected_buttons = []
        self.binary_string = None

        for _, label in self.button_map:
            self._set_pressed_style(label, False)

        self.pressed_label.setText("No buttons pressed")
        self.status_label.setText("0 buttons pressed")

        self.apply_btn.setEnabled(False)
        self.redo_btn.setEnabled(False)

    def on_apply(self) -> None:
        """
        Confirm the current locked combination and close dialog.
        """
        if self._locked and len(self.selected_buttons) == 2 and self.binary_string:
            print(
                f"Buttons selected for hotkey: "
                f"{self.selected_buttons[0]} + {self.selected_buttons[1]} "
                f"({self.binary_string})"
            )
            self.accept()

    def closeEvent(self, event) -> None:
        """
        Stop monitoring when dialog is closed.
        """
        self.instance.is_monitoring = False
        self.timer.stop()
        super().closeEvent(event)


class HotkeyDialog(AnimatedDialog):
    """
    Dialog for managing hotkeys bound to a single controller instance.

    The `hotkey` manager is expected to provide:
        - set_hotkey(binary_bytes, action) -> (ok: bool, message: str)
        - clear_hotkey(binary_str)         -> (ok: bool, message: str)
        - list_hotkeys()                   -> iterable of (binary_str, action) or dict
    """

    def __init__(self, instance, name: str, hotkey):
        super().__init__()

        self.instance = instance
        self.controller_name = name
        self.hotkey = hotkey

        self.setWindowTitle(f"Hotkey Settings - {name}")
        self.setMinimumSize(750, 450)

        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
            }
            QLabel {
                color: #f0f0f0;
                font-size: 11px;
            }
            QLabel#MainTitle {
                font-size: 16px;
                font-weight: bold;
            }
            QLabel#Subtitle {
                font-size: 11px;
                color: #cccccc;
            }
            QGroupBox {
                color: #f0f0f0;
                border: 1px solid #555;
                border-radius: 6px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QPushButton {
                background-color: #444;
                color: white;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QComboBox {
                background-color: #444;
                color: white;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
            QListWidget {
                background-color: #333;
                color: #f0f0f0;
                border: 1px solid #555;
                border-radius: 4px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(40, 20, 40, 20)

        title_label = QLabel(f"Hotkey Management - {name}")
        title_label.setObjectName("MainTitle")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        subtitle_label = QLabel(
            "Select a hotkey action and use the buttons below to add or remove it.\n"
            "Hotkey combinations are captured from the selected controller."
        )
        subtitle_label.setObjectName("Subtitle")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setWordWrap(True)
        main_layout.addWidget(subtitle_label)

        split_layout = QHBoxLayout()
        split_layout.setSpacing(16)
        main_layout.addLayout(split_layout)

        hotkey_group = QGroupBox("Add / Delete Hotkeys")
        group_layout = QVBoxLayout()
        group_layout.setSpacing(10)
        group_layout.setContentsMargins(15, 25, 15, 15)

        info_label = QLabel(
            "Choose an action, then click 'Add Hotkey' to define a button combination, "
            "or 'Delete Hotkey' to remove existing mapping(s) for that action."
        )
        info_label.setWordWrap(True)
        group_layout.addWidget(info_label)

        row_layout = QHBoxLayout()
        row_layout.setSpacing(10)

        self.hotkey_combo = QComboBox()
        self.hotkey_combo.setMinimumWidth(250)
        self.hotkey_combo.addItems(
            [
                "volume up",
                "volume down",
                "volume mute",
                "play/pause media",
                "next track",
                "previous track",
            ]
        )
        row_layout.addWidget(self.hotkey_combo, stretch=2)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        self.add_button = QPushButton("Add Hotkey")
        self.delete_button = QPushButton("Delete Hotkey")

        self.add_button.clicked.connect(self.on_add_hotkey_clicked)
        self.delete_button.clicked.connect(self.on_delete_hotkey_clicked)

        buttons_layout.addWidget(self.add_button)
        buttons_layout.addWidget(self.delete_button)

        row_layout.addLayout(buttons_layout, stretch=1)
        group_layout.addLayout(row_layout)

        group_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        hotkey_group.setLayout(group_layout)
        split_layout.addWidget(hotkey_group, stretch=1)

        self.list_group = QGroupBox("Current Hotkeys")
        list_layout = QVBoxLayout()
        list_layout.setSpacing(6)
        list_layout.setContentsMargins(10, 20, 10, 10)

        info2 = QLabel(
            "Existing hotkey mappings from the hotkey manager.\n"
            "Format: <binary>  →  <action>"
        )
        info2.setWordWrap(True)
        list_layout.addWidget(info2)

        self.hotkey_list = QListWidget()
        list_layout.addWidget(self.hotkey_list)

        self.list_group.setLayout(list_layout)
        split_layout.addWidget(self.list_group, stretch=1)

        main_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.refresh_hotkey_list()

    def refresh_hotkey_list(self) -> None:
        """
        Reload and display hotkeys from the manager.
        """
        self.hotkey_list.clear()
        try:
            items = self.hotkey.list_hotkeys()
        except Exception as e:
            self.hotkey_list.addItem(f"Error loading hotkeys: {e}")
            return

        if isinstance(items, dict):
            items = list(items.items())

        for entry in items:
            if isinstance(entry, tuple) and len(entry) >= 2:
                binary_str, action = entry[0], entry[1]
            elif isinstance(entry, dict):
                binary_str = entry.get("binary") or entry.get("combo") or ""
                action = entry.get("action") or entry.get("func") or ""
            else:
                continue

            item = QListWidgetItem(f"{binary_str}  →  {action}")
            item.setData(Qt.UserRole, (binary_str, action))
            self.hotkey_list.addItem(item)

    def on_add_hotkey_clicked(self) -> None:
        """
        Capture a new hotkey combo and register it for the selected action.
        """
        selected_action = self.hotkey_combo.currentText()

        dialog = PressTwoButtonsAtTheSameTime(self.instance)
        if dialog.exec() == QDialog.Accepted and dialog.binary_string:
            binary_str = dialog.binary_string
            binary_bytes = binary_str.encode("ascii")

            ok, msg = self.hotkey.set_hotkey(binary_bytes, selected_action)
            print("set_hotkey:", ok, msg)

            if ok:
                self.refresh_hotkey_list()
            else:
                print("Failed to set hotkey:", msg)

    def on_delete_hotkey_clicked(self) -> None:
        """
        Delete hotkey(s) for the selected action.

        Behavior:
        - If a specific list row is selected: delete exactly that binary pattern.
        - Otherwise: delete all patterns mapped to the selected action.
        """
        selected_action = self.hotkey_combo.currentText()
        current_item = self.hotkey_list.currentItem()

        if current_item:
            binary_str, action = current_item.data(Qt.UserRole)
            ok, msg = self.hotkey.clear_hotkey(binary_str)
            print("clear_hotkey (single):", ok, msg)
        else:
            try:
                items = self.hotkey.list_hotkeys()
            except Exception as e:
                print("Error listing hotkeys for delete:", e)
                return

            if isinstance(items, dict):
                items = list(items.items())

            for entry in items:
                if isinstance(entry, tuple) and len(entry) >= 2:
                    binary_str, action = entry[0], entry[1]
                elif isinstance(entry, dict):
                    binary_str = entry.get("binary") or entry.get("combo") or ""
                    action = entry.get("action") or entry.get("func") or ""
                else:
                    continue

                if action == selected_action:
                    ok, msg = self.hotkey.clear_hotkey(binary_str)
                    print(f"clear_hotkey ({binary_str} -> {action}):", ok, msg)

        self.refresh_hotkey_list()

    def closeEvent(self, event) -> None:
        """
        Ensure monitoring stops when dialog is closed.
        """
        self.instance.is_monitoring = False
        super().closeEvent(event)


class HotkeyPage(QWidget):
    """
    Page listing emulated controllers, allowing selection of one for hotkey management.

    Hotkeys are shared across all controllers through a common hotkey manager.
    """

    def __init__(self, hotkey):
        super().__init__()

        self.hotkey = hotkey
        self.x360_instances = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel(
            "Choose a controller to define hotkeys on.\n"
            "(Hotkeys will be applied to all controllers.)"
        )
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight:bold; font-size: 12px;")

        self.list_widget = QListWidget()

        layout.addWidget(title)
        layout.addWidget(self.list_widget)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_list)
        self.refresh_timer.start(1000)

        self.list_widget.itemDoubleClicked.connect(self.open_hotkey_dialog)

    def add_x360_instance(self, instance) -> None:
        """
        Register a new emulated controller instance.

        The instance must expose `device_path` to be tracked.
        """
        if hasattr(instance, "device_path"):
            self.x360_instances[instance.device_path] = instance
        self.refresh_list()

    def refresh_list(self) -> None:
        """
        Refresh controller list from `emulator.ListOfAllControllers`.
        """
        self.list_widget.clear()

        with emulator.ListOfAllControllers.lock:
            active_paths = list(emulator.ListOfAllControllers.controllers_path)
            active_names = list(emulator.ListOfAllControllers.controllers_name)

        keys_to_remove = [path for path in self.x360_instances if path not in active_paths]
        for path in keys_to_remove:
            del self.x360_instances[path]

        for i, name in enumerate(active_names):
            item = QListWidgetItem(name)
            if i < len(active_paths):
                item.setData(Qt.UserRole, active_paths[i])
            self.list_widget.addItem(item)

    def open_hotkey_dialog(self, item: QListWidgetItem) -> None:
        """
        Open HotkeyDialog for the double-clicked controller item.
        """
        device_path = item.data(Qt.UserRole)
        if device_path not in self.x360_instances:
            return

        instance = self.x360_instances[device_path]
        dialog = HotkeyDialog(instance, item.text(), self.hotkey)
        dialog.exec()
