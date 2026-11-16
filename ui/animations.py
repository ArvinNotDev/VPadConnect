"""Small, reusable Qt animations for the VPadConnect desktop UI.

Transitions are deliberately short and use snapshots for outgoing pages so the
actual controller/HID widgets are not forced through an expensive opacity effect.
Set VPADCONNECT_REDUCED_MOTION=1 to disable decorative animations.
"""
from __future__ import annotations

import os

from PySide6.QtCore import (
    QEvent,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QObject,
    Property,
)
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTabBar,
)


def animations_enabled() -> bool:
    """Return whether nonessential UI motion is enabled for this process."""
    if os.environ.get("VPADCONNECT_REDUCED_MOTION", "").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        return False

    app = QApplication.instance()
    if app is not None and bool(app.property("reducedMotion")):
        return False
    return True


class AnimatedDialog(QDialog):
    """Modal dialog with a lightweight, safe entrance transition.

    Closing stays synchronous: QDialog.exec() callers can immediately finish
    their modal flow without waiting for a QObject animation to finish.
    """

    OPEN_MS = 135

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dialog_animation = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._stop_dialog_animation()
        self.setEnabled(True)
        self.setWindowOpacity(1.0)
        if not animations_enabled():
            return

        # Keep the entrance effect deliberately simple. Animating top-level
        # geometry while a nested QDialog.exec() loop is active can race with
        # native window close/reject handling on Windows.
        self.setWindowOpacity(0.0)
        group = QParallelAnimationGroup(self)
        opacity = QPropertyAnimation(self, b"windowOpacity", group)
        opacity.setDuration(self.OPEN_MS)
        opacity.setStartValue(0.0)
        opacity.setEndValue(1.0)
        opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.finished.connect(
            lambda active=group: self._finish_dialog_open(active)
        )
        self._dialog_animation = group
        group.start()

    def done(self, result: int) -> None:
        # accept(), reject(), Cancel, and the window close button all converge
        # here. Stop any entrance animation and finish the modal result now.
        self._stop_dialog_animation()
        self.setWindowOpacity(1.0)
        super().done(result)

    def hideEvent(self, event) -> None:
        self._stop_dialog_animation()
        self.setWindowOpacity(1.0)
        super().hideEvent(event)

    def _stop_dialog_animation(self) -> None:
        group = self._dialog_animation
        self._dialog_animation = None
        if group is None:
            return
        group.stop()
        group.deleteLater()

    def _finish_dialog_open(self, group) -> None:
        if self._dialog_animation is not group:
            return
        self._dialog_animation = None
        self.setWindowOpacity(1.0)
        group.deleteLater()


