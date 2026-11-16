from pathlib import Path

from PySide6.QtWidgets import QWidget

from core.utils.paths import resource_path

class ThemeManager:
    def __init__(self, app, base_path=None):
        self.app = app
        self.base_path = (
            resource_path("ui", "themes")
            if base_path is None
            else Path(base_path)
        )
        self._cache = {}

    def apply_theme(self, theme_name: str):
        base_qss = self._read(self.base_path / f"{theme_name}.qss")
        self.base_qss = base_qss
        self.current_theme = theme_name
        self.app.setProperty("vpadTheme", theme_name)
        self.app.setStyleSheet(self.base_qss)

        # Some rich cards own compact local stylesheets. Let those widgets
        # refresh their palettes whenever the application theme changes.
        for window in self.app.topLevelWidgets():
            for widget in (window, *window.findChildren(QWidget)):
                apply_widget_theme = getattr(widget, "apply_theme", None)
                if callable(apply_widget_theme):
                    try:
                        apply_widget_theme(theme_name)
                    except Exception:
                        import logging
                        logging.getLogger("vpadconnect.theme").exception(
                            "Could not apply %s theme to %s",
                            theme_name,
                            type(widget).__name__,
                        )

    def apply_component(self, component_name: str):
        """Append a component QSS (e.g. 'dashboard') to base and apply."""
        comp_path = self.base_path / "components" / f"{component_name}.qss"
        comp_qss = self._read(comp_path)
        composed = (self.base_qss or "") + "\n\n" + (comp_qss or "")
        self.app.setStyleSheet(composed)

    def clear_component(self):
        """Revert to base theme only."""
        self.app.setStyleSheet(self.base_qss or "")
        
    def _read(self, path):
        if path in self._cache:
            return self._cache[path]
        path = Path(path)
        if not path.exists():
            return ""
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        self._cache[path] = txt
        return txt
