"""Responsive mobile pairing dialogs for the integrated Controller Emulation workflow."""

from __future__ import annotations

import io
import time

import qrcode
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class MobilePairingDialog(QDialog):
    """Start or reuse Web Companion and wait for an authenticated mobile session."""

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

        self.setWindowTitle("Connect a mobile device")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setSizeGripEnabled(True)
        self.setStyleSheet(
            """
            QDialog#mobilePairingDialog {
                background: #101827;
                color: #eaf1ff;
            }
            QLabel {
                color: #eaf1ff;
                background: transparent;
            }
            QLabel#pairTitle {
                font-size: 24px;
                font-weight: 800;
            }
            QLabel#pairSubtitle {
                color: #9aabc4;
                font-size: 12px;
            }
            QLabel#pairEyebrow {
                color: #7e9abb;
                font-size: 9px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QLabel#pairStatus {
                color: #9ac6ff;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#pairMuted {
                color: #9aabc4;
                font-size: 11px;
            }
            QLabel#pairCode {
                color: #8ab8ff;
                font-family: Consolas;
                font-size: 30px;
                font-weight: 900;
                letter-spacing: 5px;
            }
            QLabel#pairFingerprint {
                color: #b3c4dc;
                font-family: Consolas;
                font-size: 10px;
            }
            QLabel#pairQr {
                background: #ffffff;
                border: 8px solid #ffffff;
                border-radius: 16px;
            }
            QFrame#pairCard {
                background: #172338;
                border: 1px solid #30435f;
                border-radius: 18px;
            }
            QFrame#pairInfoCard {
                background: #111d2e;
                border: 1px solid #2b3e59;
                border-radius: 12px;
            }
            QFrame#pairDivider {
                background: #2b3e59;
                border: none;
                max-height: 1px;
            }
            QPushButton {
                min-height: 38px;
                padding: 7px 14px;
                border-radius: 9px;
                border: 1px solid #3b5272;
                background: #22334c;
                color: #edf4ff;
                font-weight: 650;
            }
            QPushButton:hover:enabled {
                background: #2b4567;
                border-color: #5b7ca8;
            }
            QPushButton#pairPrimary {
                background: #2674d9;
                border-color: #4995f3;
                color: #ffffff;
                font-weight: 750;
            }
            QPushButton#pairPrimary:hover:enabled {
                background: #3685ec;
            }
            QPushButton#pairCancel {
                background: transparent;
                border-color: #34445b;
                color: #b6c4d8;
            }
            QPushButton:disabled {
                color: #66758b;
                background: #202a39;
            }
            QProgressBar {
                border: none;
                border-radius: 2px;
                background: #24344b;
                max-height: 4px;
            }
            QProgressBar::chunk {
                border-radius: 2px;
                background: #4d9bff;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            """
        )
        self.setObjectName("mobilePairingDialog")

        self._build_ui()
        self._connect_service()
        self._start_timers()

        available = None
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()

        if available is not None:
            target_width = min(1040, max(760, available.width() - 64))
            target_height = min(780, max(600, available.height() - 64))
        else:
            target_width, target_height = 960, 700

        self.setMinimumSize(min(760, target_width), min(600, target_height))
        self.resize(target_width, target_height)

        already_running = self.service.begin_mobile_pairing_flow()
        if already_running:
            self._show_pairing_ready()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(14)

        header = QVBoxLayout()
        header.setSpacing(5)

        title = QLabel("Connect your phone")
        title.setObjectName("pairTitle")
        header.addWidget(title)

        subtitle = QLabel(
            "Turn your phone into a wireless gamepad, touch mouse and PC remote. "
            "Both devices must be connected to the same trusted local network."
        )
        subtitle.setObjectName("pairSubtitle")
        subtitle.setWordWrap(True)
        header.addWidget(subtitle)
        root.addLayout(header)

        status_row = QHBoxLayout()
        self.status = QLabel("Starting the secure local connection service…")
        self.status.setObjectName("pairStatus")
        status_row.addWidget(self.status, 1)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedWidth(92)
        self._progress.setTextVisible(False)
        status_row.addWidget(self._progress)
        root.addLayout(status_row)

        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet(
            "color:#ffaaaa; background:#351f2b; border:1px solid #75404f; "
            "border-radius:8px; padding:8px 10px;"
        )
        self.error.hide()
        root.addWidget(self.error)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.card = QFrame()
        self.card.setObjectName("pairCard")
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(26)

        qr_column = QVBoxLayout()
        qr_column.setSpacing(10)

        qr_heading = QLabel("SCAN WITH YOUR PHONE")
        qr_heading.setObjectName("pairEyebrow")
        qr_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_column.addWidget(qr_heading)

        self.qr_image = QLabel("Preparing secure QR code…")
        self.qr_image.setObjectName("pairQr")
        self.qr_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_image.setMinimumSize(280, 280)
        self.qr_image.setFixedSize(320, 320)
        self.qr_image.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        qr_column.addWidget(
            self.qr_image,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        qr_note = QLabel("Point your phone camera at this code")
        qr_note.setObjectName("pairMuted")
        qr_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_note.setWordWrap(True)
        qr_column.addWidget(qr_note)
        card_layout.addLayout(qr_column, 0)

        divider = QFrame()
        divider.setObjectName("pairDivider")
        divider.setFixedWidth(1)
        card_layout.addWidget(divider)

        details = QVBoxLayout()
        details.setSpacing(12)

        scan_title = QLabel("Pair in a few seconds")
        scan_title.setStyleSheet("font-size:18px; font-weight:800;")
        details.addWidget(scan_title)

        instructions = QLabel(
            "1. Open your phone camera and scan the QR code.\n"
            "2. Open the link in your browser.\n"
            "3. Verify the certificate fingerprint if prompted, then finish pairing."
        )
        instructions.setObjectName("pairMuted")
        instructions.setWordWrap(True)
        instructions.setMinimumHeight(62)
        details.addWidget(instructions)

        code_card = QFrame()
        code_card.setObjectName("pairInfoCard")
        code_layout = QVBoxLayout(code_card)
        code_layout.setContentsMargins(13, 10, 13, 10)
        code_layout.setSpacing(6)

        code_heading = QLabel("SIX-DIGIT PAIRING CODE")
        code_heading.setObjectName("pairEyebrow")
        code_layout.addWidget(code_heading)

        code_row = QHBoxLayout()
        self.code = QLabel("— — — — — —")
        self.code.setObjectName("pairCode")
        code_row.addWidget(self.code, 1)

        self.copy_code = QPushButton("Copy code")
        self.copy_code.clicked.connect(self._copy_code)
        code_row.addWidget(self.copy_code)
        code_layout.addLayout(code_row)
        details.addWidget(code_card)

        self.countdown = QLabel("Waiting for server…")
        self.countdown.setObjectName("pairStatus")
        details.addWidget(self.countdown)

        url_card = QFrame()
        url_card.setObjectName("pairInfoCard")
        url_layout = QVBoxLayout(url_card)
        url_layout.setContentsMargins(13, 11, 13, 11)
        url_layout.setSpacing(7)

        url_heading = QLabel("LOCAL PAIRING ADDRESS")
        url_heading.setObjectName("pairEyebrow")
        url_layout.addWidget(url_heading)

        self.url = QLabel("—")
        self.url.setObjectName("pairMuted")
        self.url.setWordWrap(True)
        self.url.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        url_layout.addWidget(self.url)

        self.copy_url = QPushButton("Copy pairing link")
        self.copy_url.clicked.connect(self._copy_url)
        url_layout.addWidget(self.copy_url)
        details.addWidget(url_card)

        fingerprint_card = QFrame()
        fingerprint_card.setObjectName("pairInfoCard")
        fingerprint_layout = QVBoxLayout(fingerprint_card)
        fingerprint_layout.setContentsMargins(13, 11, 13, 11)
        fingerprint_layout.setSpacing(7)

        fingerprint_heading = QLabel("TLS CERTIFICATE FINGERPRINT · SHA-256")
        fingerprint_heading.setObjectName("pairEyebrow")
        fingerprint_heading.setWordWrap(True)
        fingerprint_layout.addWidget(fingerprint_heading)

        self.fingerprint = QLabel("—")
        self.fingerprint.setObjectName("pairFingerprint")
        self.fingerprint.setWordWrap(True)
        self.fingerprint.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        fingerprint_layout.addWidget(self.fingerprint)

        self.copy_fingerprint = QPushButton("Copy fingerprint")
        self.copy_fingerprint.clicked.connect(self._copy_fingerprint)
        fingerprint_layout.addWidget(self.copy_fingerprint)
        details.addWidget(fingerprint_card)

        self.new_code = QPushButton("Generate a new QR code")
        self.new_code.setObjectName("pairPrimary")
        self.new_code.clicked.connect(self._generate_new_code)
        details.addWidget(self.new_code)
        details.addStretch(1)

        card_layout.addLayout(details, 1)
        self._scroll.setWidget(self.card)
        root.addWidget(self._scroll, 1)

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

        self.card.hide()

    def _connect_service(self) -> None:
        self.service.server_state_changed.connect(self._on_server_state_changed)
        self.service.mobile_session_added.connect(self._on_session_added)

    def _start_timers(self) -> None:
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._update_countdown)
        self._countdown_timer.start()

    def _on_server_state_changed(self, running: bool, message: str) -> None:
        if running:
            self._show_pairing_ready()
            return
        if message:
            self.status.setText("The local connection service could not start.")
            self.error.setText(message)
            self.error.show()
            self.retry.show()
            self._progress.hide()
            self.card.hide()
            self.copy_url.setEnabled(False)
            self.copy_code.setEnabled(False)
            self.copy_fingerprint.setEnabled(False)
            self.new_code.setEnabled(False)

    def _show_pairing_ready(self) -> None:
        if self._finished_pairing or not self.service.web_server.running:
            return
        self.error.hide()
        self.retry.hide()
        self._progress.hide()
        self.card.show()
        self.status.setText("Secure server ready · Waiting for your phone")
        self.copy_url.setEnabled(True)
        self.copy_code.setEnabled(True)
        self.copy_fingerprint.setEnabled(True)
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
                box_size=10,
                border=4,
            )
            qr.add_data(server.pairing_url())
            qr.make(fit=True)
            image = qr.make_image(fill_color="#07111f", back_color="#ffffff")
            stream = io.BytesIO()
            image.save(stream, format="PNG")

            pixmap = QPixmap()
            if not pixmap.loadFromData(stream.getvalue(), "PNG") or pixmap.isNull():
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
            self.fingerprint.setText(
                server.fingerprint or "Fingerprint unavailable"
            )
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
            self.status.setText("Secure server ready · Waiting for your phone")
        else:
            self.countdown.setText(
                "Pairing code expired · Generate a new QR code"
            )
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
            QApplication.clipboard().setText(
                self.service.web_server.pairing_url()
            )
            self.copy_url.setText("Copied")
            QTimer.singleShot(
                1200,
                lambda: self.copy_url.setText("Copy pairing link"),
            )

    def _copy_code(self) -> None:
        if self.service.web_server.running:
            QApplication.clipboard().setText(
                self.service.web_server.pairing_code
            )
            self.copy_code.setText("Copied")
            QTimer.singleShot(
                1200,
                lambda: self.copy_code.setText("Copy pairing code"),
            )

    def _copy_fingerprint(self) -> None:
        if self.service.web_server.running:
            QApplication.clipboard().setText(
                self.service.web_server.fingerprint
            )
            self.copy_fingerprint.setText("Copied")
            QTimer.singleShot(
                1200,
                lambda: self.copy_fingerprint.setText("Copy fingerprint"),
            )

    def _retry_server(self) -> None:
        self.error.hide()
        self.retry.hide()
        self._progress.show()
        self.status.setText("Retrying secure local server startup…")
        self.service.ensure_server_running()

    def _on_session_added(self, session: dict) -> None:
        session_id = str(session.get("session_id") or "")
        if not session_id or session_id in self._existing_session_ids:
            return
        self.connected_session = dict(session)
        self._finished_pairing = True
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
            self.service.server_state_changed.disconnect(
                self._on_server_state_changed
            )
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
    """Brief confirmation displayed after a real mobile pairing event."""

    def __init__(self, device_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connected")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.FramelessWindowHint
        )
        self.setFixedSize(360, 205)
        self.setStyleSheet(
            """
            QDialog {
                background:#111d2b;
                border:1px solid #2d7559;
                border-radius:16px;
            }
            QLabel { color:#eaf5ef; background:transparent; }
            QLabel#successMark {
                color:#39d98a;
                font-size:52px;
                font-weight:900;
            }
            QLabel#successTitle { font-size:18px; font-weight:800; }
            QLabel#successDevice { color:#a8b9cb; font-size:12px; }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(5)

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
        device.setWordWrap(True)
        layout.addWidget(device)

        QTimer.singleShot(1800, self.accept)
