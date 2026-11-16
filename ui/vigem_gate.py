"""Reusable UI gate for features that require ViGEmBus."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from core.vigem import VIGEMBUS_RELEASES_URL


class VigemGate(QWidget):
    """Blur and disable a feature until ViGEmBus is detected."""

    recheck_requested = Signal()

    def __init__(
        self,
        content: QWidget,
        *,
        title: str = "Virtual gamepad unavailable",
        description: str = (
            "ViGEmBus is required to create a virtual Xbox/XInput controller. "
            "Install the driver on this Windows PC, then recheck or restart "
            "VPadConnect. Other application features remain available."
        ),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.content = content
        self._available = True

        self._stack = QStackedLayout(self)
        self._stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self.content)

        self.overlay = QWidget(self)
        self.overlay.setObjectName("vigemGateOverlay")
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        overlay_layout = QVBoxLayout(self.overlay)
        overlay_layout.setContentsMargins(20, 18, 20, 18)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame(self.overlay)
        card.setObjectName("vigemGateCard")
        card.setMaximumWidth(540)
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(11)

        self.icon_label = QLabel("⌁")
        self.icon_label.setObjectName("vigemGateIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.icon_label)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("vigemGateTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        card_layout.addWidget(self.title_label)

        self.description_label = QLabel(description)
        self.description_label.setObjectName("vigemGateDescription")
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label.setWordWrap(True)
        card_layout.addWidget(self.description_label)

        self.detail_label = QLabel(
            "Mouse control, hotkeys, physical HID detection, and Web Companion "
            "PC Remote are not blocked by this requirement."
        )
        self.detail_label.setObjectName("vigemGateDetail")
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setWordWrap(True)
        card_layout.addWidget(self.detail_label)

        actions = QHBoxLayout()
        actions.setSpacing(9)
        self.install_button = QPushButton("Install ViGEmBus ↗")
        self.install_button.setObjectName("vigemInstallButton")
        self.install_button.setMinimumHeight(40)
        self.install_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(VIGEMBUS_RELEASES_URL))
        )
        actions.addWidget(self.install_button)

        self.recheck_button = QPushButton("Recheck status")
        self.recheck_button.setObjectName("vigemRecheckButton")
        self.recheck_button.setMinimumHeight(40)
        self.recheck_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.recheck_button.clicked.connect(self.recheck_requested.emit)
        actions.addWidget(self.recheck_button)
        card_layout.addLayout(actions)

        overlay_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self.overlay)

        self.apply_theme()
        self.set_vigem_available(True)

    def apply_theme(self, theme_name: str | None = None) -> None:
        app = QApplication.instance()
        theme = theme_name or (
            app.property("vpadTheme") if app is not None else "dark"
        )
        light = theme == "light"
        overlay = "rgba(226, 234, 246, 205)" if light else "rgba(7, 13, 24, 112)"
        card = "#ffffff" if light else "#17243a"
        border = "#c9d9ec" if light else "#395275"
        title = "#263650" if light else "#f2f6ff"
        body = "#455a78" if light else "#d5e2f6"
        muted = "#647895" if light else "#91a6c3"
        icon_bg = "#e4efff" if light else "rgba(91, 132, 208, 28)"
        icon_border = "#c4d8f0" if light else "rgba(126, 166, 239, 60)"
        secondary_bg = "#edf3fb" if light else "#1c2a40"
        secondary_text = "#31557d" if light else "#d9e6fa"
        secondary_border = "#cbd8e8" if light else "#3b506e"
        self.setStyleSheet(f"""
            QWidget#vigemGateOverlay {{ background:{overlay}; }}
            QFrame#vigemGateCard {{
                background:{card}; border:1px solid {border}; border-radius:17px;
            }}
            QLabel#vigemGateIcon {{
                color:#397ac0; font-size:27px; font-weight:800;
                background:{icon_bg}; border:1px solid {icon_border};
                border-radius:24px; min-width:48px; max-width:48px;
                min-height:48px; max-height:48px; qproperty-alignment:AlignCenter;
            }}
            QLabel#vigemGateTitle {{ color:{title}; font-size:18px; font-weight:800; }}
            QLabel#vigemGateDescription {{ color:{body}; font-size:12px; }}
            QLabel#vigemGateDetail {{ color:{muted}; font-size:11px; }}
            QPushButton#vigemInstallButton {{
                color:white; background:#386fe8; border:1px solid #5d8eff;
                border-radius:9px; padding:8px 12px; font-weight:750;
            }}
            QPushButton#vigemInstallButton:hover {{ background:#4a80f3; }}
            QPushButton#vigemRecheckButton {{
                color:{secondary_text}; background:{secondary_bg};
                border:1px solid {secondary_border}; border-radius:9px;
                padding:8px 12px; font-weight:650;
            }}
            QPushButton#vigemRecheckButton:hover {{ background:{'#dce9f8' if light else '#273b58'}; }}
        """)

    @property
    def vigem_available(self) -> bool:
        return self._available

    def set_vigem_available(self, available: bool) -> None:
        self._available = bool(available)
        if self._available:
            self.content.setGraphicsEffect(None)
            self.content.setEnabled(True)
            self.overlay.hide()
        else:
            blur = QGraphicsBlurEffect(self.content)
            blur.setBlurRadius(5.5)
            self.content.setGraphicsEffect(blur)
            self.content.setEnabled(False)
            self.overlay.show()
        self.overlay.raise_()
