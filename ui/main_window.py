import logging
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabBar,
    QSystemTrayIcon,
    QMenu,
    QApplication,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSizeGrip,
)
from PySide6.QtCore import Qt, QUrl, QSize, Signal
from PySide6.QtGui import (
    QDesktopServices, QIcon, QAction, QActionGroup, QPixmap, QPainter,
    QBrush, QPen, QColor, QFont,
)

from ui.theme_manager import ThemeManager
from ui.animations import AnimatedStackedWidget, AnimatedTabBar, ButtonHoverAnimations
from ui.icons import ICON_SIZE, icon
from ui.pages.controller_emulation import ControllerEmulation
from ui.pages.controllers import ControllersPage
from ui.pages.settings import SettingsPage
from ui.pages.web_remote import WebRemotePage
from ui.pages.hotkey import HotkeyPage
from ui.pages.profiles import ProfilesPage
from core.settings import SettingsManager
from core.profile_manager import ProfileManager

from core.utils.hotkeys import Hotkey
from core.utils.paths import data_path, resource_path
from ui.i18n import apply_translations, tr
from core.version import APP_NAME
from core.vigem import is_vigem_installed
from core.dev_logging import configure_developer_logging

logger = logging.getLogger("vpadconnect.main_window")


class MainWindow(QMainWindow):
    gyro_shortcut_requested = Signal()

    WINDOW_TITLE = APP_NAME
    WINDOW_WIDTH = 1180
    WINDOW_HEIGHT = 760
    MIN_WINDOW_WIDTH = 820
    MIN_WINDOW_HEIGHT = 540
    NAV_PAGE_INDICES = (0, 1, 3, 4, 2)
    IDX_CONTROLLER_EMULATION = 0
    IDX_HOTKEY = 1
    IDX_INPUT_TEST = 2

    def __init__(self, app: QApplication) -> None:
        super().__init__()

        # Theme & settings
        self.theme_manager = ThemeManager(app)
        self.theme_manager.apply_theme("dark")
        self.media_functions = {
                "volume up": "volume up",
                "volume down": "volume down",
                "play/pause media": "play/pause media",
                "next track": "next track",
                "previous track": "previous track",
                "volume mute": "volume mute",
            }
        self.hotkey = Hotkey(str(data_path("hotkeys.json")))
        self.settings = SettingsManager()
        self.settings.normalize()
        configure_developer_logging(self.settings)
        app.setProperty("reducedMotion", self.settings.get_ui_reduced_motion())
        self.profile_manager = ProfileManager(self.settings)
        self.profile_manager.create_default_profile()
        self.vigem_available = is_vigem_installed()
        self._applying_language = False

        # quitting flag
        self._is_quitting = False
        self._tracked_screens = []
        self._screen_signal_connected = False
        self._screen_adjusting = False
        self._preferred_window_size = QSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(self.WINDOW_TITLE)
        # Keep the shell usable in compact windows; individual settings pages
        # now scroll independently instead of clipping lower controls.
        self.setMinimumSize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)
        self.resize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        app_icon = QIcon(str(resource_path("ui", "assets", "vpadconnect-icon.ico")))
        self.setWindowIcon(app_icon)
        app.setWindowIcon(app_icon)

        self._shown_tray_hint = False
        for screen in app.screens():
            self._track_screen(screen)
        app.screenAdded.connect(self._track_screen)

        # Main application shell
        central = QWidget(self)
        central.setObjectName("app_root")
        main_layout = QVBoxLayout(central)
        self._main_layout = main_layout
        main_layout.setContentsMargins(22, 16, 22, 16)
        main_layout.setSpacing(10)
        self.setCentralWidget(central)

        # Compact, frameless title bar inspired by macOS.
        header = _DraggableTitleBar(self)
        header.setObjectName("app_header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 2, 4, 8)
        header_layout.setSpacing(10)

        window_controls = QHBoxLayout()
        window_controls.setContentsMargins(3, 0, 4, 0)
        window_controls.setSpacing(7)
        self._window_minimize = QPushButton()
        self._window_minimize.setObjectName("window_minimize")
        self._window_minimize.setFixedSize(14, 14)
        self._window_minimize.setToolTip("Minimize")
        self._window_minimize.clicked.connect(self.showMinimized)
        self._window_maximize = QPushButton()
        self._window_maximize.setObjectName("window_maximize")
        self._window_maximize.setFixedSize(14, 14)
        self._window_maximize.setToolTip("Maximize / restore")
        self._window_maximize.clicked.connect(self._toggle_window_maximized)
        self._window_close = QPushButton()
        self._window_close.setObjectName("window_close")
        self._window_close.setFixedSize(14, 14)
        self._window_close.setToolTip("Close")
        self._window_close.clicked.connect(self.close)
        for control in (self._window_close, self._window_minimize, self._window_maximize):
            window_controls.addWidget(control)

        self._brand_mark = QLabel()
        self._brand_mark.setObjectName("brand_mark")
        self._brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._brand_mark.setFixedSize(42, 42)
        logo = QPixmap(str(resource_path("ui", "assets", "vpadconnect-icon.png")))
        if not logo.isNull():
            self._brand_mark.setPixmap(logo.scaled(
                42, 42, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            logo_icon = QIcon(str(resource_path("ui", "assets", "vpadconnect-icon.ico")))
            if not logo_icon.isNull():
                self._brand_mark.setPixmap(logo_icon.pixmap(42, 42))
        header_layout.addWidget(self._brand_mark)

        brand_title = QLabel("VPadConnect")
        brand_title.setObjectName("brand_title")
        header_layout.addWidget(brand_title)
        header_layout.addStretch(1)

        self._avatar_container = QPushButton()
        self._avatar_container.setObjectName("profile_chip")
        self._avatar_container.setFlat(False)
        self._avatar_container.setCursor(Qt.CursorShape.PointingHandCursor)
        self._avatar_container.setToolTip("Switch active profile")
        self._avatar_container.setAccessibleName("Profile selector")
        self._avatar_container.setMinimumWidth(236)
        self._avatar_container.setMinimumHeight(48)
        avatar_layout = QHBoxLayout(self._avatar_container)
        avatar_layout.setContentsMargins(8, 4, 10, 4)
        avatar_layout.setSpacing(8)

        self._sidebar_avatar = _SidebarAvatar(30)
        avatar_layout.addWidget(self._sidebar_avatar, alignment=Qt.AlignmentFlag.AlignVCenter)
        profile_copy = QVBoxLayout()
        profile_copy.setContentsMargins(0, 0, 0, 0)
        profile_copy.setSpacing(1)
        self._sidebar_profile_name = QLabel("")
        self._sidebar_profile_name.setObjectName("sidebar_profile_name")
        self._sidebar_profile_name.setMinimumWidth(150)
        self._sidebar_profile_label = QLabel("No profile active")
        self._sidebar_profile_label.setObjectName("sidebar_profile_label")
        self._sidebar_profile_label.setMinimumWidth(150)
        profile_copy.addWidget(self._sidebar_profile_name)
        profile_copy.addWidget(self._sidebar_profile_label)
        avatar_layout.addLayout(profile_copy)
        self._profile_dropdown_chevron = QLabel("▾")
        self._profile_dropdown_chevron.setObjectName("profile_dropdown_chevron")
        avatar_layout.addWidget(self._profile_dropdown_chevron)
        self._profile_selector_menu = QMenu(self)
        self._profile_selector_menu.setObjectName("profile_selector_menu")
        self._profile_selector_menu.aboutToShow.connect(self._refresh_profile_menu)
        self._profile_action_group = QActionGroup(self._profile_selector_menu)
        self._profile_action_group.setExclusive(True)
        self._avatar_container.setMenu(self._profile_selector_menu)
        header_layout.addWidget(self._avatar_container)

        header_layout.addLayout(window_controls)

        main_layout.addWidget(header)

        # The feature list contains only the pages used directly during normal work.
        self.menu = AnimatedTabBar()
        self.menu.setObjectName("top_navigation")
        self.menu.setDocumentMode(True)
        self.menu.setDrawBase(False)
        self.menu.setExpanding(False)
        self.menu.setMovable(False)
        self.menu.setUsesScrollButtons(True)
        self.menu.setElideMode(Qt.TextElideMode.ElideNone)
        self.menu.setShape(QTabBar.Shape.RoundedNorth)
        for glyph, label in (
            ("gamepad", "Controller Emulation"),
            ("keyboard", "Hotkeys"),
            ("chart-line", "Input Test"),
            ("sliders", "Settings"),
            ("id-card", "Profiles"),
        ):
            self.menu.addTab(icon(glyph, "#7787a4"), label)
        self.menu.setIconSize(ICON_SIZE)
        self.menu.setMinimumHeight(38)
        self.menu.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        navigation_row = QWidget()
        navigation_layout = QHBoxLayout(navigation_row)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        navigation_layout.setSpacing(12)
        navigation_layout.addWidget(self.menu, 0, Qt.AlignmentFlag.AlignLeft)
        navigation_layout.addStretch(1)

        self.donate_button = QPushButton("Buy me a coffee")
        self.donate_button.setObjectName("nav_donate_button")
        self.donate_button.setIcon(icon("mug-hot", "#513915"))
        self.donate_button.setIconSize(ICON_SIZE)
        self.donate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.donate_button.setMinimumHeight(34)
        self.donate_button.setStyleSheet("QPushButton#nav_donate_button { color: #25202a; background: #f4c37b; border: 1px solid #ffdda2; border-radius: 9px; padding: 6px 14px; font-weight: 800; } QPushButton#nav_donate_button:hover { background: #ffdaa0; }")
        self.donate_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://reymit.ir/arvinnotdev")))
        navigation_layout.addWidget(self.donate_button, 0, Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(navigation_row)

        # Pages are kept in one stack; Profiles open from the title bar.
        self.pages = AnimatedStackedWidget()
        self.pages.setObjectName("content_stack")

        controllers_page = ControllersPage(
            self.settings, vigem_available=self.vigem_available
        )
        self.controllers_page = controllers_page
        self._keyboard_module = None
        self._gyro_shortcut_handle = None
        hotkey_page = HotkeyPage(self.hotkey)
        self.hotkey_page = hotkey_page

        self.controller_emulation_page = ControllerEmulation(
            self.settings, controllers_page, hotkey_page,
            vigem_available=self.vigem_available,
        )
        self.controller_emulation_page.vigem_recheck_requested.connect(
            self._refresh_vigem_status
        )
        self.controllers_page.vigem_recheck_requested.connect(
            self._refresh_vigem_status
        )
        self.pages.addWidget(self.controller_emulation_page)

        # Keep Web Companion as an internal service owned by the main window.
        # Pairing is initiated from Controller Emulation, not a separate page.
        self.web_remote_page = WebRemotePage(
            self.settings, controllers_page, hotkey_page,
            status_changed=self._refresh_tray_menu,
            vigem_available=self.vigem_available,
            parent=self,
        )
        self.web_remote_page.vigem_recheck_requested.connect(
            self._refresh_vigem_status
        )
        self.controller_emulation_page.set_web_remote_service(self.web_remote_page)
        self.pages.addWidget(hotkey_page)

        self.profiles_page = ProfilesPage(self.profile_manager, self.settings)
        self.profiles_page.profile_loaded.connect(self._on_profile_loaded)
        self.profiles_page.profile_changed.connect(self._refresh_profile_selector)
        self.pages.addWidget(self.profiles_page)

        self.pages.addWidget(controllers_page)

        self.settings_page = SettingsPage(
            self.theme_manager, self.settings, self.profile_manager
        )
        self.controller_emulation_page.raw_hid_report.connect(
            self.settings_page.append_raw_hid_report
        )
        self.settings_page.raw_hid_monitor_state_changed.connect(
            self.controller_emulation_page.set_raw_hid_monitor_active
        )
        self.pages.addWidget(self.settings_page)
        self.settings_page.combo_lang.currentIndexChanged.connect(
            lambda _index: self._apply_language()
        )
        self.settings_page.vibration_enabled_changed.connect(
            self.controllers_page.set_vibration_enabled
        )

        main_layout.addWidget(self.pages, 1)

        # Keep the frameless window resizable without restoring the native title bar.
        resize_row = QHBoxLayout()
        resize_row.setContentsMargins(0, 0, 0, 0)
        resize_row.setSpacing(0)
        resize_row.addStretch(1)
        self._size_grip = QSizeGrip(central)
        self._size_grip.setFixedSize(12, 12)
        resize_row.addWidget(
            self._size_grip, 0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        )
        main_layout.addLayout(resize_row)

        self.menu.currentChanged.connect(self._on_menu_index_changed)
        self.menu.setCurrentIndex(self.IDX_CONTROLLER_EMULATION)
        self.pages.setCurrentIndex(0)

        # Initialize sidebar avatar
        self._refresh_profile_selector()
        self._apply_language()

        self.gyro_shortcut_requested.connect(self.controllers_page.toggle_selected_gyro)
        self._register_gyro_shortcut()

        # Add quiet, animated hover feedback to the finished desktop interface.
        # The controller/input logic and button click handlers remain unchanged.
        self._button_hover_animations = ButtonHoverAnimations(self)

        # Tray
        self.tray_icon: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._init_tray_icon()
            app.setQuitOnLastWindowClosed(False)
        app.aboutToQuit.connect(self.shutdown)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._screen_adjusting and not self.isMaximized():
            self._preferred_window_size = event.size()
        if hasattr(self, "_main_layout"):
            compact = self.width() < 1000
            self._main_layout.setContentsMargins(
                12 if compact else 22,
                10 if compact else 16,
                12 if compact else 22,
                10 if compact else 16,
            )
            self._main_layout.setSpacing(7 if compact else 10)
        # Native tab scroll buttons preserve navigation; hide the decorative
        # donation action when the window becomes compact.
        if hasattr(self, "donate_button"):
            self.donate_button.setVisible(self.width() >= 1000)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        handle = self.windowHandle()
        if handle is not None:
            if not self._screen_signal_connected:
                handle.screenChanged.connect(self._on_screen_changed)
                self._screen_signal_connected = True
            self._on_screen_changed(handle.screen() or self.screen())

    def _track_screen(self, screen) -> None:
        if screen is None or screen in self._tracked_screens:
            return
        self._tracked_screens.append(screen)
        screen.availableGeometryChanged.connect(self._on_screen_metrics_changed)
        screen.logicalDotsPerInchChanged.connect(self._on_screen_metrics_changed)

    def _on_screen_metrics_changed(self, *_args) -> None:
        handle = self.windowHandle()
        screen = handle.screen() if handle is not None else self.screen()
        self._on_screen_changed(screen)

    def _on_screen_changed(self, screen) -> None:
        if screen is None:
            return
        self._track_screen(screen)
        available = screen.availableGeometry()
        self.setMinimumSize(
            min(self.MIN_WINDOW_WIDTH, max(1, available.width())),
            min(self.MIN_WINDOW_HEIGHT, max(1, available.height())),
        )
        if self.isMaximized():
            return

        target_size = QSize(
            min(self._preferred_window_size.width(), available.width()),
            min(self._preferred_window_size.height(), available.height()),
        )
        if self.size() != target_size:
            self._screen_adjusting = True
            self.resize(target_size)
            self._screen_adjusting = False

        # Use Qt's logical desktop coordinates so mixed-DPI screens need no
        # physical-pixel conversions. Keep the title bar reachable if a
        # display is removed or its work area changes.
        frame = self.frameGeometry()
        visible_width = min(160, max(1, frame.width()))
        min_x = available.left() - frame.width() + visible_width
        max_x = available.right() - visible_width + 1
        max_y = max(available.top(), available.bottom() - 52 + 1)
        x = min(max(frame.left(), min_x), max_x)
        y = min(max(frame.top(), available.top()), max_y)
        if x != frame.left() or y != frame.top():
            self.move(x, y)

    # --------------------
    # ViGEmBus prerequisite
    # --------------------

    def _refresh_vigem_status(self) -> None:
        """Refresh all UI gates after the user installs the optional driver."""
        available = is_vigem_installed()
        self.vigem_available = available
        self.controller_emulation_page.set_vigem_available(available)
        self.controllers_page.set_vigem_available(available)
        self.web_remote_page.set_vigem_available(available)
        self._refresh_tray_menu()

    def _register_gyro_shortcut(self) -> None:
        """Install the global Ctrl+Shift+G toggle for the selected DualSense."""
        try:
            import keyboard

            self._keyboard_module = keyboard
            self._gyro_shortcut_handle = keyboard.add_hotkey(
                "ctrl+shift+g",
                self.gyro_shortcut_requested.emit,
                suppress=False,
                trigger_on_release=True,
            )
            self.controllers_page.set_gyro_shortcut_available(True)
        except Exception as exc:
            self.controllers_page.set_gyro_shortcut_available(False)
            logger.warning("Could not register Ctrl+Shift+G gyro shortcut: %s", exc)

    # --------------------
    # Menu
    # --------------------

    def _on_menu_index_changed(self, index: int) -> None:
        if 0 <= index < len(self.NAV_PAGE_INDICES):
            self.pages.setCurrentIndex(self.NAV_PAGE_INDICES[index])

    def _toggle_window_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self._size_grip.setVisible(True)
            handle = self.windowHandle()
            self._on_screen_changed(
                handle.screen() if handle is not None else self.screen()
            )
        else:
            self.showMaximized()
            self._size_grip.setVisible(False)

    # --------------------
    # Tray
    # --------------------

    def _init_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray_icon = QSystemTrayIcon(self)
        icon = QIcon(str(resource_path("ui", "assets", "vpadconnect-icon.ico")))
        if icon.isNull():
            icon = QIcon.fromTheme("applications-system")
        tray_icon.setIcon(icon)
        tray_icon.setToolTip(self.WINDOW_TITLE)
        self.tray_icon = tray_icon
        self._create_tray_menu()
        tray_icon.activated.connect(self._on_tray_activated)
        tray_icon.show()
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(False)

    def _create_tray_menu(self) -> None:
        if self.tray_icon is None:
            return
        menu = QMenu(self)
        self._tray_menu = menu
        self._tray_status_action = QAction("Web Companion: stopped", menu)
        self._tray_status_action.setEnabled(False)
        menu.addAction(self._tray_status_action)
        menu.addSeparator()

        self._tray_show_action = QAction("Show window", menu)
        self._tray_show_action.triggered.connect(self._show_from_tray)
        menu.addAction(self._tray_show_action)
        self._tray_hide_action = QAction("Hide window", menu)
        self._tray_hide_action.triggered.connect(self.hide)
        menu.addAction(self._tray_hide_action)
        menu.addSeparator()
        for label, index in (
            ("Controller Emulation", self.IDX_CONTROLLER_EMULATION),
            ("Hotkeys", self.IDX_HOTKEY),
            ("Input Test", self.IDX_INPUT_TEST),
        ):
            action = QAction(label, menu)
            action.triggered.connect(
                lambda checked=False, target=index: self._show_page_from_tray(target)
            )
            menu.addAction(action)

        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(quit_action)
        menu.aboutToShow.connect(self._refresh_tray_menu)
        self.tray_icon.setContextMenu(menu)
        self._refresh_tray_menu()

    def _refresh_tray_menu(self) -> None:
        if self.tray_icon is None:
            return
        web_server = getattr(getattr(self, "web_remote_page", None), "web_server", None)
        web_running = bool(web_server and web_server.running)
        web_count = int(web_server.client_count) if web_server else 0
        mapped_count = len(getattr(self.controller_emulation_page, "mappers", {}))
        self._tray_status_action.setText(
            f"Web Companion: {'running' if web_running else 'stopped'} · "
            f"Browsers: {web_count} · Mapped: {mapped_count}"
        )
        self.tray_icon.setToolTip(
            f"{self.WINDOW_TITLE} — Web Companion "
            f"{'running' if web_running else 'stopped'}"
        )
        self._tray_hide_action.setEnabled(self.isVisible())

    def _on_profile_loaded(self, profile_name: str) -> None:
        """Called when a profile is activated from the Profiles page."""
        self._refresh_profile_selector()
        self.settings_page.reload_from_settings()
        # Reload theme in case it changed
        try:
            theme = self.settings.get_ui_theme()
            self.theme_manager.apply_theme(theme)
        except Exception:
            pass

    def _refresh_profile_selector(self) -> None:
        """Update the active profile chip and its available-profile menu."""
        name = self.profile_manager.get_active_profile_name()
        try:
            language = self.settings.get_ui_language()
        except Exception:
            language = "eng"
        if name:
            img_path = self.profile_manager.get_profile_image_path(name)
            self._sidebar_avatar.set_image(img_path)
            self._sidebar_profile_name.setText(name)
            self._sidebar_profile_label.setText(tr("Active profile", language))
        else:
            self._sidebar_avatar.set_image(None)
            self._sidebar_profile_name.setText("")
            self._sidebar_profile_label.setText(tr("No profile active", language))
        self._refresh_profile_menu()

    def _refresh_profile_menu(self) -> None:
        menu = getattr(self, "_profile_selector_menu", None)
        if menu is None:
            return
        for old_action in self._profile_action_group.actions():
            self._profile_action_group.removeAction(old_action)
        menu.clear()
        active_name = self.profile_manager.get_active_profile_name()
        for profile in self.profile_manager.list_profiles():
            name = profile.get("name", "")
            if not name:
                continue
            action = QAction(name, menu)
            action.setCheckable(True)
            action.setChecked(name == active_name)
            if name == active_name:
                font = action.font()
                font.setWeight(QFont.Weight.DemiBold)
                action.setFont(font)
            image_path = self.profile_manager.get_profile_image_path(name)
            if image_path:
                action.setIcon(QIcon(image_path))
            else:
                action.setIcon(icon("id-card", "#7486a6"))
            action.triggered.connect(
                lambda checked=False, selected=name: self._switch_profile(selected)
            )
            self._profile_action_group.addAction(action)
            menu.addAction(action)

    def _switch_profile(self, name: str) -> None:
        """Activate a profile selected from the title-bar dropdown."""
        if name == self.profile_manager.get_active_profile_name():
            return
        if self.profile_manager.activate_profile(name):
            self.profiles_page.refresh_list()
            self._on_profile_loaded(name)

    def _apply_language(self) -> None:
        """Apply the selected UI language without changing layout direction."""
        if self._applying_language:
            return
        self._applying_language = True
        try:
            language = self.settings_page.combo_lang.currentData()
            if language not in ("eng", "fa", "es"):
                language = self.settings.get_ui_language()
            self.settings.set_ui_language(language or "eng")
            self.settings.save()
        except Exception:
            language = "eng"
        try:
            apply_translations(self, language)
            self.profiles_page.refresh_list()
            self._sidebar_profile_label.setText(
                tr(
                    "Active profile"
                    if self.profile_manager.get_active_profile_name()
                    else "No profile active",
                    language,
                )
            )
        finally:
            self._applying_language = False

    def _show_page_from_tray(self, index: int) -> None:
        self.menu.setCurrentIndex(index)
        self._show_from_tray()

    def _quit_from_tray(self) -> None:
        self._is_quitting = True
        QApplication.quit()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:

        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):

            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self._show_from_tray()

    def _show_from_tray(self) -> None:

        self.show()

        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)

        self.activateWindow()
        self.raise_()
        self._refresh_tray_menu()

    def shutdown(self) -> None:
        if getattr(self, "_shutdown_complete", False):
            return
        self._shutdown_complete = True
        if self._keyboard_module is not None and self._gyro_shortcut_handle is not None:
            try:
                self._keyboard_module.remove_hotkey(self._gyro_shortcut_handle)
            except Exception:
                logger.debug("Could not unregister gyro keyboard shortcut", exc_info=True)
            self._gyro_shortcut_handle = None
        try:
            self.web_remote_page.shutdown()
        except Exception as exc:
            logger.exception("Web Companion shutdown failed")
        try:
            self.controller_emulation_page.shutdown()
        except Exception as exc:
            logger.exception("HID shutdown failed")
        try:
            self.controllers_page.refresh_timer.stop()
        except Exception:
            pass
        if self.tray_icon is not None:
            self.tray_icon.hide()

    # --------------------
    # Close behavior
    # --------------------

    def closeEvent(self, event) -> None:
        # If we are quitting explicitly (from menu or tray), exit
        if self._is_quitting:
            self.shutdown()
            event.accept()
            return

        # Otherwise, go to tray (if available)
        if self.tray_icon is not None:

            self.hide()

            if not self._shown_tray_hint:
                try:
                    self.tray_icon.showMessage(
                        self.WINDOW_TITLE,
                        "Application is still running in the tray. "
                        "Use the tray icon to restore or quit.",
                    )
                except Exception:
                    pass

                self._shown_tray_hint = True

            event.ignore()
        else:
            self.shutdown()
            super().closeEvent(event)


# ------------------------------------------------------------------
# Frameless title bar drag behavior
# ------------------------------------------------------------------

class _DraggableTitleBar(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self._drag_offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._window.isMaximized():
            self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            cursor_position = event.globalPosition().toPoint()
            target_position = cursor_position - self._drag_offset

            # Keep the draggable title bar inside the monitor's work area.
            # availableGeometry excludes the taskbar/dock, so the controls
            # remain reachable even when the user drags the window downward.
            screen = QApplication.screenAt(cursor_position) or self._window.screen()
            if screen is not None:
                available = screen.availableGeometry()
                frame = self._window.frameGeometry()
                titlebar_height = max(self.height(), 52)
                min_y = available.top()
                max_y = max(min_y, available.bottom() - titlebar_height + 1)
                target_position.setY(
                    min(max(target_position.y(), min_y), max_y)
                )

                # Keep a useful part of the title bar reachable horizontally.
                visible_width = min(160, max(1, self.width()))
                min_x = available.left() - frame.width() + visible_width
                max_x = available.right() - visible_width + 1
                target_position.setX(
                    min(max(target_position.x(), min_x), max_x)
                )

            self._window.move(target_position)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._window._toggle_window_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


# ------------------------------------------------------------------
# Sidebar avatar widget
# ------------------------------------------------------------------

class _SidebarAvatar(QLabel):
    """Circular avatar displayed at the top of the sidebar."""

    def __init__(self, size: int = 64, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setStyleSheet("background: transparent;")
        self._pixmap: QPixmap | None = None
        self._placeholder_icon = icon("gamepad", "#9aaecb")

    def set_image(self, path: str | None) -> None:
        if path and Path(path).is_file():
            self._pixmap = QPixmap(path)
        else:
            self._pixmap = None
        self.update()

    def paintEvent(self, event) -> None:
        s = self._size
        if self._pixmap is None or self._pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QBrush(QColor("#3a3a5a")))
            painter.setPen(QPen(QColor("#555577"), 2))
            painter.drawEllipse(1, 1, s - 2, s - 2)
            placeholder = self._placeholder_icon.pixmap(s // 2, s // 2)
            painter.drawPixmap(
                (s - placeholder.width()) // 2,
                (s - placeholder.height()) // 2,
                placeholder,
            )
            painter.end()
            return

        scaled = self._pixmap.scaled(
            s, s, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        x = (scaled.width() - s) // 2
        y = (scaled.height() - s) // 2
        cropped = scaled.copy(x, y, s, s)

        mask = QPixmap(s, s)
        mask.fill(QColor(0, 0, 0, 0))
        m = QPainter(mask)
        m.setRenderHint(QPainter.Antialiasing)
        m.setBrush(QBrush(QColor(0, 0, 0)))
        m.setPen(Qt.NoPen)
        m.drawEllipse(0, 0, s, s)
        m.end()
        cropped.setMask(mask.mask())

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, cropped)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#5a5af0"), 2))
        painter.drawEllipse(1, 1, s - 2, s - 2)
        painter.end()

