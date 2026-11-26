"""Editor for per-controller physical button output layouts."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.input_layout import (
    is_valid_keyboard_key,
    load_controller_profile,
    normalize_controller_layout,
)
from ui.i18n import tr


_SOURCE_LABELS = {
    "cross": "Cross / A",
    "circle": "Circle / B",
    "square": "Square / X",
    "triangle": "Triangle / Y",
    "l1": "L1",
    "r1": "R1",
    "share": "Share / Back",
    "option": "Options / Start",
    "l3": "Left Stick Click",
    "r3": "Right Stick Click",
    "dpad_up": "D-Pad Up",
    "dpad_down": "D-Pad Down",
    "dpad_left": "D-Pad Left",
    "dpad_right": "D-Pad Right",
}

_OUTPUT_OPTIONS = [
    ("Unmapped", "disabled"),
    ("Xbox 360 A", "x360:a"),
    ("Xbox 360 B", "x360:b"),
    ("Xbox 360 X", "x360:x"),
    ("Xbox 360 Y", "x360:y"),
    ("Xbox 360 LB", "x360:lb"),
    ("Xbox 360 RB", "x360:rb"),
    ("Xbox 360 Back", "x360:back"),
    ("Xbox 360 Start", "x360:start"),
    ("Xbox 360 L3", "x360:l3"),
    ("Xbox 360 R3", "x360:r3"),
    ("Xbox 360 D-Pad Up", "x360:dpad_up"),
    ("Xbox 360 D-Pad Down", "x360:dpad_down"),
    ("Xbox 360 D-Pad Left", "x360:dpad_left"),
    ("Xbox 360 D-Pad Right", "x360:dpad_right"),
    ("Keyboard key", "keyboard"),
    ("Mouse Left", "mouse:left"),
    ("Mouse Right", "mouse:right"),
    ("Mouse Middle", "mouse:middle"),
]


class ControllerLayoutDialog(QDialog):
    """Edit digital control routes and switch polarity for a single controller."""

    def __init__(
        self,
        controller_name: str,
        controller_type: str,
        current_layout: dict | None = None,
        language: str = "eng",
        parent=None,
    ):
        super().__init__(parent)
        self._language = language
        self._profile = load_controller_profile(controller_type)
        self._layout = normalize_controller_layout(current_layout, self._profile)
        self._rows: dict[str, tuple[QComboBox, QLineEdit, QComboBox]] = {}

        self.setWindowTitle(tr("Edit Controller Layout", language))
        self.setMinimumSize(760, 520)
        self.resize(880, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        identity = QLabel(f"{tr('Controller', language)}: {controller_name}")
        identity.setWordWrap(True)
        identity.setStyleSheet("font-weight: 700;")
        root.addWidget(identity)

        description = QLabel(
            tr(
                "Choose one output for each physical button. Layouts are saved "
                "per controller and are applied immediately.",
                language,
            )
        )
        description.setWordWrap(True)
        root.addWidget(description)

        polarity_help = QLabel(
            tr(
                "Normally Open: raw 1 means pressed. Normally Closed: raw 0 means pressed.",
                language,
            )
        )
        polarity_help.setWordWrap(True)
        polarity_help.setStyleSheet("color: #8fa4bf; font-size: 11px;")
        root.addWidget(polarity_help)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(scroll)
        grid = QGridLayout(body)
        grid.setContentsMargins(2, 4, 8, 4)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        headers = (
            tr("Physical Input", language),
            tr("Output", language),
            tr("Keyboard Key", language),
            tr("Switch Type", language),
        )
        for column, title in enumerate(headers):
            label = QLabel(title)
            label.setStyleSheet("font-weight: 700;")
            grid.addWidget(label, 0, column)

        for row_index, (source, config) in enumerate(
            self._layout["buttons"].items(), start=1
        ):
            source_label = QLabel(
                tr(_SOURCE_LABELS.get(source, source.replace("_", " ").title()), language)
            )
            source_label.setMinimumWidth(130)
            grid.addWidget(source_label, row_index, 0)

            output_combo = QComboBox()
            for label, target in _OUTPUT_OPTIONS:
                output_combo.addItem(tr(label, language), target)
            selected_output = output_combo.findData(config["target"])
            output_combo.setCurrentIndex(max(0, selected_output))
            grid.addWidget(output_combo, row_index, 1)

            key_edit = QLineEdit(config.get("key", ""))
            key_edit.setPlaceholderText(
                tr("For example: space, enter, left shift", language)
            )
            key_edit.setEnabled(config["target"] == "keyboard")
            grid.addWidget(key_edit, row_index, 2)

            polarity_combo = QComboBox()
            polarity_combo.addItem(
                tr("Normally Open (1 = pressed)", language), "open"
            )
            polarity_combo.addItem(
                tr("Normally Closed (0 = pressed)", language), "closed"
            )
            selected_polarity = polarity_combo.findData(config["normally"])
            polarity_combo.setCurrentIndex(max(0, selected_polarity))
            is_hat_direction = source.startswith("dpad_")
            polarity_combo.setEnabled(not is_hat_direction)
            if is_hat_direction:
                polarity_combo.setToolTip(
                    tr("Polarity is not applicable to a hat-switch direction.", language)
                )
            grid.addWidget(polarity_combo, row_index, 3)

            output_combo.currentIndexChanged.connect(
                lambda _index, combo=output_combo, editor=key_edit:
                    editor.setEnabled(combo.currentData() == "keyboard")
            )
            self._rows[source] = (output_combo, key_edit, polarity_combo)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)
        grid.setColumnStretch(3, 2)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            orientation=Qt.Orientation.Horizontal,
        )
        buttons.button(QDialogButtonBox.Save).setText(tr("Save", language))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Cancel", language))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _save(self) -> None:
        for source, (target_combo, key_edit, _polarity_combo) in self._rows.items():
            if target_combo.currentData() == "keyboard" and not is_valid_keyboard_key(key_edit.text()):
                QMessageBox.warning(
                    self,
                    tr("Keyboard key required", self._language),
                    tr(
                        "Enter a keyboard key for each input mapped to the keyboard.",
                        self._language,
                    ),
                )
                key_edit.setFocus()
                return
        self.accept()

    def get_layout(self) -> dict:
        buttons = {}
        for source, (target_combo, key_edit, polarity_combo) in self._rows.items():
            buttons[source] = {
                "target": target_combo.currentData(),
                "key": key_edit.text().strip(),
                "normally": polarity_combo.currentData(),
            }
        return normalize_controller_layout(
            {"version": 1, "buttons": buttons},
            self._profile,
        )
