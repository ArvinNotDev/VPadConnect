"""Lightweight cursor-following highlight for the desktop window."""

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from ui.animations import animations_enabled


class CursorSpotlight(QWidget):
    RADIUS = 185

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent; border: none;")

        self._position = QPointF()
        self._target = QPointF()
        self._has_position = False
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance)
        self.hide()

    def set_target(self, position) -> None:
        target = QPointF(position)
        if not self._has_position:
            self._position = target
            self._target = target
            self._has_position = True
            self.show()
            self.raise_()
            self._update_area(target)
            return

        self._target = target
        if not animations_enabled():
            previous = QPointF(self._position)
            self._position = target
            self._update_area(previous, target)
            self.show()
            self.raise_()
            return

        self.show()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start()

    def hide_spotlight(self) -> None:
        self._timer.stop()
        self._has_position = False
        self.hide()

    def _advance(self) -> None:
        previous = QPointF(self._position)
        dx = self._target.x() - self._position.x()
        dy = self._target.y() - self._position.y()
        if dx * dx + dy * dy < 1.0:
            self._position = QPointF(self._target)
            self._timer.stop()
        else:
            self._position.setX(self._position.x() + dx * 0.32)
            self._position.setY(self._position.y() + dy * 0.32)
        self._update_area(previous, self._position)

    def _update_area(self, *positions: QPointF) -> None:
        dirty = None
        for position in positions:
            rect = QRectF(
                position.x() - self.RADIUS - 2,
                position.y() - self.RADIUS - 2,
                self.RADIUS * 2 + 4,
                self.RADIUS * 2 + 4,
            ).toAlignedRect()
            dirty = rect if dirty is None else dirty.united(rect)
        if dirty is not None:
            self.update(dirty.intersected(self.rect()))

    def paintEvent(self, event) -> None:
        if not self._has_position:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(event.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        gradient = QRadialGradient(self._position, self.RADIUS)
        gradient.setColorAt(0.0, QColor(34, 197, 94, 38))
        gradient.setColorAt(0.48, QColor(34, 197, 94, 19))
        gradient.setColorAt(1.0, QColor(34, 197, 94, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(
            QRectF(
                self._position.x() - self.RADIUS,
                self._position.y() - self.RADIUS,
                self.RADIUS * 2,
                self.RADIUS * 2,
            )
        )
