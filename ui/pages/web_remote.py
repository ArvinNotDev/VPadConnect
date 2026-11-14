"""Desktop controls for the secure, browser-based companion server."""
from __future__ import annotations

import io
import json
import threading
import time

import qrcode
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.web_remote import WebRemoteServer
from core.remote_actions import load_remote_permissions, save_remote_permissions
from core.vigem import VIGEMBUS_RELEASES_URL, is_vigem_installed


class _WebRemoteSignals(QObject):
    started = Signal()
    start_failed = Signal(str)
    stopped = Signal()
    mapper_added = Signal(object)
    session_added = Signal(object)
    session_removed = Signal(object)


class WebRemotePage(QWidget):
    """Start/stop the HTTPS browser companion and display short-lived pairing credentials."""

    FIXED_PORT = 8765
    vigem_recheck_requested = Signal()
    server_state_changed = Signal(bool, str)
    mobile_session_added = Signal(object)
    mobile_session_removed = Signal(str)

    def __init__(
        self, settings, controllers_page, hotkey_page, status_changed=None, *,
        vigem_available: bool | None = None, parent=None,
    ):
        super().__init__(parent)
        self._vigem_available = (
            is_vigem_installed() if vigem_available is None else bool(vigem_available)
        )
        self.setObjectName("webCompanionPage")
        self._status_changed = status_changed
        self._last_client_count = -1
        self._last_clients = ()
        self._server_busy = False
        self._mobile_sessions: dict[str, dict] = {}
        self._mobile_pairing_flows = 0
        self._auto_started_by_mobile = False
        self._signals = _WebRemoteSignals(self)
        self._signals.started.connect(self._on_server_started)
        self._signals.start_failed.connect(self._on_server_start_failed)
        self._signals.stopped.connect(self._on_server_stopped)
        self._signals.mapper_added.connect(self._register_mapper)
        self._signals.session_added.connect(self._on_mobile_session_added)
        self._signals.session_removed.connect(self._on_mobile_session_removed)
        self.web_server = WebRemoteServer(
            settings,
            controllers_page,
            hotkey_page,
            mapper_added=self._signals.mapper_added.emit,
            session_added=self._signals.session_added.emit,
            session_removed=self._signals.session_removed.emit,
            port=self.FIXED_PORT,
        )
        self._build_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(700)
        self._refresh_timer.timeout.connect(self._refresh_countdown)
        self._refresh_timer.start()
        self._set_running(False)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 6, 16, 8)
        root.setSpacing(8)

        intro = QFrame()
        intro.setObjectName("webHero")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(16, 6, 16, 6)
        intro_layout.setSpacing(3)
        eyebrow = QLabel("VPADCONNECT")
        eyebrow.setObjectName("webEyebrow")
        title = QLabel("Web Companion")
        title.setObjectName("webTitle")
        description = QLabel("Turn a phone, tablet, or another PC into a controller.")
        description.setObjectName("webMuted")
        intro_layout.addWidget(eyebrow)
        intro_layout.addWidget(title)
        intro_layout.addWidget(description)
        root.addWidget(intro)

        # The browser gamepad needs ViGEmBus, but mouse and PC Remote do not.
        self.vigem_notice = QFrame()
        self.vigem_notice.setObjectName("webVigemNotice")
        notice_layout = QHBoxLayout(self.vigem_notice)
        notice_layout.setContentsMargins(12, 9, 12, 9)
        notice_layout.setSpacing(10)
        notice_copy = QVBoxLayout()
        notice_copy.setSpacing(3)
        self.vigem_notice_title = QLabel("Virtual gamepad unavailable")
        self.vigem_notice_title.setObjectName("webVigemNoticeTitle")
        self.vigem_notice_detail = QLabel(
            "Install ViGEmBus on this Windows PC to enable virtual Xbox/XInput output. "
            "Touch mouse and PC Remote stay available without it."
        )
        self.vigem_notice_detail.setObjectName("webVigemNoticeDetail")
        self.vigem_notice_detail.setWordWrap(True)
        notice_copy.addWidget(self.vigem_notice_title)
        notice_copy.addWidget(self.vigem_notice_detail)
        notice_layout.addLayout(notice_copy, 1)
        self.vigem_install_button = QPushButton("Install ViGEmBus ↗")
        self.vigem_install_button.setObjectName("webVigemInstall")
        self.vigem_install_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(VIGEMBUS_RELEASES_URL))
        )
        notice_layout.addWidget(self.vigem_install_button)
        self.vigem_recheck_button = QPushButton("Recheck")
        self.vigem_recheck_button.setObjectName("webVigemRecheck")
        self.vigem_recheck_button.clicked.connect(self.vigem_recheck_requested.emit)
        notice_layout.addWidget(self.vigem_recheck_button)
        root.addWidget(self.vigem_notice)

        setup = QFrame()
        setup.setObjectName("webCard")
        setup_layout = QGridLayout(setup)
        setup_layout.setContentsMargins(12, 6, 12, 6)
        setup_layout.setHorizontalSpacing(12)
        setup_layout.setVerticalSpacing(6)
        setup_layout.setColumnStretch(1, 1)

        status_caption = QLabel("STATUS")
        status_caption.setObjectName("webCaption")
        self.status_badge = QLabel("●  STOPPED")
        self.status_badge.setObjectName("webStatusStopped")
        self.permissions_button = QPushButton("⚙")
        self.permissions_button.setObjectName("webPermissionsButton")
        self.permissions_button.setToolTip("Remote access permissions")
        self.permissions_button.setFixedSize(34, 32)
        self.permissions_button.clicked.connect(self._edit_permissions)
        setup_layout.addWidget(status_caption, 0, 0)
        setup_layout.addWidget(self.status_badge, 0, 1)
        setup_layout.addWidget(self.permissions_button, 0, 2, alignment=Qt.AlignmentFlag.AlignRight)

        url_caption = QLabel("BROWSER URL")
        url_caption.setObjectName("webCaption")
        self.url_label = QLabel("Start the server to get the URL.")
        self.url_label.setObjectName("webUrl")
        self.url_label.setWordWrap(True)
        self.url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fingerprint_caption = QLabel("TLS FINGERPRINT")
        fingerprint_caption.setObjectName("webCaption")
        self.fingerprint_label = QLabel("—")
        self.fingerprint_label.setObjectName("webFingerprint")
        self.fingerprint_label.setWordWrap(True)
        self.fingerprint_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.copy_button = QPushButton("Copy URL")
        self.copy_button.setObjectName("webCopyButton")
        self.copy_button.setFixedSize(96, 32)
        self.copy_button.setToolTip("Copy the pairing link")
        self.copy_button.clicked.connect(self._copy_url)
        setup_layout.addWidget(url_caption, 1, 0)
        setup_layout.addWidget(self.url_label, 1, 1)
        setup_layout.addWidget(self.copy_button, 1, 2)
        setup_layout.addWidget(fingerprint_caption, 2, 0)
        setup_layout.addWidget(self.fingerprint_label, 2, 1, 1, 2)

        self.start_button = QPushButton("Start Web Server")
        self.start_button.setObjectName("webStartButton")
        self.start_button.setMinimumHeight(36)
        self.start_button.clicked.connect(self._toggle_server)
        setup_layout.addWidget(self.start_button, 3, 0, 1, 3)
        root.addWidget(setup)

        pairing = QFrame()
        pairing.setObjectName("webPairingCard")
        self.pairing_card = pairing
        pairing_layout = QHBoxLayout(pairing)
        pairing_layout.setContentsMargins(12, 6, 12, 6)
        pairing_layout.setSpacing(14)

        qr_column = QVBoxLayout()
        qr_column.setSpacing(6)
        qr_title = QLabel("Scan to connect")
        qr_title.setObjectName("webSectionTitle")
        self.qr_image = QLabel("QR appears after startup")
        self.qr_image.setObjectName("webQrImage")
        self.qr_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_image.setFixedSize(160, 160)
        qr_column.addWidget(qr_title)
        qr_column.addWidget(self.qr_image, 0, Qt.AlignmentFlag.AlignLeft)
        pairing_layout.addLayout(qr_column, 0)

        code_column = QVBoxLayout()
        code_column.setSpacing(6)
        code_title = QLabel("Pairing code")
        code_title.setObjectName("webSectionTitle")
        self.code_label = QLabel("— — — — — —")
        self.code_label.setObjectName("webPairCode")
        self.code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.expiry_label = QLabel("Start the server to create a code.")
        self.expiry_label.setObjectName("webMuted")
        self.rotate_button = QPushButton("New code")
        self.rotate_button.setMinimumHeight(34)
        self.rotate_button.clicked.connect(self._rotate_code)
        clients_title = QLabel("CONNECTED BROWSERS · 0")
        clients_title.setObjectName("webCaption")
        self.client_list_header = clients_title
        self.client_list = QListWidget()
        self.client_list.setObjectName("webClientsList")
        self.client_list.setMinimumHeight(48)
        self.client_list.setMaximumHeight(60)
        self.client_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        code_column.addWidget(code_title)
        code_column.addWidget(self.code_label)
        code_column.addWidget(self.expiry_label)
        code_column.addWidget(self.rotate_button)
        code_column.addSpacing(2)
        code_column.addWidget(clients_title)
        code_column.addWidget(self.client_list, 1)
        pairing_layout.addLayout(code_column, 1)
        root.addWidget(pairing)


        self.setStyleSheet("""
            QWidget#webCompanionPage { background: transparent; }
            QFrame#webHero { border: 1px solid #2a3d5b; border-radius: 15px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #172841,stop:1 #211a3b); }
            QFrame#webCard, QFrame#webPairingCard { border: 1px solid #2b3b53;
                border-radius: 13px; background: #121c2b; }
            QFrame#webPairingCard:disabled { border-color: #292f3a; background: #1a202b; }
            QLabel { background: transparent; color: #eaf1ff; }
            QLabel#webEyebrow { color: #91b3ff; font-size: 9px; font-weight: 800; letter-spacing: 2px; }
            QLabel#webTitle { font-size: 21px; font-weight: 800; }
            QLabel#webMuted { color: #a5b4cb; font-size: 11px; }
            QLabel#webCaption { color: #8296b4; font-size: 9px; font-weight: 800; }
            QLabel#webSectionTitle { color: #f0f4ff; font-size: 14px; font-weight: 750; }
            QLabel#webUrl { color: #85bcff; font-size: 12px; font-weight: 700; }
            QLabel#webFingerprint { color: #879ab7; font-family: Consolas; font-size: 9px; }
            QLabel#webStatusStopped { color: #ff9cac; font-size: 11px; font-weight: 800; }
            QLabel#webStatusRunning { color: #68e3b7; font-size: 11px; font-weight: 800; }
            QLabel#webPairCode { color: #8ab8ff; font-family: Consolas; font-size: 23px; font-weight: 900; letter-spacing: 3px; }
            QLabel#webQrImage { padding: 6px; color: #637996; background: #fff; border-radius: 10px; }
            QListWidget#webClientsList { background: #0d1623; border: 1px solid #28374d;
                border-radius: 8px; padding: 3px; color: #c9d6e9; }
            QListWidget#webClientsList::item { padding: 4px 6px; border-radius: 5px; }
            QListWidget#webClientsList::item:selected { background: #2a4165; }
            QWidget:disabled { color: #69778c; }
            QPushButton { border: 1px solid #354964; border-radius: 8px; padding: 7px 11px;
                color: #eef4ff; background: #1a2940; font-weight: 650; }
            QPushButton:hover:enabled { background: #263d5e; }
            QPushButton:disabled { color: #667790; background: #202633; border-color: #303746; }
            QPushButton#webStartButton { background: #17845d; border-color: #35b987;
                color: white; font-weight: 800; }
            QPushButton#webStartButton:hover:enabled { background: #1ca370; }
            QPushButton#webStartButton[running="true"] { background: #bd394b; border-color: #e65a6a; }
            QPushButton#webStartButton[running="true"]:hover:enabled { background: #d34859; }
            QPushButton#webCopyButton { padding: 4px 8px; font-size: 11px; }
            QPushButton#webPermissionsButton { padding: 0; font-size: 17px; }
            QFrame#webVigemNotice { border: 1px solid #806239; border-radius: 12px;
                background: #2a2119; }
            QLabel#webVigemNoticeTitle { color: #ffd49a; font-size: 12px; font-weight: 800; }
            QLabel#webVigemNoticeDetail { color: #d8c5aa; font-size: 11px; }
            QPushButton#webVigemInstall { background: #77501e; border-color: #ae7a37;
                color: #fff3df; font-weight: 800; }
            QPushButton#webVigemInstall:hover:enabled { background: #8b612a; }
            QPushButton#webVigemRecheck { background: #1b283a; }
        """)
        self._set_vigem_available(self._vigem_available)

    def set_vigem_available(self, available: bool) -> None:
        self._vigem_available = bool(available)
        self._set_vigem_available(self._vigem_available)

    def _set_vigem_available(self, available: bool) -> None:
        self.vigem_notice.setVisible(not bool(available))

    def _toggle_server(self) -> None:
        if self._server_busy:
            return
        self._server_busy = True
        self.start_button.setEnabled(False)
        if self.web_server.running:
            self.start_button.setText("Stopping…")
            target = self._stop_server_worker
        else:
            self.start_button.setText("Starting…")
            target = self._start_server_worker
        self._server_worker = threading.Thread(target=target, name="VPadConnectWebSetup", daemon=True)
        self._server_worker.start()

    def _start_server_worker(self) -> None:
        try:
            self.web_server.start()
        except Exception as exc:
            self._signals.start_failed.emit(str(exc))
        else:
            self._signals.started.emit()

    def _stop_server_worker(self) -> None:
        try:
            self.web_server.stop()
        finally:
            self._signals.stopped.emit()

    def _on_server_started(self) -> None:
        self._server_busy = False
        self._set_running(True)
        self._render_qr()
        self._refresh_countdown()
        self.server_state_changed.emit(True, "")
        self._notify_status_changed()
        self._maybe_stop_auto_server()

    def _on_server_start_failed(self, message: str) -> None:
        self._server_busy = False
        self._auto_started_by_mobile = False
        self._set_running(False)
        self.server_state_changed.emit(False, message)
        if self.isVisible():
            QMessageBox.critical(
                self, "Could not start Web Companion",
                f"Could not start the local server on port {self.FIXED_PORT}.\n\n{message}",
            )

    def _on_server_stopped(self) -> None:
        self._server_busy = False
        self._set_running(False)
        self.server_state_changed.emit(False, "")
        self._notify_status_changed()

    def _set_running(self, running: bool) -> None:
        self.status_badge.setText("●  RUNNING" if running else "●  STOPPED")
        self.status_badge.setObjectName("webStatusRunning" if running else "webStatusStopped")
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
        self.start_button.setText("Stop Web Server" if running else "Start Web Server")
        self.start_button.setProperty("running", running)
        self.start_button.setEnabled(not self._server_busy)
        self.start_button.style().unpolish(self.start_button)
        self.start_button.style().polish(self.start_button)
        self.pairing_card.setEnabled(running)
        self.copy_button.setEnabled(running)
        self.permissions_button.setEnabled(True)
        self.client_list.setEnabled(running)
        if running:
            self.url_label.setText(self.web_server.local_url)
            self.fingerprint_label.setText(self.web_server.fingerprint)
        else:
            self.url_label.setText("Start the server to get the URL.")
            self.fingerprint_label.setText("—")
            self.client_list_header.setText("CONNECTED BROWSERS · 0")
            self.qr_image.clear()
            self.qr_image.setText("QR appears after startup")
            self.code_label.setText("— — — — — —")
            self.expiry_label.setText("Start the server to create a code.")
            self.client_list.clear()
            self._last_clients = ()
            self._last_client_count = 0

    def _render_qr(self) -> None:
        if not self.web_server.running:
            return
        try:
            qr = qrcode.QRCode(
                version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=7, border=3,
            )
            qr.add_data(self.web_server.pairing_url())
            qr.make(fit=True)
            image = qr.make_image(fill_color="#07111f", back_color="#ffffff")
            stream = io.BytesIO()
            image.save(stream, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(stream.getvalue(), "PNG")
            if pixmap.isNull():
                raise RuntimeError("Could not render the QR image.")
            self.qr_image.setPixmap(pixmap.scaled(
                self.qr_image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self.qr_image.setText("")
            self.code_label.setText(self.web_server.pairing_code)
            self.url_label.setText(self.web_server.local_url)
        except Exception as exc:
            self.qr_image.setText("QR unavailable")
            QMessageBox.warning(self, "Pairing QR", str(exc))

    def _rotate_code(self) -> None:
        if not self.web_server.running:
            return
        self.web_server.rotate_pairing_code()
        self._render_qr()
        self._refresh_countdown()

    def _refresh_countdown(self) -> None:
        if not self.web_server.running:
            return
        import time
        names = tuple(self.web_server.connected_clients)
        count = len(names)
        self.client_list_header.setText(f"CONNECTED BROWSERS · {count}")
        if names != self._last_clients:
            self._last_clients = names
            self.client_list.clear()
            for name in names:
                QListWidgetItem(name, self.client_list)
        if count != self._last_client_count:
            self._last_client_count = count
            self._notify_status_changed()
        remaining = max(0, int(self.web_server.pairing_deadline - time.monotonic()))
        self.expiry_label.setText(
            f"Expires in {remaining // 60}:{remaining % 60:02d}"
            if remaining else "Code expired — generate a new one"
        )

    def _copy_url(self) -> None:
        if not self.web_server.running:
            return
        QApplication.clipboard().setText(self.web_server.pairing_url())
        self.copy_button.setText("Copied")
        QTimer.singleShot(
            1400,
            lambda: self.copy_button.setText("Copy URL") if self.web_server.running else None,
        )

    def _edit_permissions(self) -> None:
        current = load_remote_permissions()
        dialog = QDialog(self)
        dialog.setWindowTitle("Remote access")
        dialog.setModal(True)
        dialog.setMinimumWidth(340)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(8)
        title = QLabel("Allow remote actions")
        title.setStyleSheet("font-size: 16px; font-weight: 750;")
        layout.addWidget(title)
        checks = {}
        for key, label in (
            ("keyboard", "Keyboard and text"),
            ("media", "Media and volume"),
            ("clipboard", "Clipboard"),
            ("app_launch", "Approved app shortcuts"),
            ("presentation", "Presentation controls"),
            ("power", "Power actions"),
        ):
            check = QCheckBox(label)
            check.setChecked(current.get(key, False))
            checks[key] = check
            layout.addWidget(check)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            save_remote_permissions({key: check.isChecked() for key, check in checks.items()})

    def _register_mapper(self, instance) -> None:
        self.web_server.controllers_page.add_x360_instance(instance)
        self.web_server.hotkey_page.add_x360_instance(instance)

    def open_permissions_dialog(self) -> None:
        """Open the existing permission editor from the integrated controller page."""
        self._edit_permissions()

    def _on_mobile_session_added(self, session: dict) -> None:
        session_id = str(session.get("session_id") or "")
        if not session_id:
            return
        self._mobile_sessions[session_id] = dict(session)
        self.mobile_session_added.emit(dict(session))
        self._notify_status_changed()

    def _on_mobile_session_removed(self, session: dict) -> None:
        session_id = str(session.get("session_id") or "")
        if session_id:
            self._mobile_sessions.pop(session_id, None)
            self.mobile_session_removed.emit(session_id)
        try:
            self.web_server.controllers_page.refresh_list()
        except Exception:
            pass
        try:
            self.web_server.hotkey_page.refresh_list()
        except Exception:
            pass
        self._notify_status_changed()
        self._maybe_stop_auto_server()

    def sessions_snapshot(self) -> list[dict]:
        try:
            return self.web_server.sessions_snapshot()
        except Exception:
            return [dict(session) for session in self._mobile_sessions.values()]

    def begin_mobile_pairing_flow(self) -> bool:
        """Register an active pairing dialog and ensure the HTTPS server is running."""
        self._mobile_pairing_flows += 1
        if self.web_server.running:
            if (
                not self.web_server.pairing_code
                or time.monotonic() >= self.web_server.pairing_deadline
            ):
                self.web_server.rotate_pairing_code()
            return True
        if not self._server_busy:
            self._auto_started_by_mobile = True
        self.ensure_server_running()
        return False

    def ensure_server_running(self) -> bool:
        """Start the embedded server if needed; return whether it is ready now."""
        if self.web_server.running:
            return True
        if not self._server_busy:
            if self._mobile_pairing_flows:
                self._auto_started_by_mobile = True
            self._toggle_server()
        return False

    def end_mobile_pairing_flow(self) -> None:
        self._mobile_pairing_flows = max(0, self._mobile_pairing_flows - 1)
        self._maybe_stop_auto_server()

    def rotate_mobile_pairing_code(self) -> str:
        return self.web_server.rotate_pairing_code()

    def disconnect_mobile_session(self, session_id: str) -> None:
        """Disconnect one mobile session without blocking the Qt event loop."""
        def disconnect() -> None:
            try:
                removed = self.web_server.disconnect_session(session_id)
                if not removed:
                    self._mobile_sessions.pop(session_id, None)
                    self.mobile_session_removed.emit(session_id)
            except Exception:
                logger.exception("Could not disconnect mobile session %s", session_id)

        threading.Thread(
            target=disconnect,
            name="VPadConnectMobileDisconnect",
            daemon=True,
        ).start()

    def _maybe_stop_auto_server(self) -> None:
        if (
            self._auto_started_by_mobile
            and self._mobile_pairing_flows == 0
            and self.web_server.running
            and self.web_server.client_count == 0
            and not self._server_busy
        ):
            self._auto_started_by_mobile = False
            self._toggle_server()

    def shutdown(self) -> None:
        self._refresh_timer.stop()
        self.web_server.stop()


    def _notify_status_changed(self) -> None:
        if self._status_changed is not None:
            try:
                self._status_changed()
            except Exception:
                # Tray UI should never prevent the browser server from starting.
                pass