class AnimatedTabBar(QTabBar):
    """A native QTabBar with a smoothly moving indigo-to-cyan active indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._indicator_rect = QRect()
        self._indicator_animation = QPropertyAnimation(
            self, b"indicatorRect", self
        )
        self._indicator_animation.setDuration(260)
        self._indicator_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.currentChanged.connect(self._animate_indicator_to_index)

    def get_indicator_rect(self) -> QRect:
        return QRect(self._indicator_rect)

    def set_indicator_rect(self, rect: QRect) -> None:
        if rect == self._indicator_rect:
            return
        self._indicator_rect = QRect(rect)
        self.update()

    indicatorRect = Property(QRect, get_indicator_rect, set_indicator_rect)

    def _target_indicator_rect(self, index: int) -> QRect:
        if index < 0 or index >= self.count():
            center = self._indicator_rect.center().x() if not self._indicator_rect.isNull() else self.width() // 2
            return QRect(center, max(0, self.height() - 3), 0, 3)

        tab_rect = self.tabRect(index)
        if tab_rect.width() <= 0:
            return QRect()

        inset = min(14, max(6, tab_rect.width() // 5))
        width = max(12, tab_rect.width() - 2 * inset)
        return QRect(
            tab_rect.left() + (tab_rect.width() - width) // 2,
            max(0, self.height() - 3),
            width,
            3,
        )

    def _animate_indicator_to_index(self, index: int) -> None:
        target = self._target_indicator_rect(index)
        self._indicator_animation.stop()

        if (
            not animations_enabled()
            or not self.isVisible()
            or self._indicator_rect.isNull()
            or target.isNull()
        ):
            self._indicator_rect = target
            self.update()
            return

        self._indicator_animation.setStartValue(self._indicator_rect)
        self._indicator_animation.setEndValue(target)
        self._indicator_animation.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Tab geometry is final after the bar is shown, so paint the initial
        # underline at the active tab instead of animating from an empty rect.
        self._indicator_rect = self._target_indicator_rect(self.currentIndex())
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._indicator_animation.stop()
        self._indicator_rect = self._target_indicator_rect(self.currentIndex())
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        rect = self._indicator_rect
        if rect.width() <= 0 or rect.height() <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, QColor("#6572ff"))
        gradient.setColorAt(0.55, QColor("#8270ff"))
        gradient.setColorAt(1.0, QColor("#38cde1"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 1.5, 1.5)


class AnimatedStackedWidget(QStackedWidget):
    """A page stack with a brief snapshot cross-fade and low-distance slide."""

    TRANSITION_MS = 245
    SLIDE_DISTANCE = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_transition = None

    def setCurrentIndex(self, index: int) -> None:
        if index == self.currentIndex():
            return

        # Complete an interrupted transition before taking the next snapshot.
        self._finish_transition()

        old_index = self.currentIndex()
        old_page = self.currentWidget()
        can_animate = (
            animations_enabled()
            and self.isVisible()
            and old_page is not None
            and 0 <= index < self.count()
        )
        snapshot = None
        old_geometry = None
        if can_animate:
            try:
                old_geometry = old_page.geometry()
                snapshot = old_page.grab()
            except RuntimeError:
                snapshot = None

        super().setCurrentIndex(index)
        new_page = self.currentWidget()

        if (
            not can_animate
            or new_page is None
            or old_page is new_page
            or snapshot is None
            or snapshot.isNull()
        ):
            return

        target_pos = new_page.pos()
        direction = 1 if index > old_index else -1

        # The old page is a lightweight pixmap overlay; live page widgets remain
        # normally rendered underneath it throughout the transition.
        overlay = QLabel(self)
        overlay.setObjectName("page_transition_overlay")
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        overlay.setStyleSheet("background: transparent; border: none; padding: 0;")
        overlay.setPixmap(snapshot)
        overlay.setGeometry(old_geometry or self.rect())

        overlay_effect = QGraphicsOpacityEffect(overlay)
        overlay_effect.setOpacity(1.0)
        overlay.setGraphicsEffect(overlay_effect)

        new_page.move(target_pos + QPoint(direction * self.SLIDE_DISTANCE, 0))
        new_page.show()
        overlay.show()
        overlay.raise_()

        group = QParallelAnimationGroup(self)
        fade = QPropertyAnimation(overlay_effect, b"opacity", group)
        fade.setDuration(self.TRANSITION_MS)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        outgoing = QPropertyAnimation(overlay, b"pos", group)
        outgoing.setDuration(self.TRANSITION_MS)
        outgoing.setStartValue(overlay.pos())
        outgoing.setEndValue(overlay.pos() - QPoint(direction * self.SLIDE_DISTANCE, 0))
        outgoing.setEasingCurve(QEasingCurve.Type.OutCubic)

        incoming = QPropertyAnimation(new_page, b"pos", group)
        incoming.setDuration(self.TRANSITION_MS)
        incoming.setStartValue(new_page.pos())
        incoming.setEndValue(target_pos)
        incoming.setEasingCurve(QEasingCurve.Type.OutCubic)

        transition = {
            "group": group,
            "overlay": overlay,
            "page": new_page,
            "target_pos": target_pos,
        }
        self._active_transition = transition
        group.finished.connect(
            lambda current=transition: self._complete_transition(current)
        )
        group.start()

    def resizeEvent(self, event) -> None:
        if self._active_transition is not None:
            self._finish_transition()
        super().resizeEvent(event)

    def _complete_transition(self, transition) -> None:
        if self._active_transition is not transition:
            return
        self._active_transition = None

        page = transition["page"]
        if self.indexOf(page) >= 0:
            page.move(transition["target_pos"])

        overlay = transition["overlay"]
        overlay.setGraphicsEffect(None)
        overlay.hide()
        overlay.deleteLater()
        transition["group"].deleteLater()

    def _finish_transition(self) -> None:
        transition = self._active_transition
        if transition is None:
            return
        self._active_transition = None

        group = transition["group"]
        group.stop()

        page = transition["page"]
        if self.indexOf(page) >= 0:
            page.move(transition["target_pos"])

        overlay = transition["overlay"]
        overlay.setGraphicsEffect(None)
        overlay.hide()
        overlay.deleteLater()
        group.deleteLater()


class ButtonHoverAnimations(QObject):
    """Adds a restrained animated glow on hover without changing button styles.

    A completed Qt animation group is deleted by deleteLater(). Keep no live
    reference to that group after completion; future enter/leave events can then
    safely start a fresh animation without touching a deleted C++ object.
    """

    def __init__(self, root: QObject):
        super().__init__(root)
        self._root = root
        self._active = {}
        app = QApplication.instance()
        if app is not None:
            # Application-level filtering also covers controller widgets that
            # are created later, after a device is added to the emulation list.
            app.installEventFilter(self)
        else:
            for button in root.findChildren(QPushButton):
                button.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if not isinstance(watched, QPushButton):
            return False
        try:
            if not self._root.isAncestorOf(watched):
                return False
        except RuntimeError:
            # A C++ widget may be destroyed while Qt is dispatching events.
            return False

        if event.type() == QEvent.Type.Enter:
            self._animate_hover(watched, True)
        elif event.type() == QEvent.Type.Leave:
            self._animate_hover(watched, False)
        elif event.type() == QEvent.Type.Destroy:
            self._discard_button(watched)
        return False

    @staticmethod
    def _stop_group(record) -> None:
        """Stop and schedule a group for deletion, tolerating Qt-owned deletion."""
        group = record.get("group")
        # Clear the Python reference first so nested/queued events cannot reuse it.
        record["group"] = None
        if group is None:
            return
        try:
            group.stop()
        except RuntimeError:
            pass
        try:
            group.deleteLater()
        except RuntimeError:
            pass

    def _discard_button(self, button) -> None:
        record = self._active.pop(button, None)
        if record is None:
            return
        self._stop_group(record)

    def _remove_effect(self, button, effect) -> None:
        try:
            if button.graphicsEffect() is effect:
                button.setGraphicsEffect(None)
        except RuntimeError:
            # The button can disappear during window/page teardown.
            pass

    def _animate_hover(self, button: QPushButton, hovered: bool) -> None:
        if hovered and (not animations_enabled() or not button.isEnabled()):
            return
        try:
            if button.width() < 34 or button.height() < 26:
                return
            object_name = button.objectName()
        except RuntimeError:
            return
        if object_name in {
            "window_minimize", "window_maximize", "window_close",
        }:
            return

        record = self._active.get(button)
        if not hovered and not animations_enabled():
            if record is not None:
                self._stop_group(record)
                self._remove_effect(button, record["effect"])
                self._active.pop(button, None)
            return

        if record is None:
            try:
                # Respect effects owned by another part of the interface.
                if button.graphicsEffect() is not None:
                    return
                effect = QGraphicsDropShadowEffect(button)
                effect.setOffset(0, 2)
                effect.setBlurRadius(0)
                effect.setColor(QColor(99, 91, 255, 0))
                button.setGraphicsEffect(effect)
            except RuntimeError:
                return
            record = {"effect": effect, "group": None}
            self._active[button] = record
        else:
            effect = record["effect"]
            self._stop_group(record)
            try:
                if button.graphicsEffect() is not effect:
                    # The button's effect was replaced externally. Do not animate
                    # a stale effect or overwrite the newer owner's effect.
                    self._active.pop(button, None)
                    return
            except RuntimeError:
                self._active.pop(button, None)
                return

        try:
            group = QParallelAnimationGroup(self)
            blur = QPropertyAnimation(effect, b"blurRadius", group)
            blur.setDuration(175)
            blur.setStartValue(effect.blurRadius())
            blur.setEndValue(12.0 if hovered else 0.0)
            blur.setEasingCurve(QEasingCurve.Type.OutCubic)

            color = QPropertyAnimation(effect, b"color", group)
            color.setDuration(175)
            color.setStartValue(effect.color())
            color.setEndValue(QColor(99, 91, 255, 85 if hovered else 0))
            color.setEasingCurve(QEasingCurve.Type.OutCubic)
        except RuntimeError:
            self._active.pop(button, None)
            return

        record["group"] = group
        group.finished.connect(
            lambda target=button, current_effect=effect,
                   current_group=group, active=hovered:
            self._finish_hover(target, current_effect, current_group, active)
        )
        group.start()

    def _finish_hover(self, button, effect, group, hovered: bool) -> None:
        record = self._active.get(button)
        if record is None or record.get("group") is not group:
            return

        # Do not retain the group in the record: deleteLater() means its wrapped
        # C++ instance may already be gone by the next mouse-enter/leave event.
        record["group"] = None
        try:
            group.deleteLater()
        except RuntimeError:
            pass

        if not hovered:
            self._remove_effect(button, effect)
            self._active.pop(button, None)
