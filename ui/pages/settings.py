import os
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QSlider, QFrame, QScrollArea, QFileDialog,
    QSpinBox, QCheckBox, QComboBox, QLineEdit, QMessageBox, QGroupBox,
    QSizePolicy, QSpacerItem, QDoubleSpinBox, QInputDialog, QAbstractSpinBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from ui.i18n import LANGUAGE_NAMES, tr
from ui.animations import AnimatedStackedWidget, AnimatedTabBar
from ui.icons import SMALL_ICON_SIZE, icon
from ui.pages.raw_hid_terminal import RawHidTerminalDialog
from core.dev_logging import configure_developer_logging, resolve_log_path, clear_log_file as clear_developer_log_file


class _WheelSafeSpinBox(QSpinBox):
    """Let the settings scroll area handle the wheel instead of changing values."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class _WheelSafeDoubleSpinBox(QDoubleSpinBox):
    """Prevent accidental numeric changes while scrolling settings."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class _WheelSafeComboBox(QComboBox):
    """Keep wheel scrolling from silently changing the selected option."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class _WheelSafeSlider(QSlider):
    """Allow the parent settings page to consume wheel events."""

    def wheelEvent(self, event) -> None:
        event.ignore()





def _numeric_stepper(control: QAbstractSpinBox) -> QHBoxLayout:
    """Build a compact custom decrement/increment control for a numeric setting."""
    control.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    control.setFixedWidth(112)
    control.setFixedHeight(36)

    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(5)
    row.addWidget(control)

    for glyph, direction, accessible_name in (
        ("minus", -1, "Decrease setting"),
        ("plus", 1, "Increase setting"),
    ):
        button = QPushButton()
        button.setObjectName("settings_stepper_button")
        button.setIcon(icon(glyph))
        button.setIconSize(SMALL_ICON_SIZE)
        button.setFixedSize(32, 32)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setAutoDefault(False)
        button.setDefault(False)
        button.setToolTip(accessible_name)
        button.setAccessibleName(accessible_name)
        button.clicked.connect(
            lambda _checked=False, step=direction: control.setValue(
                control.value() + control.singleStep() * step
            )
        )
        row.addWidget(button)

    row.addStretch(1)
    return row


class SettingsPage(QWidget):
    vibration_enabled_changed = Signal(bool)
    raw_hid_monitor_state_changed = Signal(bool)

    def __init__(self, theme_manager, settings: object, profile_manager=None):
        super().__init__()
        self.setObjectName("settingsPage")
        self.theme_manager = theme_manager
        self.settings = settings
        self.profile_manager = profile_manager
        self._raw_hid_terminal: RawHidTerminalDialog | None = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(350)
        self._autosave_timer.timeout.connect(self._save_current_values)

        # Make sure config is normalized (all keys exist / sane) before we read anything
        if hasattr(self.settings, "normalize"):
            try:
                self.settings.normalize()
            except Exception:
                pass

        root = QVBoxLayout(self)
        self._settings_root_layout = root
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)


        # Compact horizontal sections, with the settings content directly underneath.
        self.menu = AnimatedTabBar()
        self.menu.setObjectName("settings_navigation")
        self.menu.setDocumentMode(True)
        self.menu.setDrawBase(False)
        self.menu.setExpanding(False)
        self.menu.setMovable(False)
        self.menu.setUsesScrollButtons(True)
        self.menu.addTab("Device")
        self.menu.addTab("UI")
        self.menu.addTab("Developer")
        self.menu.setMinimumHeight(36)
        root.addWidget(self.menu)

        self.pages = AnimatedStackedWidget()
        self.pages.setObjectName("settings_pages")
        root.addWidget(self.pages, 1)

        # ==========================================================
        # DEVICE PAGE
        # ==========================================================
        device_page = QWidget()
        device_layout = QVBoxLayout(device_page)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.setSpacing(12)

        header = QLabel("Device Settings")
        header.setObjectName("settings_page_heading")
        header.setAlignment(Qt.AlignLeft)
        device_layout.addWidget(header)
        device_description = QLabel("Customize controller input, mouse behavior, and output preferences.")
        device_description.setObjectName("settings_page_description")
        device_description.setWordWrap(True)
        device_layout.addWidget(device_description)

        device_group = QGroupBox()
        device_form = QFormLayout()
        device_form.setLabelAlignment(Qt.AlignLeft)
        device_form.setFormAlignment(Qt.AlignLeft)
        device_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        device_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        device_form.setHorizontalSpacing(18)
        device_form.setVerticalSpacing(12)
        device_group.setMinimumWidth(0)

        # Input poll interval
        poll_row = QHBoxLayout()
        self.spin_poll = _WheelSafeSpinBox()
        self.spin_poll.setRange(1, 1000)
        poll_row.addLayout(_numeric_stepper(self.spin_poll))
        poll_row.addStretch()
        device_form.addRow("Input poll interval (ms)", poll_row)

        # Checkboxes
        self.chk_reconnect = QCheckBox("Auto reconnect")
        device_form.addRow(self.chk_reconnect)

        self.chk_dpad_mouse = QCheckBox("D-Pad as mouse")
        device_form.addRow(self.chk_dpad_mouse)

        self.chk_mouse_mode = QCheckBox("Mouse mode")
        device_form.addRow(self.chk_mouse_mode)

        self.chk_vibration = QCheckBox("Enable controller vibration")
        self.chk_vibration.setToolTip(
            "Apply Xbox/XInput vibration to connected DualSense controllers immediately."
        )
        device_form.addRow(self.chk_vibration)

        # Mouse sensitivity
        sens_row = QHBoxLayout()
        self.spin_mouse_sens = _WheelSafeDoubleSpinBox()
        self.spin_mouse_sens.setRange(0.1, 10.0)
        self.spin_mouse_sens.setSingleStep(0.1)
        self.spin_mouse_sens.setDecimals(2)
        sens_row.addLayout(_numeric_stepper(self.spin_mouse_sens))
        sens_row.addStretch()
        device_form.addRow("Mouse sensitivity", sens_row)

        mouse_deadzone_row = QHBoxLayout()
        self.mouse_deadzone_slider = _WheelSafeSlider(Qt.Orientation.Horizontal)
        self.mouse_deadzone_slider.setRange(0, 500)
        self.mouse_deadzone_slider.setSingleStep(5)
        self.mouse_deadzone_slider.setPageStep(25)
        self.mouse_deadzone_slider.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.mouse_deadzone_value = QLabel("10.0%")
        self.mouse_deadzone_value.setMinimumWidth(52)
        self.mouse_deadzone_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        mouse_deadzone_row.addWidget(self.mouse_deadzone_slider, 1)
        mouse_deadzone_row.addWidget(self.mouse_deadzone_value)
        device_form.addRow("Mouse deadzone", mouse_deadzone_row)

        # Deadzones
        deadzone_layout = QGridLayout()
        deadzone_layout.setHorizontalSpacing(12)
        deadzone_layout.setVerticalSpacing(10)

        lbl_left = QLabel("Left joystick deadzone")
        self.left_slider = _WheelSafeSlider(Qt.Horizontal)
        self.left_slider.setRange(0, 1000)
        self.left_slider.setSingleStep(1)
        self.left_slider.setPageStep(10)
        self.left_val = QLabel()
        self.left_val.setFixedWidth(50)
        self.left_val.setAlignment(Qt.AlignRight)
        deadzone_layout.addWidget(lbl_left, 0, 0)
        deadzone_layout.addWidget(self.left_slider, 0, 1)
        deadzone_layout.addWidget(self.left_val, 0, 2)

        lbl_right = QLabel("Right joystick deadzone")
        self.right_slider = _WheelSafeSlider(Qt.Horizontal)
        self.right_slider.setRange(0, 1000)
        self.right_slider.setSingleStep(1)
        self.right_slider.setPageStep(10)
        self.right_val = QLabel()
        self.right_val.setFixedWidth(50)
        self.right_val.setAlignment(Qt.AlignRight)
        deadzone_layout.addWidget(lbl_right, 1, 0)
        deadzone_layout.addWidget(self.right_slider, 1, 1)
        deadzone_layout.addWidget(self.right_val, 1, 2)

        deadzone_container = QWidget()
        deadzone_container.setLayout(deadzone_layout)
        device_form.addRow(deadzone_container)

        # Axis inversion group
        inv_group = QGroupBox("Axis inversion")
        inv_layout = QGridLayout()
        inv_layout.setHorizontalSpacing(18)
        inv_layout.setVerticalSpacing(8)

        left_label = QLabel("Left")
        left_label.setAlignment(Qt.AlignCenter)
        right_label = QLabel("Right")
        right_label.setAlignment(Qt.AlignCenter)

        inv_layout.addWidget(QLabel(""), 0, 0)
        inv_layout.addWidget(left_label, 0, 1)
        inv_layout.addWidget(right_label, 0, 2)

        inv_layout.addWidget(QLabel("Invert X joystick"), 1, 0)
        self.chk_left_invert_x = QCheckBox()
        self.chk_right_invert_x = QCheckBox()
        inv_layout.addWidget(self.chk_left_invert_x, 1, 1, alignment=Qt.AlignCenter)
        inv_layout.addWidget(self.chk_right_invert_x, 1, 2, alignment=Qt.AlignCenter)

        inv_layout.addWidget(QLabel("Invert Y joystick"), 2, 0)
        self.chk_left_invert_y = QCheckBox()
        self.chk_right_invert_y = QCheckBox()
        inv_layout.addWidget(self.chk_left_invert_y, 2, 1, alignment=Qt.AlignCenter)
        inv_layout.addWidget(self.chk_right_invert_y, 2, 2, alignment=Qt.AlignCenter)

        self.chk_button_invert = QCheckBox()
        inv_layout.addWidget(self.chk_button_invert, 3, 1, alignment=Qt.AlignCenter)
        inv_layout.addWidget(QLabel("Invert buttons"), 3, 0)

        inv_group.setLayout(inv_layout)
        device_form.addRow(inv_group)

        device_group.setLayout(device_form)
        device_layout.addWidget(device_group)

        # Device bottom buttons
        device_buttons = QHBoxLayout()
        device_buttons.addItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.dev_restore = QPushButton("Reset")
        self.dev_restore.setObjectName("secondary")
        self.dev_restore.setProperty("class", "secondary")
        self.dev_restore.setFixedWidth(140)
        self.dev_apply = QPushButton("Apply Now")
        self.dev_apply.setObjectName("primary")
        self.dev_apply.setFixedWidth(110)
        device_buttons.addWidget(self.dev_restore)
        device_buttons.addWidget(self.dev_apply)
        device_layout.addLayout(device_buttons)

        self.pages.addWidget(self._make_scrollable_page(device_page))

        # ==========================================================
        # UI PAGE
        # ==========================================================
        ui_page = QWidget()
        ui_layout = QVBoxLayout(ui_page)
        ui_layout.setContentsMargins(0, 0, 0, 0)
        ui_layout.setSpacing(12)

        header_ui = QLabel("UI Settings")
        header_ui.setObjectName("settings_page_heading")
        header_ui.setAlignment(Qt.AlignLeft)
        ui_layout.addWidget(header_ui)
        ui_description = QLabel("Personalize appearance and accessibility.")
        ui_description.setObjectName("settings_page_description")
        ui_description.setWordWrap(True)
        ui_layout.addWidget(ui_description)

        ui_group = QGroupBox()
        ui_form = QFormLayout()
        ui_form.setLabelAlignment(Qt.AlignLeft)
        ui_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        ui_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        ui_form.setHorizontalSpacing(18)
        ui_form.setVerticalSpacing(12)
        ui_group.setMinimumWidth(0)

        self.combo_lang = _WheelSafeComboBox()
        for code, name in LANGUAGE_NAMES.items():
            self.combo_lang.addItem(name, code)
        self.combo_lang.setMinimumWidth(120)
        self.combo_lang.view().setMinimumWidth(140)
        ui_form.addRow("Language", self.combo_lang)

        self.combo_theme = _WheelSafeComboBox()
        self.combo_theme.setMinimumWidth(120)
        self.combo_theme.view().setMinimumWidth(140)

        theme_names = []
        try:
            base = getattr(self.theme_manager, "base_path", None)
            if base and os.path.isdir(base):
                for f in os.listdir(base):
                    if f.endswith(".qss"):
                        theme_names.append(os.path.splitext(f)[0])
        except Exception:
            theme_names = []
        if not theme_names:
            theme_names = ["dark", "light"]
        self.combo_theme.addItems(theme_names)
        ui_form.addRow("Theme", self.combo_theme)

        self.chk_reduced_motion = QCheckBox("Reduce interface animations")
        self.chk_reduced_motion.setToolTip(
            "Disable decorative page transitions and animated tab indicators. "
            "Controller input and other functionality are unchanged."
        )
        ui_form.addRow(self.chk_reduced_motion)

        ui_group.setLayout(ui_form)
        ui_layout.addWidget(ui_group)

        ui_buttons = QHBoxLayout()
        ui_buttons.addItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.ui_restore = QPushButton("Reset")
        self.ui_restore.setObjectName("secondary")
        self.ui_restore.setFixedWidth(140)
        self.ui_apply = QPushButton("Apply Now")
        self.ui_apply.setObjectName("primary")
        self.ui_apply.setFixedWidth(110)
        ui_buttons.addWidget(self.ui_restore)
        ui_buttons.addWidget(self.ui_apply)
        ui_layout.addLayout(ui_buttons)

        self.pages.addWidget(self._make_scrollable_page(ui_page))

        # ==========================================================
        # DEVELOPER PAGE
        # ==========================================================
        dev_page = QWidget()
        dev_layout = QVBoxLayout(dev_page)
        dev_layout.setContentsMargins(0, 0, 0, 0)
        dev_layout.setSpacing(12)

        header_dev = QLabel("Developer Settings")
        header_dev.setObjectName("settings_page_heading")
        header_dev.setAlignment(Qt.AlignLeft)
        dev_layout.addWidget(header_dev)
        dev_description = QLabel("Diagnostics, raw controller reports, and rotating logs for troubleshooting.")
        dev_description.setObjectName("settings_page_description")
        dev_description.setWordWrap(True)
        dev_layout.addWidget(dev_description)

        dev_group = QGroupBox()
        dev_form = QFormLayout()
        dev_form.setLabelAlignment(Qt.AlignLeft)
        dev_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        dev_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        dev_form.setHorizontalSpacing(18)
        dev_form.setVerticalSpacing(12)
        dev_group.setMinimumWidth(0)

        self.chk_debug = QCheckBox("Debug")
        dev_form.addRow(self.chk_debug)

        raw_hid_row = QHBoxLayout()
        raw_hid_row.setSpacing(10)
        self.chk_raw_hid = QCheckBox("Raw HID debug")
        self.chk_raw_hid.setToolTip(
            "Stream live raw HID packets to the terminal and include rate-limited samples in diagnostic logs."
        )
        raw_hid_row.addWidget(self.chk_raw_hid)
        raw_hid_row.addStretch(1)
        self.btn_raw_hid_terminal = QPushButton("Open live terminal")
        self.btn_raw_hid_terminal.setObjectName("settings_secondary")
        self.btn_raw_hid_terminal.setMinimumWidth(150)
        self.btn_raw_hid_terminal.setToolTip(
            "Open a live, timestamped hex view of raw HID reports from connected physical controllers."
        )
        raw_hid_row.addWidget(self.btn_raw_hid_terminal)
        dev_form.addRow(raw_hid_row)

        self.chk_log_to_file = QCheckBox("Log to file")
        dev_form.addRow(self.chk_log_to_file)

        log_row = QHBoxLayout()
        lbl_path = QLabel("Log file path")
        self.edit_log_path = QLineEdit()
        self.edit_log_path.setMinimumWidth(0)
        self.edit_log_path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.edit_log_path.setPlaceholderText("logs/mapper.log")
        log_row.addWidget(self.edit_log_path, 1)
        self.btn_browse_log = QPushButton("Browse…")
        self.btn_browse_log.setObjectName("settings_secondary")
        log_row.addWidget(self.btn_browse_log)
        dev_form.addRow(lbl_path, log_row)

        self.lbl_logging_status = QLabel()
        self.lbl_logging_status.setObjectName("settings_logging_status")
        self.lbl_logging_status.setWordWrap(True)
        dev_form.addRow("", self.lbl_logging_status)

        dev_group.setLayout(dev_form)
        dev_layout.addWidget(dev_group)

        log_actions = QHBoxLayout()
        log_actions.setSpacing(8)
        self.btn_open_log = QPushButton("Open log file")
        self.btn_open_log.setObjectName("settings_secondary")
        self.btn_open_log.setToolTip("Open the current diagnostic log in the default text editor.")
        log_actions.addWidget(self.btn_open_log)
        self.btn_open_log_folder = QPushButton("Open log folder")
        self.btn_open_log_folder.setObjectName("settings_secondary")
        self.btn_open_log_folder.setToolTip("Open the directory containing the configured log file.")
        log_actions.addWidget(self.btn_open_log_folder)
        self.btn_clear_log = QPushButton("Clear logs")
        self.btn_clear_log.setObjectName("settings_secondary")
        self.btn_clear_log.setToolTip("Clear the current log and its rotated backups.")
        log_actions.addWidget(self.btn_clear_log)
        log_actions.addStretch(1)
        dev_layout.addLayout(log_actions)

        dev_buttons = QHBoxLayout()
        dev_buttons.addItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.dev_restore2 = QPushButton("Reset")
        self.dev_restore2.setObjectName("secondary")
        self.dev_restore2.setFixedWidth(140)
        self.dev_apply2 = QPushButton("Apply Now")
        self.dev_apply2.setObjectName("primary")
        self.dev_apply2.setFixedWidth(110)
        dev_buttons.addWidget(self.dev_restore2)
        dev_buttons.addWidget(self.dev_apply2)
        dev_layout.addLayout(dev_buttons)

        self.pages.addWidget(self._make_scrollable_page(dev_page))

        # ==========================================================
        # SHARED BOTTOM BAR – Save to Profile
        # ==========================================================
        separator = QFrame()
        self._settings_separator = separator
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("QFrame { color: #444455; margin: 4px 0; }")
        root.addWidget(separator)

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 6, 0, 0)
        bottom_bar.setSpacing(8)

        self.lbl_profile_status = QLabel("")
        self.lbl_profile_status.setProperty("_i18n_dynamic", True)
        self.lbl_profile_status.setStyleSheet("font-size:12px; color:#888899;")
        bottom_bar.addWidget(self.lbl_profile_status)
        self.lbl_autosave_status = QLabel("Auto-save is on")
        self.lbl_autosave_status.setProperty("_i18n_dynamic", True)
        self.lbl_autosave_status.setObjectName("settings_autosave_status")
        bottom_bar.addWidget(self.lbl_autosave_status)
        bottom_bar.addStretch()

        self.btn_save_to_profile = QPushButton("  Save Settings to Profile  ")
        self.btn_save_to_profile.setObjectName("settings_save_profile")
        self.btn_save_to_profile.setProperty("class", "primary")
        self.btn_save_to_profile.setMinimumWidth(0)
        self.btn_save_to_profile.setFixedHeight(36)
        bottom_bar.addWidget(self.btn_save_to_profile)

        root.addLayout(bottom_bar)

        # ==========================================================
        # MENU → STACK CONNECTION
        # ==========================================================
        self.menu.currentChanged.connect(self.pages.setCurrentIndex)

        # ==========================================================
        # INITIAL LOAD FROM SETTINGS
        # ==========================================================
        try:
            polling = int(self.settings.get_poll_interval_ms())
        except Exception:
            polling = 1
        self.spin_poll.setRange(1, 1000)
        self.spin_poll.setValue(polling)

        try:
            self.chk_reconnect.setChecked(self.settings.get_auto_reconnect())
        except Exception:
            self.chk_reconnect.setChecked(False)

        try:
            self.chk_dpad_mouse.setChecked(self.settings.get_dpad_as_mouse())
        except Exception:
            self.chk_dpad_mouse.setChecked(True)

        try:
            self.chk_mouse_mode.setChecked(self.settings.get_mouse_mode())
        except Exception:
            self.chk_mouse_mode.setChecked(False)

        try:
            self.chk_vibration.setChecked(self.settings.get_vibration_enabled())
        except Exception:
            self.chk_vibration.setChecked(True)

        try:
            self.spin_mouse_sens.setValue(self.settings.get_mouse_sensitivity())
        except Exception:
            self.spin_mouse_sens.setValue(1.0)
        try:
            mouse_deadzone = self.settings.get_mouse_deadzone()
        except Exception:
            mouse_deadzone = 0.10
        self.mouse_deadzone_slider.setValue(int(round(mouse_deadzone * 1000)))
        self.mouse_deadzone_value.setText(f"{mouse_deadzone * 100:.1f}%")

        try:
            left_dz, right_dz = self.settings.get_deadzones()
        except Exception:
            left_dz, right_dz = 0.1, 0.1

        self.left_slider.setValue(int(left_dz * 1000))
        self.right_slider.setValue(int(right_dz * 1000))
        self.left_val.setText(f"{left_dz:.2f}")
        self.right_val.setText(f"{right_dz:.2f}")

        try:
            left_inv, right_inv = self.settings.get_joystick_invertion()
        except Exception:
            left_inv, right_inv = (False, False), (False, False)

        self.chk_left_invert_x.setChecked(bool(left_inv[0]))
        self.chk_left_invert_y.setChecked(bool(left_inv[1]))
        self.chk_right_invert_x.setChecked(bool(right_inv[0]))
        self.chk_right_invert_y.setChecked(bool(right_inv[1]))

        try:
            self.chk_button_invert.setChecked(self.settings.get_button_invertion())
        except Exception:
            self.chk_button_invert.setChecked(False)

        try:
            lang = self.settings.get_ui_language()
        except Exception:
            lang = "eng"
        language_codes = [
            self.combo_lang.itemData(i) for i in range(self.combo_lang.count())
        ]
        if lang not in language_codes:
            lang = "eng"
        self.combo_lang.setCurrentIndex(language_codes.index(lang))

        try:
            current_theme = self.settings.get_ui_theme()
        except Exception:
            current_theme = "dark"
        if current_theme in [self.combo_theme.itemText(i) for i in range(self.combo_theme.count())]:
            self.combo_theme.setCurrentText(current_theme)
        try:
            self.chk_reduced_motion.setChecked(self.settings.get_ui_reduced_motion())
        except Exception:
            self.chk_reduced_motion.setChecked(False)

        try:
            dbg = self.settings.get_developer_debug()
        except Exception:
            dbg = False
        self.chk_debug.setChecked(dbg)

        try:
            raw_hid = self.settings.get_raw_hid_debug()
        except Exception:
            raw_hid = False
        self.chk_raw_hid.setChecked(raw_hid)

        try:
            log_to_file = self.settings.get_log_to_file()
        except Exception:
            log_to_file = False
        self.chk_log_to_file.setChecked(log_to_file)

        try:
            log_path = self.settings.get_log_file_path()
        except Exception:
            log_path = "logs/mapper.log"
        self.edit_log_path.setText(log_path)

        # Apply theme from settings
        try:
            if hasattr(self.theme_manager, "apply_theme"):
                self.theme_manager.apply_theme(self.settings.get_ui_theme())
        except Exception:
            pass

        # Update active profile label
        self._update_profile_label()

        # ==========================================================
        # SIGNALS
        # ==========================================================
        self.mouse_deadzone_slider.valueChanged.connect(
            lambda v: (
                self.mouse_deadzone_value.setText(f"{v / 10:.1f}%"),
                self._schedule_autosave(),
            )
        )
        self.left_slider.valueChanged.connect(
            lambda v: (self.left_val.setText(f"{v/1000:.2f}"), self._schedule_autosave())
        )
        self.right_slider.valueChanged.connect(
            lambda v: (self.right_val.setText(f"{v/1000:.2f}"), self._schedule_autosave())
        )

        # Settings are persisted automatically whenever a control changes.
        for widget, signal_name in (
            (self.spin_poll, "valueChanged"),
            (self.chk_reconnect, "toggled"),
            (self.chk_dpad_mouse, "toggled"),
            (self.chk_mouse_mode, "toggled"),
            (self.chk_vibration, "toggled"),
            (self.spin_mouse_sens, "valueChanged"),
            (self.chk_left_invert_x, "toggled"),
            (self.chk_left_invert_y, "toggled"),
            (self.chk_right_invert_x, "toggled"),
            (self.chk_right_invert_y, "toggled"),
            (self.chk_button_invert, "toggled"),
            (self.combo_lang, "currentTextChanged"),
            (self.combo_theme, "currentTextChanged"),
            (self.chk_reduced_motion, "toggled"),
            (self.chk_debug, "toggled"),
            (self.chk_raw_hid, "toggled"),
            (self.chk_log_to_file, "toggled"),
            (self.edit_log_path, "textChanged"),
        ):
            getattr(getattr(widget, signal_name), "connect")(self._schedule_autosave)

        self.chk_vibration.toggled.connect(self._on_vibration_toggled)

        self.dev_restore.clicked.connect(self.restore_device_defaults)
        self.dev_apply.clicked.connect(self.apply_device)

        self.ui_restore.clicked.connect(self.restore_ui_defaults)
        self.ui_apply.clicked.connect(self.apply_ui)

        self.dev_restore2.clicked.connect(self.restore_dev_defaults)
        self.dev_apply2.clicked.connect(self.apply_dev)

        self.btn_raw_hid_terminal.clicked.connect(self._open_raw_hid_terminal)
        self.chk_raw_hid.toggled.connect(self._on_raw_hid_toggled)
        self.btn_browse_log.clicked.connect(self._browse_log_file)
        self.btn_open_log.clicked.connect(self._open_log_file)
        self.btn_open_log_folder.clicked.connect(self._open_log_folder)
        self.btn_clear_log.clicked.connect(self._clear_log_file)
        self._apply_reduced_motion()
        initial_log_path = configure_developer_logging(self.settings)
        self._refresh_logging_status(initial_log_path)

        self.btn_save_to_profile.clicked.connect(self._on_save_to_profile)
        self.apply_theme()

    def apply_theme(self, theme_name: str | None = None) -> None:
        app = QApplication.instance()
        theme = theme_name or (
            app.property("vpadTheme") if app is not None else "dark"
        )
        light = theme == "light"
        muted = "#64758b" if light else "#91a2bc"
        border = "#d1dbe9" if light else "#344762"
        stepper_bg = "rgba(63, 112, 176, 14%)" if light else "rgba(79, 120, 180, 22%)"
        stepper_text = "#31577f" if light else "#dceaff"
        stepper_border = "rgba(77, 125, 185, 45%)" if light else "rgba(133, 193, 255, 34%)"
        stepper_hover = "rgba(65, 129, 203, 23%)" if light else "rgba(79, 145, 220, 42%)"
        stepper_pressed = "rgba(55, 110, 185, 32%)" if light else "rgba(55, 110, 185, 55%)"
        self.setStyleSheet(f"""
            QWidget#settingsPage {{ background:transparent; }}
            QTabBar#settings_navigation {{ background:transparent; border:none; }}
            QTabBar#settings_navigation::tab {{
                padding:9px 16px; margin:0 3px 3px 0;
                border-radius:9px; border:1px solid transparent;
            }}
            QTabBar#settings_navigation::tab:selected {{
                background:rgba(99, 91, 255, {'25' if light else '35'});
                border-color:rgba(99, 91, 255, {'130' if light else '100'});
            }}
            QScrollArea#settings_scroll {{ background:transparent; border:none; }}
            QScrollArea#settings_scroll > QWidget > QWidget {{ background:transparent; }}
            QGroupBox {{ border-radius:12px; margin-top:10px; padding:14px 10px 10px; }}
            QGroupBox::title {{ subcontrol-origin:margin; left:12px; padding:0 5px; }}
            QCheckBox {{ padding:5px 2px; spacing:9px; }}
            QSlider {{ min-height:24px; }}
            QPushButton#settings_stepper_button {{
                color:{stepper_text}; background:{stepper_bg}; border:1px solid {stepper_border};
                border-radius:9px; font-size:17px; font-weight:800; padding:0;
            }}
            QPushButton#settings_stepper_button:hover {{ background:{stepper_hover}; }}
            QPushButton#settings_stepper_button:pressed {{ background:{stepper_pressed}; }}
            QPushButton#settings_primary {{ min-height:36px; padding:7px 15px; border-radius:9px; }}
            QPushButton#settings_secondary {{ min-height:36px; padding:7px 12px; border-radius:9px; }}
            QLabel#settings_page_heading {{ font-size:19px; font-weight:750; padding:5px 0 2px; }}
            QLabel#settings_page_description {{ color:{muted}; font-size:11px; padding-bottom:3px; }}
            QLabel#settings_logging_status {{ color:{muted}; font-size:11px; padding:4px 0; }}
        """)
        self._settings_theme = theme
        self.lbl_profile_status.setStyleSheet(
            f"font-size:12px; color:{muted};"
        )
        self.lbl_autosave_status.setStyleSheet(f"color:{muted};")
        if hasattr(self, "_settings_separator"):
            self._settings_separator.setStyleSheet(
                f"QFrame {{ color:{border}; margin:4px 0; }}"
            )
        if self._raw_hid_terminal is not None:
            self._raw_hid_terminal.apply_theme(theme)


    # ==========================================================
    # PROFILE HELPERS
    # ==========================================================

    def set_profile_manager(self, profile_manager):
        """Set or update the profile manager reference (called after init)."""
        self.profile_manager = profile_manager
        self._update_profile_label()

    def _update_profile_label(self):
        """Refresh the status label showing the active profile name."""
        if self.profile_manager is None:
            self.lbl_profile_status.setText("")
            return
        name = self.profile_manager.get_active_profile_name()
        language = self.settings.get_ui_language()
        if name:
            self.lbl_profile_status.setText(f"{tr('Active profile', language)}: {name}")
        else:
            self.lbl_profile_status.setText(tr("No profile active", language))

    def reload_from_settings(self) -> None:
        """Refresh every control after a profile changes the live settings."""
        self._autosave_timer.stop()
        widgets = [
            self.spin_poll, self.chk_reconnect, self.chk_dpad_mouse,
            self.chk_mouse_mode, self.chk_vibration, self.spin_mouse_sens,
            self.mouse_deadzone_slider, self.left_slider, self.right_slider, self.chk_left_invert_x,
            self.chk_left_invert_y, self.chk_right_invert_x,
            self.chk_right_invert_y, self.chk_button_invert, self.combo_lang,
            self.combo_theme, self.chk_reduced_motion, self.chk_debug, self.chk_raw_hid,
            self.chk_log_to_file, self.edit_log_path,
        ]
        states = [widget.blockSignals(True) for widget in widgets]
        try:
            self.spin_poll.setValue(int(round(self.settings.get_poll_interval_ms())))
            self.chk_reconnect.setChecked(self.settings.get_auto_reconnect())
            self.chk_dpad_mouse.setChecked(self.settings.get_dpad_as_mouse())
            self.chk_mouse_mode.setChecked(self.settings.get_mouse_mode())
            self.chk_vibration.setChecked(self.settings.get_vibration_enabled())
            self.spin_mouse_sens.setValue(self.settings.get_mouse_sensitivity())
            mouse_deadzone = self.settings.get_mouse_deadzone()
            self.mouse_deadzone_slider.setValue(int(round(mouse_deadzone * 1000)))
            self.mouse_deadzone_value.setText(f"{mouse_deadzone * 100:.1f}%")

            left_dz, right_dz = self.settings.get_deadzones()
            self.left_slider.setValue(int(left_dz * 1000))
            self.right_slider.setValue(int(right_dz * 1000))
            self.left_val.setText(f"{left_dz:.2f}")
            self.right_val.setText(f"{right_dz:.2f}")

            left_inv, right_inv = self.settings.get_joystick_invertion()
            self.chk_left_invert_x.setChecked(bool(left_inv[0]))
            self.chk_left_invert_y.setChecked(bool(left_inv[1]))
            self.chk_right_invert_x.setChecked(bool(right_inv[0]))
            self.chk_right_invert_y.setChecked(bool(right_inv[1]))
            self.chk_button_invert.setChecked(self.settings.get_button_invertion())

            language = self.settings.get_ui_language()
            language_codes = [self.combo_lang.itemData(i) for i in range(self.combo_lang.count())]
            if language in language_codes:
                self.combo_lang.setCurrentIndex(language_codes.index(language))
            self.combo_theme.setCurrentText(self.settings.get_ui_theme())
            self.chk_reduced_motion.setChecked(self.settings.get_ui_reduced_motion())
            self.chk_debug.setChecked(self.settings.get_developer_debug())
            self.chk_raw_hid.setChecked(self.settings.get_raw_hid_debug())
            self.chk_log_to_file.setChecked(self.settings.get_log_to_file())
            self.edit_log_path.setText(self.settings.get_log_file_path())
        finally:
            for widget, state in zip(widgets, states):
                widget.blockSignals(state)

        if self._raw_hid_terminal is not None:
            self._raw_hid_terminal.set_capture_enabled(
                self.settings.get_raw_hid_debug()
            )
        self._update_profile_label()
        self._apply_reduced_motion()
        log_path = configure_developer_logging(self.settings)
        self._refresh_logging_status(log_path)
        self.vibration_enabled_changed.emit(self.settings.get_vibration_enabled())

    def _apply_all_current_values(self):
        """
        Push every visible UI control value into the SettingsManager
        (without writing to disk — the caller decides when to save).
        """
        # Device
        self.settings.set_poll_interval_ms(self.spin_poll.value())
        self.settings.set_auto_reconnect(self.chk_reconnect.isChecked())
        self.settings.set_dpad_as_mouse(self.chk_dpad_mouse.isChecked())
        self.settings.set_mouse_mode(self.chk_mouse_mode.isChecked())
        self.settings.set_vibration_enabled(self.chk_vibration.isChecked())
        self.settings.set_mouse_sensitivity(self.spin_mouse_sens.value())
        self.settings.set_mouse_deadzone(self.mouse_deadzone_slider.value() / 1000.0)

        left = self.left_slider.value() / 1000.0
        right = self.right_slider.value() / 1000.0
        self.settings.set_deadzones(left, right)

        left_inv = (self.chk_left_invert_x.isChecked(), self.chk_left_invert_y.isChecked())
        right_inv = (self.chk_right_invert_x.isChecked(), self.chk_right_invert_y.isChecked())
        self.settings.set_joystick_invertion(left_inv, right_inv)
        self.settings.set_button_invertion(self.chk_button_invert.isChecked())

        # UI
        self.settings.set_ui_language(self.combo_lang.currentData() or "eng")
        self.settings.set_ui_theme(self.combo_theme.currentText())
        self.settings.set_ui_reduced_motion(self.chk_reduced_motion.isChecked())

        # Developer
        self.settings.set_developer_debug(self.chk_debug.isChecked())
        self.settings.set_raw_hid_debug(self.chk_raw_hid.isChecked())
        self.settings.set_log_to_file(self.chk_log_to_file.isChecked())
        self.settings.set_log_file_path(self.edit_log_path.text() or "logs/mapper.log")

    def _schedule_autosave(self, *_args) -> None:
        """Debounce writes while keeping settings persistently up to date."""
        self._autosave_timer.start()

    def _on_vibration_toggled(self, enabled: bool) -> None:
        """Apply the change to active controllers without a restart."""
        self.settings.set_vibration_enabled(enabled)
        self.vibration_enabled_changed.emit(bool(enabled))

    def _save_current_values(self) -> None:
        """Write the current controls to disk and refresh the save indicator."""
        self._apply_all_current_values()
        self.settings.save()
        log_path = configure_developer_logging(self.settings)
        self._apply_reduced_motion()
        self._refresh_logging_status(log_path)
        self.lbl_autosave_status.setText(
            tr("✓ Auto-saved", self.settings.get_ui_language())
        )
        if self.combo_theme.currentText() != getattr(
            self.theme_manager, "current_theme", ""
        ):
            try:
                self.theme_manager.apply_theme(self.combo_theme.currentText())
            except Exception:
                pass

    def _on_save_to_profile(self):
        """Apply current UI values, then let the user pick or create a profile to save to."""
        if self.profile_manager is None:
            QMessageBox.information(
                self,
                "Profiles Not Available",
                "Profile manager is not initialized.",
            )
            return

        # Build choice list: existing profiles + "Create new…"
        profiles = self.profile_manager.list_profiles()
        active = self.profile_manager.get_active_profile_name()
        items = [p.get("name", "Unknown") for p in profiles]

        # Ask user what to do
        from PySide6.QtWidgets import QMenu, QPushButton

        # Show a context-menu style picker anchored to the button
        menu = QMenu(self)
        menu.setObjectName("settings_profile_menu")

        if items:
            for name in items:
                label = f"  {name}  (overwrite)" if name == active else f"  {name}"
                action = menu.addAction(label)
                action.setData(name)
            menu.addSeparator()

        new_action = menu.addAction("  ＋ Save as new profile…")
        new_action.setData("__new__")

        chosen = menu.exec(self.btn_save_to_profile.mapToGlobal(
            self.btn_save_to_profile.rect().bottomLeft()
        ))

        if chosen is None:
            return

        target = chosen.data()

        if target == "__new__":
            name, ok = QInputDialog.getText(
                self,
                "New Profile",
                "Profile name:",
                QLineEdit.Normal,
            )
            if not ok or not name.strip():
                return
            name = name.strip()

            if self.profile_manager.get_profile(name) is not None:
                reply = QMessageBox.question(
                    self,
                    "Overwrite Profile?",
                    f'A profile named "{name}" already exists.\nOverwrite it?',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return

            self._apply_all_current_values()
            existing = self.profile_manager.get_profile(name)
            description = existing.get("_meta", {}).get("description", "") if existing else ""
            if self.profile_manager.save_profile(name, description=description, overwrite=True):
                self.profile_manager.activate_profile(name)
                self._update_profile_label()
                QMessageBox.information(
                    self,
                    "Profile Saved",
                    f'Settings saved to profile "{name}".',
                )
            else:
                QMessageBox.critical(
                    self, "Error", f'Failed to save profile "{name}".'
                )
        else:
            # Overwrite existing
            self._apply_all_current_values()
            existing = self.profile_manager.get_profile(target)
            description = existing.get("_meta", {}).get("description", "") if existing else ""
            if self.profile_manager.save_profile(target, description=description, overwrite=True):
                self.profile_manager.activate_profile(target)
                self._update_profile_label()
                QMessageBox.information(
                    self,
                    "Profile Updated",
                    f'Settings saved to profile "{target}".',
                )
            else:
                QMessageBox.critical(
                    self, "Error", f'Failed to update profile "{target}".'
                )

    # ==========================================================
    # DEVICE ACTIONS
    # ==========================================================
    def restore_device_defaults(self):
        self.spin_poll.setValue(1)
        self.chk_reconnect.setChecked(True)
        self.chk_dpad_mouse.setChecked(True)
        self.chk_mouse_mode.setChecked(False)
        self.chk_vibration.setChecked(True)
        self.spin_mouse_sens.setValue(1.0)
        self.mouse_deadzone_slider.setValue(100)
        self.mouse_deadzone_value.setText("10.0%")
        self.left_slider.setValue(100)
        self.right_slider.setValue(100)
        self.left_val.setText("0.10")
        self.right_val.setText("0.10")
        self.chk_left_invert_x.setChecked(False)
        self.chk_left_invert_y.setChecked(False)
        self.chk_right_invert_x.setChecked(False)
        self.chk_right_invert_y.setChecked(False)
        self.chk_button_invert.setChecked(False)
        self._save_current_values()

    def apply_device(self):
        old_polling = self.settings.get_poll_interval_ms()
        polling = self.spin_poll.value()
        self.settings.set_poll_interval_ms(polling)
        self.settings.set_auto_reconnect(self.chk_reconnect.isChecked())
        self.settings.set_dpad_as_mouse(self.chk_dpad_mouse.isChecked())
        self.settings.set_mouse_mode(self.chk_mouse_mode.isChecked())
        self.settings.set_vibration_enabled(self.chk_vibration.isChecked())
        self.settings.set_mouse_sensitivity(self.spin_mouse_sens.value())
        self.settings.set_mouse_deadzone(self.mouse_deadzone_slider.value() / 1000.0)

        left = self.left_slider.value() / 1000.0
        right = self.right_slider.value() / 1000.0
        self.settings.set_deadzones(left, right)

        left_inv = (self.chk_left_invert_x.isChecked(), self.chk_left_invert_y.isChecked())
        right_inv = (self.chk_right_invert_x.isChecked(), self.chk_right_invert_y.isChecked())
        self.settings.set_joystick_invertion(left_inv, right_inv)

        self.settings.set_button_invertion(self.chk_button_invert.isChecked())
        self.vibration_enabled_changed.emit(self.chk_vibration.isChecked())

        self.settings.save()

        if polling != old_polling:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Restart Required")
            msg.setText(
                "Input poll interval has changed. Please restart the application for the changes to take effect."
            )
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()

    # ==========================================================
    # UI ACTIONS
    # ==========================================================
    def restore_ui_defaults(self):
        language_codes = [
            self.combo_lang.itemData(i) for i in range(self.combo_lang.count())
        ]
        if "eng" in language_codes:
            self.combo_lang.setCurrentIndex(language_codes.index("eng"))
        self.chk_reduced_motion.setChecked(False)
        if "dark" in [self.combo_theme.itemText(i) for i in range(self.combo_theme.count())]:
            self.combo_theme.setCurrentText("dark")
        else:
            if self.combo_theme.count() > 0:
                self.combo_theme.setCurrentIndex(0)
        self._save_current_values()

    def apply_ui(self):
        self.settings.set_ui_language(self.combo_lang.currentData() or "eng")
        theme = self.combo_theme.currentText()
        self.settings.set_ui_theme(theme)
        self.settings.set_ui_reduced_motion(self.chk_reduced_motion.isChecked())
        self.settings.save()
        self._apply_reduced_motion()
        try:
            if hasattr(self.theme_manager, "apply_theme"):
                self.theme_manager.apply_theme(theme)
        except Exception:
            pass

    # ==========================================================
    # DEVELOPER ACTIONS
    # ==========================================================
    def _open_raw_hid_terminal(self) -> None:
        """Open the live monitor and ensure raw capture is enabled first."""
        if not self.chk_raw_hid.isChecked():
            self.chk_raw_hid.setChecked(True)
        self._autosave_timer.stop()
        self._save_current_values()

        if self._raw_hid_terminal is None:
            self._raw_hid_terminal = RawHidTerminalDialog(
                language=self.settings.get_ui_language(),
                parent=self,
            )
            self._raw_hid_terminal.visibility_changed.connect(
                self.raw_hid_monitor_state_changed.emit
            )
        self._raw_hid_terminal.set_capture_enabled(self.chk_raw_hid.isChecked())
        self._raw_hid_terminal.show()
        self._raw_hid_terminal.raise_()
        self._raw_hid_terminal.activateWindow()

    def _on_raw_hid_toggled(self, enabled: bool) -> None:
        terminal = self._raw_hid_terminal
        if terminal is not None:
            terminal.set_capture_enabled(enabled)

    @Slot(str, bytes)
    def append_raw_hid_report(self, controller_name: str, report: bytes) -> None:
        """Receive HID reports queued onto the GUI thread and forward only to a visible terminal."""
        terminal = self._raw_hid_terminal
        if (
            terminal is None
            or not terminal.isVisible()
            or not self.chk_raw_hid.isChecked()
        ):
            return
        terminal.append_report(controller_name, report)

    def restore_dev_defaults(self):
        self.chk_debug.setChecked(False)
        self.chk_raw_hid.setChecked(False)
        self.chk_log_to_file.setChecked(False)
        self.edit_log_path.setText("logs/mapper.log")
        self._save_current_values()

    def apply_dev(self):
        self._apply_all_current_values()
        self.settings.save()
        log_path = configure_developer_logging(self.settings)
        self._refresh_logging_status(log_path)

    def _browse_log_file(self) -> None:
        current = str(resolve_log_path(self.settings))
        if self.edit_log_path.text().strip():
            try:
                from core.utils.paths import resolve_data_path
                current = str(resolve_data_path(self.edit_log_path.text().strip()))
            except (TypeError, ValueError):
                pass
        filename, _ = QFileDialog.getSaveFileName(
            self, "Choose diagnostic log file", current,
            "Log files (*.log *.txt);;All files (*)",
        )
        if filename:
            self.edit_log_path.setText(filename)
            self._schedule_autosave()

    def _open_log_file(self) -> None:
        self._apply_all_current_values()
        self.settings.save()
        configure_developer_logging(self.settings)
        path = resolve_log_path(self.settings)
        if not path.exists():
            QMessageBox.information(
                self, "Log file not created yet",
                "Enable 'Log to file' and generate a diagnostic message first. "
                "The file is created automatically when the first log entry is written.",
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, "Could not open log file", f"Open this file manually:\n{path}")

    def _open_log_folder(self) -> None:
        self._apply_all_current_values()
        self.settings.save()
        configure_developer_logging(self.settings)
        path = resolve_log_path(self.settings)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Could not open log folder", str(exc))
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))):
            QMessageBox.warning(self, "Could not open log folder", str(path.parent))

    def _clear_log_file(self) -> None:
        self._apply_all_current_values()
        self.settings.save()
        configure_developer_logging(self.settings)
        path = resolve_log_path(self.settings)
        answer = QMessageBox.question(
            self, "Clear diagnostic logs?",
            f"Clear the current log and its rotated backups?\n\n{path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if clear_developer_log_file(self.settings):
            self.lbl_logging_status.setText(tr("Diagnostic logs cleared.", self.settings.get_ui_language()))
        else:
            QMessageBox.warning(
                self, "Could not clear logs",
                f"Close any application that may be using this file, then try again:\n{path}",
            )

    def _refresh_logging_status(self, active_path: Path | None = None) -> None:
        language = self.settings.get_ui_language()
        if active_path is None and self.settings.get_log_to_file():
            active_path = configure_developer_logging(self.settings)
        if self.settings.get_log_to_file() and active_path is not None:
            title = tr("File logging enabled · rotating at 2 MiB, keeping 3 backups", language)
            self.lbl_logging_status.setText(f"{title}\n{active_path}")
        elif self.settings.get_log_to_file():
            self.lbl_logging_status.setText(tr(
                "Could not activate file logging. Check that the selected folder exists and is writable.",
                language,
            ))
        elif self.settings.get_developer_debug() or self.settings.get_raw_hid_debug():
            self.lbl_logging_status.setText(tr(
                "Detailed diagnostics are enabled. Turn on Log to file to retain them after closing the app.",
                language,
            ))
        else:
            self.lbl_logging_status.setText(tr(
                "File logging is off. Enable it to save diagnostic logs to disk.", language
            ))

    def _apply_reduced_motion(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setProperty("reducedMotion", bool(self.chk_reduced_motion.isChecked()))

    @staticmethod
    def _make_scrollable_page(page: QWidget) -> QScrollArea:
        page.setMinimumWidth(0)
        scroll = QScrollArea()
        scroll.setObjectName("settings_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.width() < 980:
            self._settings_root_layout.setContentsMargins(10, 8, 10, 8)
            self._settings_root_layout.setSpacing(5)
            self.menu.setMinimumHeight(34)
        else:
            self._settings_root_layout.setContentsMargins(16, 12, 16, 12)
            self._settings_root_layout.setSpacing(8)
            self.menu.setMinimumHeight(36)
