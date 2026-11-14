"""Integrated mobile-device pairing dialogs for Controller Emulation."""

from __future__ import annotations

import io
import time

import qrcode
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MobilePairingDialog(QDialog):
    """Start/reuse Web Companion and wait for a newly authenticated mobile session."""

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.connected_session: dict | None = None
        self._finished_pairing = False
        self._existing_session_ids = {
            str(item.get("session_id"))
            for item in service.sessions_snapshot()
            if item.get("session_id")
        }

        self.setWindowTitle("Connect your phone")
        self.setModal(True)
        self.setMinimumSize(650, 480)
        self.setStyleSheet(
            """
            QDialog { background:#101827; color:#eaf1ff; }
            QLabel { color:#eaf1ff; background:transparent; }
            QLabel#pairTitle { font-size:22px; font-weight:800; }
            QLabel#pairMuted { color:#9aabc4; font-size:12px; }
            QLabel#pairStatus { color:#9ac6ff; font-size:12px; font-weight:700; }
            QLabel#pairCode { color:#8ab8ff; font-family:Consolas; font-size:25px; font-weight:900; letter-spacing:4px; }
            QLabel#pairFingerprint { color:#8298b8; font-family:Consolas; font-size:9px; }
            QLabel#pairQr { background:#ffffff; border:7px solid #ffffff; border-radius:12px; }
            QFrame#pairCard { background:#172338; border:1px solid #30435f; border-radius:15px; }
            QPushButton { min-height:34px; padding:6px 13px; border-radius:8px; border:1px solid #3b5272; background:#22334c; color:#edf4ff; font-weight:650; }
            QPushButton:hover:enabled { background:#2b4567; }
            QPushButton#pairPrimary { background:#2674d9; border-color:#4995f3; }
            QPushButton#pairPrimary:hover:enabled { background:#3685ec; }
            QPushButton#pairCancel { background:transparent; }
            QPushButton:disabled { color:#66758b; background:#202a39; }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        title = QLabel("Connect your phone")
        title.setObjectName("pairTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Use your phone as a wireless gamepad, touch mouse and keyboard. "
            "Keep both devices connected to the same trusted Wi-Fi network."
        )
        subtitle.setObjectName("pairMuted")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.status = QLabel("Starting the secure local connection service…")
        self.status.setObjectName("pairStatus")
        root.addWidget(self.status)

        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#ff9b9b; font-size:11px;")
        self.error.hide()
        root.addWidget(self.error)

        self.card = QFrame()
        self.card.setObjectName("pairCard")
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(18)

        self.qr_image = QLabel("Preparing QR code…")
        self.qr_image.setObjectName("pairQr")
        self.qr_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_image.setFixedSize(224, 224)
        card_layout.addWidget(self.qr_image, 0, Qt.AlignmentFlag.AlignVCenter)

        details = QVBoxLayout()
        details.setSpacing(8)
        scan_title = QLabel("Scan to pair")
        scan_title.setStyleSheet("font-size:15px; font-weight:750;")
        details.addWidget(scan_title)
        instructions = QLabel(
            "Open your phone camera and scan this QR code. "
            "Follow the browser's certificate verification step, then complete pairing."
        )
        instructions.setObjectName("pairMuted")
        instructions.setWordWrap(True)
        details.addWidget(instructions)

        code_caption = QLabel("SIX-DIGIT PAIRING CODE")
        code_caption.setStyleSheet("color:#8296b4; font-size:9px; font-weight:800;")
        details.addWidget(code_caption)
        self.code = QLabel("— — — — — —")
        self.code.setObjectName("pairCode")
        details.addWidget(self.code)

        self.countdown = QLabel("Waiting for server…")
        self.countdown.setObjectName("pairMuted")
        details.addWidget(self.countdown)

        self.url = QLabel("")
        self.url.setObjectName("pairMuted")
        self.url.setWordWrap(True)
        self.url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.addWidget(self.url)

        fingerprint_caption = QLabel("TLS CERTIFICATE FINGERPRINT · SHA-256")
        fingerprint_caption.setStyleSheet(
            "color:#8296b4; font-size:9px; font-weight:800;"
        )
        details.addWidget(fingerprint_caption)
        self.fingerprint = QLabel("—")
        self.fingerprint.setObjectName("pairFingerprint")
        self.fingerprint.setWordWrap(True)
        self.fingerprint.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        details.addWidget(self.fingerprint)

        actions = QHBoxLayout()
        self.copy_url = QPushButton("Copy pairing link")
        self.copy_url.clicked.connect(self._copy_url)
        self.copy_code = QPushButton("Copy code")
        self.copy_code.clicked.connect(self._copy_code)
        self.copy_fingerprint = QPushButton("Copy fingerprint")
        self.copy_fingerprint.clicked.connect(self._copy_fingerprint)
        actions.addWidget(self.copy_url)
        actions.addWidget(self.copy_code)
        actions.addWidget(self.copy_fingerprint)
        details.addLayout(actions)

        self.new_code = QPushButton("Generate new QR code")
        self.new_code.setObjectName("pairPrimary")
        self.new_code.clicked.connect(self._generate_new_code)
        details.addWidget(self.new_code)
        details.addStretch(1)
        card_layout.addLayout(details, 1)
        self.card.hide()
        root.addWidget(self.card, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.retry = QPushButton("Retry server")
        self.retry.hide()
        self.retry.clicked.connect(self._retry_server)
        footer.addWidget(self.retry)
        self.cancel = QPushButton("Cancel")
        self.cancel.setObjectName("pairCancel")
        self.cancel.clicked.connect(self.reject)
        footer.addWidget(self.cancel)
        root.addLayout(footer)

        self.service.server_state_changed.connect(self._on_server_state_changed)
        self.service.mobile_session_added.connect(self._on_session_added)

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._update_countdown)
        self._countdown_timer.start()

        already_running = self.service.begin_mobile_pairing_flow()
        if already_running:
            self._show_pairing_ready()

    def _on_server_state_changed(self, running: bool, message: str) -> None:
        if running:
            self._show_pairing_ready()
            return
        if message:
            self.status.setText("The local connection service could not start.")
            self.error.setText(message)
            self.error.show()
            self.retry.show()
            self.card.hide()
            self.copy_url.setEnabled(False)
            self.copy_code.setEnabled(False)
            self.new_code.setEnabled(False)

    def _show_pairing_ready(self) -> None:
        if self._finished_pairing or not self.service.web_server.running:
            return
        self.error.hide()
        self.retry.hide()
        self.card.show()
        self.status.setText("Server ready · Waiting for your phone to connect")
        self.copy_url.setEnabled(True)
        self.copy_code.setEnabled(True)
        self.new_code.setEnabled(True)
        self._render_qr()
        self._update_countdown()

    def _render_qr(self) -> None:
        server = self.service.web_server
        if not server.running or not server.pairing_code:
            return
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=3,
            )
            qr.add_data(server.pairing_url())
            qr.make(fit=True)
            image = qr.make_image(fill_color="#07111f", back_color="#ffffff")
            stream = io.BytesIO()
            image.save(stream, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(stream.getvalue(), "PNG")
            if pixmap.isNull():
                raise RuntimeError("The QR image could not be rendered.")
            self.qr_image.setPixmap(
                pixmap.scaled(
                    self.qr_image.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.code.setText(server.pairing_code)
            self.url.setText(server.local_url)
            self.fingerprint.setText(server.fingerprint or "Fingerprint unavailable")
        except Exception as exc:
            self.error.setText(f"Could not generate the pairing QR code: {exc}")
            self.error.show()

    def _update_countdown(self) -> None:
        if not self.service.web_server.running:
            return
        remaining = max(
            0,
            int(self.service.web_server.pairing_deadline - time.monotonic()),
        )
        if remaining:
            self.countdown.setText(
                f"Pairing code expires in {remaining // 60}:{remaining % 60:02d}"
            )
            self.status.setText("Server ready · Waiting for your phone to connect")
        else:
            self.countdown.setText("Pairing code expired · Generate a new QR code")
            self.status.setText("The previous pairing code has expired.")

    def _generate_new_code(self) -> None:
        if not self.service.web_server.running:
            return
        self.service.rotate_mobile_pairing_code()
        self._render_qr()
        self._update_countdown()
        self.status.setText("New pairing code generated · Scan the updated QR code")

    def _copy_url(self) -> None:
        if self.service.web_server.running:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self.service.web_server.pairing_url())
            self.copy_url.setText("Copied")
            QTimer.singleShot(1200, lambda: self.copy_url.setText("Copy pairing link"))

    def _copy_code(self) -> None:
        if self.service.web_server.running:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self.service.web_server.pairing_code)
            self.copy_code.setText("Copied")
            QTimer.singleShot(1200, lambda: self.copy_code.setText("Copy code"))

    def _copy_fingerprint(self) -> None:
        if self.service.web_server.running:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self.service.web_server.fingerprint)
            self.copy_fingerprint.setText("Copied")
            QTimer.singleShot(
                1200,
                lambda: self.copy_fingerprint.setText("Copy fingerprint"),
            )

    def _retry_server(self) -> None:
        self.error.hide()
        self.retry.hide()
        self.status.setText("Retrying secure local server startup…")
        self.service.ensure_server_running()

    def _on_session_added(self, session: dict) -> None:
        session_id = str(session.get("session_id") or "")
        if not session_id or session_id in self._existing_session_ids:
            return
        self.connected_session = dict(session)
        self._finished_pairing = True
        # Invalidate the QR credential immediately so it cannot be reused.
        try:
            self.service.rotate_mobile_pairing_code()
        except Exception:
            pass
        self.accept()

    def _cleanup(self) -> None:
        if getattr(self, "_cleanup_done", False):
            return
        self._cleanup_done = True
        self._countdown_timer.stop()
        try:
            self.service.server_state_changed.disconnect(self._on_server_state_changed)
        except (RuntimeError, TypeError):
            pass
        try:
            self.service.mobile_session_added.disconnect(self._on_session_added)
        except (RuntimeError, TypeError):
            pass
        self.service.end_mobile_pairing_flow()

    def done(self, result: int) -> None:
        self._cleanup()
        super().done(result)


class MobileConnectedDialog(QDialog):
    """Brief, automatically dismissed confirmation after a real pairing event."""

    def __init__(self, device_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connected")
        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.FramelessWindowHint
        )
        self.setFixedSize(330, 190)
        self.setStyleSheet(
            """
            QDialog { background:#111d2b; border:1px solid #2d7559; border-radius:16px; }
            QLabel { color:#eaf5ef; background:transparent; }
            QLabel#successMark { color:#39d98a; font-size:48px; font-weight:900; }
            QLabel#successTitle { font-size:17px; font-weight:800; }
            QLabel#successDevice { color:#a8b9cb; font-size:11px; }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(4)
        mark = QLabel("✓")
        mark.setObjectName("successMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(mark)
        title = QLabel("Connected Successfully")
        title.setObjectName("successTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        device = QLabel(device_name or "Mobile Device")
        device.setObjectName("successDevice")
        device.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(device)
        QTimer.singleShot(1800, self.accept)
