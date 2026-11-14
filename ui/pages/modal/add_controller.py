from PySide6.QtWidgets import (
    QDialog, QLabel, QVBoxLayout, QListWidget, QHBoxLayout,
    QDialogButtonBox, QListWidgetItem,
)
from PySide6.QtCore import Qt

class AddControllerDialog(QDialog):
    """
    A modal dialog that presents two lists:
    - HID device list
    - Emulated controller list
    Returns selected items via exec_().
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Controller")
        self.setModal(True)
        self.resize(400, 300)

        main_layout = QVBoxLayout(self)

        # Title
        lbl_title = QLabel(
            "Select a physical controller or connect a phone"
        )
        lbl_title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(lbl_title)

        # Content layout
        lists_layout = QHBoxLayout()

        # HID List
        self.hid_list = QListWidget()
        self.hid_list.setSelectionMode(QListWidget.SingleSelection)
        lists_layout.addWidget(self.hid_list)

        # Emulated Controller List
        self.emu_list = QListWidget()
        self.emu_list.setSelectionMode(QListWidget.SingleSelection)
        self.emu_list.setToolTip("Choose the output used by a physical HID controller.")
        lists_layout.addWidget(self.emu_list)

        main_layout.addLayout(lists_layout)

        self.mobile_hint = QLabel(
            "Mobile Device connects through the secure Web Companion. "
            "The server and QR pairing window start automatically."
        )
        self.mobile_hint.setWordWrap(True)
        self.mobile_hint.setStyleSheet("color: #91a2bc; font-size: 11px;")
        self.mobile_hint.setVisible(False)
        main_layout.addWidget(self.mobile_hint)

        self.hid_list.currentItemChanged.connect(self._update_selection_mode)

        # Buttons (Apply / Cancel)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            orientation=Qt.Horizontal
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)
             
    def add_mobile_device_option(self):
        """Append the remote phone source without changing physical HID indexes."""
        item = QListWidgetItem("📱  Mobile Device / Web Companion")
        item.setData(Qt.ItemDataRole.UserRole, "mobile")
        item.setToolTip(
            "Pair a phone over your local network and use its gamepad, mouse and keyboard."
        )
        self.hid_list.addItem(item)

    def is_mobile_selected(self) -> bool:
        item = self.hid_list.currentItem()
        return bool(
            item is not None
            and item.data(Qt.ItemDataRole.UserRole) == "mobile"
        )

    def _update_selection_mode(self, current=None, _previous=None):
        mobile = bool(
            current is not None
            and current.data(Qt.ItemDataRole.UserRole) == "mobile"
        )
        self.emu_list.setEnabled(not mobile)
        self.mobile_hint.setVisible(mobile)

    def get_selections(self):
        """
        Returns (hid_device, emu_device) or (None, None) if nothing selected.
        """
        hid = None
        emu = None

        if self.hid_list.currentItem() is not None:
            hid = self.hid_list.currentItem().text()

        if self.emu_list.currentItem() is not None:
            emu = self.emu_list.currentItem().text()

        return hid, emu
