"""Shared Font Awesome icons for the desktop interface."""

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
import qtawesome as qta


ICON_SIZE = QSize(16, 16)
SMALL_ICON_SIZE = QSize(14, 14)


def icon(name: str, color: str = "#7787a4") -> QIcon:
    """Return a consistently styled Font Awesome 6 solid icon."""
    return qta.icon(f"fa6s.{name}", color=color)


def battery_icon_name(percent: int | None, charging: bool = False) -> str:
    """Map a reported battery level to a matching status icon."""
    if charging:
        return "bolt"
    if percent is None or percent < 25:
        return "battery-empty" if percent is None else "battery-quarter"
    if percent < 50:
        return "battery-half"
    if percent < 75:
        return "battery-three-quarters"
    return "battery-full"
