"""Dark, bounded live terminal for inspecting raw controller HID reports."""
from __future__ import annotations

from collections import deque
from pathlib import Path
import time

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.raw_hid import format_raw_hid_report
from ui.i18n import tr
from ui.animations import AnimatedDialog


class RawHidTerminalDialog(AnimatedDialog):
    """Display rate-limited live HID packets without doing work on HID threads."""

    visibility_changed = Signal(bool)

    def __init__(self, language: str = "eng", parent: QWidget | None = None):
        super().__init__(parent)
        self.language = language if language in {"eng", "fa", "es"} else "eng"
        self.setObjectName("rawHidTerminal")
        self.setWindowTitle(tr("Raw HID Live Terminal", self.language))
        self.setMinimumSize(720, 460)
        self.resize(1080, 640)
        self.setModal(False)

        self._capture_enabled = True
        self._paused = False
        self._record_count = 0
        self._last_report = ""
        self._last_size = 0
        self._last_device = "—"
        self._recent_arrivals: deque[float] = deque(maxlen=120)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(12)

        header = QFrame(self)
        header.setObjectName("rawTerminalHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 13, 16, 13)
        header_layout.setSpacing(12)

        brand = QFrame(header)
        brand.setObjectName("rawTerminalIcon")
        brand.setFixedSize(44, 44)
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        glyph = QLabel(">_", brand)
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setObjectName("rawTerminalGlyph")
        brand_layout.addWidget(glyph)
        header_layout.addWidget(brand)

        title_stack = QVBoxLayout()
        title_stack.setSpacing(3)
        self.title_label = QLabel(tr("Raw HID Live Terminal", self.language))
        self.title_label.setObjectName("rawTerminalTitle")
        self.subtitle_label = QLabel(tr("RAW INPUT STREAM", self.language))
        self.subtitle_label.setObjectName("rawTerminalSubtitle")
        title_stack.addWidget(self.title_label)
        title_stack.addWidget(self.subtitle_label)
        header_layout.addLayout(title_stack, 1)

        self.status_badge = QLabel()
        self.status_badge.setObjectName("rawTerminalStatus")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.status_badge)
        root.addWidget(header)

        stats = QHBoxLayout()
        stats.setSpacing(9)
        self._packets_value = self._add_stat_card(stats, tr("Packets", self.language), "0")
        self._rate_value = self._add_stat_card(stats, tr("Rate", self.language), "0.0/s")
        self._last_size_value = self._add_stat_card(stats, tr("Last report", self.language), "—")
        self._device_value = self._add_stat_card(stats, tr("Device", self.language), "—")
        root.addLayout(stats)

        self.output = QPlainTextEdit(self)
        self.output.setObjectName("rawHidOutput")
        self.output.setReadOnly(True)
        self.output.setUndoRedoEnabled(False)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.document().setMaximumBlockCount(1600)
        self.output.setPlaceholderText(tr("Waiting for HID reports…", self.language))
        terminal_font = QFont("Cascadia Mono")
        if not terminal_font.exactMatch():
            terminal_font = QFont("Consolas")
        if not terminal_font.exactMatch():
            terminal_font = QFont("Courier New")
        terminal_font.setStyleHint(QFont.StyleHint.Monospace)
        terminal_font.setPointSize(10)
        self.output.setFont(terminal_font)
        root.addWidget(self.output, 1)

        self.detail_label = QLabel(tr("Waiting for HID reports…", self.language))
        self.detail_label.setObjectName("rawTerminalDetail")
        self.detail_label.setWordWrap(True)
        root.addWidget(self.detail_label)

        self._meta_format = QTextCharFormat()
        self._meta_format.setForeground(QColor("#7e94b3"))
        self._hex_format = QTextCharFormat()
        self._hex_format.setForeground(QColor("#9cf7bd"))
        self._hex_format.setFont(terminal_font)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.auto_scroll = QCheckBox(tr("Auto-scroll", self.language))
        self.auto_scroll.setChecked(True)
        self.auto_scroll.setObjectName("rawTerminalAutoScroll")
        footer.addWidget(self.auto_scroll)
        footer.addStretch(1)

        self.pause_button = QPushButton(tr("Pause stream", self.language))
        self.pause_button.setObjectName("rawTerminalSecondary")
        self.pause_button.clicked.connect(self._toggle_pause)
        footer.addWidget(self.pause_button)

        self.clear_button = QPushButton(tr("Clear", self.language))
        self.clear_button.setObjectName("rawTerminalSecondary")
        self.clear_button.clicked.connect(self.clear_terminal)
        footer.addWidget(self.clear_button)

        self.copy_button = QPushButton(tr("Copy latest", self.language))
        self.copy_button.setObjectName("rawTerminalSecondary")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_latest)
        footer.addWidget(self.copy_button)

        self.save_button = QPushButton(tr("Save capture…", self.language))
        self.save_button.setObjectName("rawTerminalPrimary")
        self.save_button.clicked.connect(self.save_capture)
        footer.addWidget(self.save_button)

        self.close_button = QPushButton(tr("Close", self.language))
        self.close_button.setObjectName("rawTerminalSecondary")
        self.close_button.clicked.connect(self.close)
        footer.addWidget(self.close_button)
        root.addLayout(footer)

        self.setStyleSheet("""
            QDialog#rawHidTerminal {
                background: #07111e;
                color: #dbe8f7;
            }
            QFrame#rawTerminalHeader {
                background: #0c1929;
                border: 1px solid #1b3046;
                border-radius: 13px;
            }
            QFrame#rawTerminalIcon {
                background: #102a27;
                border: 1px solid #225b4a;
                border-radius: 11px;
            }
            QLabel#rawTerminalGlyph {
                color: #80f5b2;
                font-family: Consolas;
                font-weight: 900;
                font-size: 17px;
            }
            QLabel#rawTerminalTitle {
                color: #eef6ff;
                font-size: 17px;
                font-weight: 800;
            }
            QLabel#rawTerminalSubtitle {
                color: #7089a7;
                font-size: 9px;
                font-weight: 800;
                letter-spacing: 2px;
            }
            QLabel#rawTerminalDetail {
                color: #7f94ad;
                font-size: 10px;
                padding-left: 3px;
            }
            QLabel#rawTerminalStatus {
                min-width: 82px;
                padding: 7px 11px;
                border-radius: 8px;
                font-size: 10px;
                font-weight: 900;
            }
            QLabel#rawTerminalStatus[state="live"] {
                color: #a7f3c1;
                background: #12382d;
                border: 1px solid #24674d;
            }
            QLabel#rawTerminalStatus[state="paused"] {
                color: #f9d58b;
                background: #3a2c16;
                border: 1px solid #735421;
            }
            QLabel#rawTerminalStatus[state="disabled"] {
                color: #aab9cd;
                background: #1b2a3b;
                border: 1px solid #34485e;
            }
            QFrame#rawTerminalStat {
                background: #0b1726;
                border: 1px solid #1a2a3d;
                border-radius: 10px;
            }
            QLabel#rawTerminalStatLabel {
                color: #7188a5;
                font-size: 9px;
                font-weight: 800;
            }
            QLabel#rawTerminalStatValue {
                color: #d8f4e5;
                font-family: Consolas;
                font-size: 14px;
                font-weight: 800;
            }
            QPlainTextEdit#rawHidOutput {
                background: #050b13;
                color: #9cf7bd;
                border: 1px solid #1a3041;
                border-radius: 11px;
                padding: 12px;
                selection-background-color: #194b3b;
                selection-color: #e4fff0;
            }
            QCheckBox#rawTerminalAutoScroll {
                color: #9aadc5;
                spacing: 7px;
                padding: 4px;
            }
            QPushButton#rawTerminalSecondary, QPushButton#rawTerminalPrimary {
                min-height: 32px;
                padding: 5px 11px;
                border-radius: 8px;
                font-weight: 650;
            }
            QPushButton#rawTerminalSecondary {
                color: #c3d2e4;
                background: #142235;
                border: 1px solid #263b54;
            }
            QPushButton#rawTerminalSecondary:hover {
                background: #1c3047;
                border-color: #42617e;
            }
            QPushButton#rawTerminalPrimary {
                color: #052015;
                background: #8cf0b4;
                border: 1px solid #a7f8c8;
            }
            QPushButton#rawTerminalPrimary:hover {
                background: #a8ffd0;
            }
            QPushButton:disabled {
                color: #627187;
                background: #111b29;
                border-color: #1d2b3c;
            }
        """)

        self._metrics_timer = QTimer(self)
        self._metrics_timer.setInterval(500)
        self._metrics_timer.timeout.connect(self._update_metrics)
        self._refresh_status()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._metrics_timer.start()
        self.visibility_changed.emit(True)

    def hideEvent(self, event) -> None:
        self._metrics_timer.stop()
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    def _add_stat_card(self, row: QHBoxLayout, label: str, value: str) -> QLabel:
        card = QFrame(self)
        card.setObjectName("rawTerminalStat")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 9)
        layout.setSpacing(4)
        label_widget = QLabel(label, card)
        label_widget.setObjectName("rawTerminalStatLabel")
        value_widget = QLabel(value, card)
        value_widget.setObjectName("rawTerminalStatValue")
        value_widget.setMinimumWidth(40)
        label_widget.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(label_widget)
        layout.addWidget(value_widget)
        row.addWidget(card, 1)
        return value_widget

    @Slot(str, bytes)
    def append_report(self, controller_name: str, report: bytes) -> None:
        """Append a packet on the UI thread; never called from the HID worker directly."""
        if not self.isVisible() or not self._capture_enabled or self._paused:
            return
        raw = bytes(report)
        line = format_raw_hid_report(controller_name, raw)
        prefix, separator, payload = line.partition("  │  ")
        scroll_bar = self.output.verticalScrollBar()
        previous_scroll = scroll_bar.value()
        follow_output = self.auto_scroll.isChecked()
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(prefix + separator, self._meta_format)
        cursor.insertText(payload + "\n", self._hex_format)
        self.output.setTextCursor(cursor)
        if follow_output:
            self.output.ensureCursorVisible()
        else:
            scroll_bar.setValue(previous_scroll)

        self._record_count += 1
        self._last_report = line
        self._last_size = len(raw)
        self._last_device = "".join(ch for ch in str(controller_name) if ch.isprintable()).strip() or "Unknown device"
        self._recent_arrivals.append(time.monotonic())
        self._packets_value.setText(f"{self._record_count:,}")
        self._last_size_value.setText(f"{self._last_size} B")
        self._device_value.setText(self._last_device[:22])
        self._device_value.setToolTip(self._last_device)
        self.copy_button.setEnabled(True)
        if self._record_count == 1:
            self._refresh_status()

    def set_capture_enabled(self, enabled: bool) -> None:
        self._capture_enabled = bool(enabled)
        self._refresh_status()

    def _refresh_status(self) -> None:
        if not self._capture_enabled:
            text, state = tr("DISABLED", self.language), "disabled"
            detail = tr("Live capture is off. Enable Raw HID debug to receive reports.", self.language)
        elif self._paused:
            text, state = tr("PAUSED", self.language), "paused"
            detail = tr("Capture is paused. Incoming reports are ignored until resumed.", self.language)
        else:
            text, state = tr("LIVE", self.language), "live"
            detail = (
                tr("Waiting for HID reports…", self.language)
                if not self._record_count
                else tr("Live capture is receiving reports.", self.language)
            )
        self.detail_label.setText(detail)
        self.status_badge.setText(text)
        self.status_badge.setProperty("state", state)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
        self.subtitle_label.setToolTip(detail)
        self.status_badge.setToolTip(detail)

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_button.setText(
            tr("Resume stream", self.language) if self._paused
            else tr("Pause stream", self.language)
        )
        self._refresh_status()

    def clear_terminal(self) -> None:
        self.output.clear()
        self._record_count = 0
        self._last_report = ""
        self._last_size = 0
        self._last_device = "—"
        self._recent_arrivals.clear()
        self._packets_value.setText("0")
        self._rate_value.setText("0.0/s")
        self._last_size_value.setText("—")
        self._device_value.setText("—")
        self._device_value.setToolTip("")
        self.copy_button.setEnabled(False)
        self._refresh_status()

    def copy_latest(self) -> None:
        if not self._last_report:
            return
        QApplication.clipboard().setText(self._last_report)

    def save_capture(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            tr("Save capture…", self.language),
            "raw-hid-capture.txt",
            "Text files (*.txt *.log);;All files (*)",
        )
        if not filename:
            return
        try:
            Path(filename).write_text(self.output.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self,
                tr("Raw HID Live Terminal", self.language),
                f'{tr("Could not save capture:", self.language)}\n{exc}',
            )

    def _update_metrics(self) -> None:
        now = time.monotonic()
        while self._recent_arrivals and now - self._recent_arrivals[0] > 2.0:
            self._recent_arrivals.popleft()
        if len(self._recent_arrivals) < 2:
            rate = 0.0
        else:
            elapsed = max(0.1, now - self._recent_arrivals[0])
            rate = (len(self._recent_arrivals) - 1) / elapsed
        self._rate_value.setText(f"{rate:.1f}/s")
