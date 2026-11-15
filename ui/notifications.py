"""Small, non-interactive status toasts for the desktop window."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.icons import ICON_SIZE, icon


class StatusToast(QFrame):
    """Show brief status messages without blocking the application's controls."""

    DISPLAY_MS = 3600
    MAX_WIDTH = 360

    _STYLES = {
        "warning": ("triangle-exclamation", "#fbbf24"),
        "success": ("circle-check", "#4ade80"),
        "battery": ("battery-quarter", "#fb7185"),
        "charging": ("bolt", "#4ade80"),
    }

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("statusToast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 16, 12)
        row.setSpacing(12)

        self._icon = QLabel(self)
        self._icon.setFixedSize(ICON_SIZE)
        row.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(3)
        self._title = QLabel(self)
        self._title.setObjectName("toastTitle")
        copy.addWidget(self._title)
        self._message = QLabel(self)
        self._message.setObjectName("toastMessage")
        self._message.setWordWrap(True)
        self._message.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        copy.addWidget(self._message)
        row.addLayout(copy, 1)

        self._queue = deque()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_next)
        self.hide()

    def notify(self, title: str, message: str, kind: str = "success") -> None:
        self._queue.append((str(title), str(message), kind))
        if not self.isVisible() and not self._timer.isActive():
            self._show_next()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        width = max(220, min(self.MAX_WIDTH, parent.width() - 32))
        self.setFixedWidth(width)
        self.adjustSize()
        x = max(16, parent.width() - self.width() - 18)
        y = max(16, parent.height() - self.height() - 28)
        self.move(x, y)

    def _show_next(self) -> None:
        if not self._queue:
            self.hide()
            return

        title, message, kind = self._queue.popleft()
        icon_name, color = self._STYLES.get(
            kind, self._STYLES["success"]
        )
        self._title.setText(title)
        self._message.setText(message)
        self._icon.setPixmap(icon(icon_name, color).pixmap(ICON_SIZE))
        self.setStyleSheet(
            f"""
            QFrame#statusToast {{
                background:#172438;
                border:1px solid #344762;
                border-left:3px solid {color};
                border-radius:12px;
            }}
            QLabel {{ background:transparent; border:none; }}
            QLabel#toastTitle {{ color:#edf4ff; font-size:12px; font-weight:750; }}
            QLabel#toastMessage {{ color:#aebdd1; font-size:11px; }}
            """
        )
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(self.DISPLAY_MS)
