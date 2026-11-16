"""VPadConnect Windows desktop application entry point."""
import sys


def _get_bootloader_splash():
    """Return the optional PyInstaller splash client when it is available."""
    try:
        import pyi_splash
    except Exception:
        return None

    try:
        return pyi_splash if pyi_splash.is_alive() else None
    except Exception:
        return None


def _update_splash(splash, message: str) -> None:
    if splash is None:
        return
    try:
        splash.update_text(message)
    except Exception:
        pass


def _close_splash(splash) -> None:
    if splash is None:
        return
    try:
        splash.close()
    except Exception:
        pass


def main():
    splash = _get_bootloader_splash()
    _update_splash(splash, "Preparing VPadConnect...")

    from PySide6.QtWidgets import QApplication
    from core.utils.paths import APP_NAME, initialize_storage

    app = QApplication(sys.argv)
    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    _update_splash(splash, "Preparing your settings...")
    initialize_storage()

    # Import UI modules after application metadata and storage are established;
    # several UI modules resolve persistent-data paths at import time.
    _update_splash(splash, "Loading the main window...")
    from ui.main_window import MainWindow

    window = MainWindow(app)
    window.show()
    # Process the initial paint before closing the bootloader splash. This keeps
    # the splash visible through construction without inserting a fixed delay.
    app.processEvents()
    _close_splash(splash)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
