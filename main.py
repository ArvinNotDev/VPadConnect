"""VPadConnect Windows desktop application entry point."""
import sys


def main():
    from PySide6.QtWidgets import QApplication
    from core.utils.paths import APP_NAME, initialize_storage

    app = QApplication(sys.argv)
    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    initialize_storage()

    # Import UI modules after application metadata and storage are established;
    # several UI modules resolve persistent-data paths at import time.
    from ui.main_window import MainWindow

    window = MainWindow(app)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
