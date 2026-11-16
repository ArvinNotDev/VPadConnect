"""Lightweight cursor-following highlight for the desktop window.

The gradient is rasterized once and displayed as a small transparent QLabel.
Moving the label lets Qt repaint the old area normally; no full-window
transparent paint pass or backing-store clearing is required.
"""

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from ui.animations import animations_enabled


class CursorSpotlight(QLabel):
    RADIUS = 215
    DIAMETER = RADIUS * 2

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("cursorSpotlight")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(self.DIAMETER, self.DIAMETER)
        self.setStyleSheet(
            "QLabel#cursorSpotlight { background: transparent; border: none; }"
        )
        self.setPixmap(self._build_gradient_pixmap())

        self._position = QPointF()
        self._target = QPointF()
        self._has_position = False
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance)
        self.hide()

    @classmethod
    def _build_gradient_pixmap(cls) -> QPixmap:
        """Create the translucent spotlight once instead of repainting it per frame."""
        pixmap = QPixmap(cls.DIAMETER, cls.DIAMETER)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = QPointF(cls.RADIUS, cls.RADIUS)
        gradient = QRadialGradient(center, cls.RADIUS)
        gradient.setColorAt(0.0, QColor(34, 211, 238, 43))
        gradient.setColorAt(0.34, QColor(6, 182, 212, 25))
        gradient.setColorAt(0.72, QColor(8, 145, 178, 9))
        gradient.setColorAt(1.0, QColor(8, 145, 178, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(0, 0, cls.DIAMETER, cls.DIAMETER)

        # A restrained technical texture: fine diagonal cyan strokes and two
        # low-contrast rings, softened by the same circular clipping boundary.
        circle = QPainterPath()
        circle.addEllipse(0.5, 0.5, cls.DIAMETER - 1, cls.DIAMETER - 1)
        painter.setClipPath(circle)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(103, 232, 249, 5), 1))
        for offset in range(-cls.DIAMETER, cls.DIAMETER * 2, 12):
            painter.drawLine(offset, cls.DIAMETER, offset + cls.DIAMETER, 0)

        painter.setPen(QPen(QColor(103, 232, 249, 10), 1))
        painter.drawEllipse(
            center,
            cls.RADIUS * 0.43,
            cls.RADIUS * 0.43,
        )
        painter.setPen(QPen(QColor(103, 232, 249, 6), 1))
        painter.drawEllipse(
            center,
            cls.RADIUS * 0.76,
            cls.RADIUS * 0.76,
        )
        painter.end()
        return pixmap

    def set_target(self, position) -> None:
        target = QPointF(position)
        if not self._has_position:
            self._position = target
            self._target = target
            self._has_position = True
            self._move_to_position()
            self.show()
            self.raise_()
            return

        self._target = target
        if not animations_enabled():
            self._timer.stop()
            self._position = target
            self._move_to_position()
            return

        if not self.isVisible():
            self.show()
            self.raise_()
        if not self._timer.isActive():
            self._timer.start()

    def hide_spotlight(self) -> None:
        self._timer.stop()
        self._has_position = False
        self.hide()

    def _advance(self) -> None:
        dx = self._target.x() - self._position.x()
        dy = self._target.y() - self._position.y()
        if dx * dx + dy * dy < 1.0:
            self._position = QPointF(self._target)
            self._timer.stop()
        else:
            self._position.setX(self._position.x() + dx * 0.32)
            self._position.setY(self._position.y() + dy * 0.32)
        self._move_to_position()

    def _move_to_position(self) -> None:
        self.move(
            round(self._position.x() - self.RADIUS),
            round(self._position.y() - self.RADIUS),
        )
