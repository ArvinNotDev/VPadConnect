"""Physical HID controller selection dialog."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QPushButton,
    QListWidgetItem,
)
from ui.icons import SMALL_ICON_SIZE, icon
from ui.animations import AnimatedDialog


class AddControllerDialog(AnimatedDialog):
    """Select a detected physical HID device and its virtual output target."""

    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add a physical controller")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumSize(740, 480)
        self.resize(820, 540)
        self.setStyleSheet(
            """
            QDialog {
                background: #101827;
                color: #eaf1ff;
            }
            QLabel { color: #eaf1ff; background: transparent; }
            QLabel#dialogTitle {
                font-size: 22px;
                font-weight: 800;
            }
            QLabel#dialogSubtitle {
                color: #9aabc4;
                font-size: 12px;
            }
            QLabel#sectionTitle {
                color: #c9d8eb;
                font-size: 12px;
                font-weight: 750;
            }
            QLabel#helperText {
                color: #91a2bc;
                font-size: 11px;
            }
            QListWidget {
                background: #172338;
                color: #eaf1ff;
                border: 1px solid #30435f;
                border-radius: 11px;
                padding: 8px;
                outline: none;
            }
            QListWidget::item {
                min-height: 38px;
                padding: 5px 9px;
                margin: 3px 1px;
                border: 1px solid #2b4260;
                border-radius: 8px;
                background: #192b42;
            }
            QListWidget::item:hover { background: #203b5a; }
            QListWidget::item:selected {
                background: #234b79;
                color: #ffffff;
            }
            QPushButton {
                min-height: 46px;
                min-width: 140px;
                padding: 7px 16px;
                border-radius: 9px;
                border: 1px solid #3b5272;
                background: #22334c;
                color: #edf4ff;
                font-size: 13px;\n                font-weight: 750;
            }
            QPushButton:hover:enabled { background: #2b4567; }
            QPushButton#refreshHidButton {
                min-width: 92px; min-height: 32px; padding: 4px 12px;
                border-radius: 8px; color: #dff2ff; background: #1d5271;
                border-color: #347ea7; font-size: 11px;
            }
            QPushButton#refreshHidButton:hover:enabled {
                background: #276b91; border-color: #62b2df;
            }
            QPushButton#addControllerConfirm {
                background: #2674d9;
                color: #ffffff;
                border-color: #4995f3;
            }
            QPushButton#addControllerConfirm:hover:enabled {
                background: #3685ec;
            }
            QPushButton:disabled {
                color: #687891;
                background: #202a39;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(12)

        title = QLabel("Add a physical controller")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Choose a connected HID controller and the virtual output it should control."
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        columns = QHBoxLayout()
        columns.setSpacing(16)

        physical_column = QVBoxLayout()
        physical_column.setSpacing(8)
        physical_header = QHBoxLayout()
        physical_header.setSpacing(8)
        physical_title = QLabel("DETECTED DEVICES")
        physical_title.setObjectName("sectionTitle")
        physical_header.addWidget(physical_title)
        physical_header.addStretch(1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("refreshHidButton")
        self.refresh_button.setIcon(icon("arrows-rotate", "#dff2ff"))
        self.refresh_button.setIconSize(SMALL_ICON_SIZE)
        self.refresh_button.setToolTip("Scan connected HID controllers again")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        physical_header.addWidget(self.refresh_button)
        physical_column.addLayout(physical_header)

        self.hid_list = QListWidget()
        self.hid_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.hid_list.setMinimumHeight(300)
        self.hid_list.setToolTip(
            "Select the HID interface that supplies the controller's input reports."
        )
        physical_column.addWidget(self.hid_list, 1)
        columns.addLayout(physical_column, 3)

        output_column = QVBoxLayout()
        output_column.setSpacing(8)
        output_title = QLabel("EMULATION OUTPUT")
        output_title.setObjectName("sectionTitle")
        output_column.addWidget(output_title)

        self.emu_list = QListWidget()
        self.emu_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.emu_list.setMinimumHeight(300)
        self.emu_list.setToolTip(
            "Choose the virtual controller output used by the selected HID device."
        )
        output_column.addWidget(self.emu_list, 1)
        columns.addLayout(output_column, 2)

        root.addLayout(columns, 1)

        helper = QLabel(
            "Remote devices are added separately using the dedicated Remote Companion action."
        )
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        root.addWidget(helper)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            orientation=Qt.Orientation.Horizontal,
        )
        self._accept_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._accept_button.setText("Add Controller")
        self._accept_button.setObjectName("addControllerConfirm")
        self._accept_button.setIcon(icon("plus", "#ffffff"))
        self._accept_button.setIconSize(SMALL_ICON_SIZE)
        self._accept_button.setEnabled(False)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_button.setText("Cancel")
        cancel_button.setIcon(icon("xmark", "#edf4ff"))
        cancel_button.setIconSize(SMALL_ICON_SIZE)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.hid_list.currentItemChanged.connect(self._update_accept_state)
        self.emu_list.currentItemChanged.connect(self._update_accept_state)

    def set_hid_devices(self, labels: list[str]) -> None:
        """Replace detected HID devices while preserving the selected item."""
        current = self.hid_list.currentItem()
        previous = current.text() if current is not None else None
        self.hid_list.clear()
        if not labels:
            placeholder = QListWidgetItem(
                "No compatible controller found. Connect one and press Refresh."
            )
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.hid_list.addItem(placeholder)
        else:
            self.hid_list.addItems(labels)
            self.hid_list.setCurrentRow(labels.index(previous) if previous in labels else 0)
        self._update_accept_state()

    def _update_accept_state(self, *_args) -> None:
        item = self.hid_list.currentItem()
        selectable = bool(
            item is not None
            and item.flags() & Qt.ItemFlag.ItemIsSelectable
            and item.flags() & Qt.ItemFlag.ItemIsEnabled
        )
        self._accept_button.setEnabled(
            selectable and self.emu_list.currentItem() is not None
        )

    def get_selections(self):
        """Return the selected HID device and virtual output labels."""
        hid_item = self.hid_list.currentItem()
        emu_item = self.emu_list.currentItem()
        if hid_item is None or not (hid_item.flags() & Qt.ItemFlag.ItemIsSelectable):
            return None, emu_item.text() if emu_item is not None else None
        return hid_item.text(), emu_item.text() if emu_item is not None else None
