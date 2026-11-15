from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.version import APP_NAME, DEVELOPER_NAME, GITHUB_URL, REPOSITORY_URL, VERSION
from ui.icons import SMALL_ICON_SIZE, icon


class AboutPage(QWidget):
    """Friendly, compact product/about page."""

    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("about_hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 28, 28, 28)
        hero_layout.setSpacing(8)

        badge = QLabel("VPADCONNECT")
        badge.setObjectName("about_badge")
        hero_layout.addWidget(badge)

        title = QLabel(APP_NAME)
        title.setObjectName("about_title")
        title_layout = QHBoxLayout()
        title_layout.addWidget(title)
        title_layout.addStretch()
        version_label = QLabel(f"v{VERSION}")
        version_label.setObjectName("about_version")
        title_layout.addWidget(version_label, alignment=Qt.AlignTop)
        hero_layout.addLayout(title_layout)

        tagline = QLabel(
            "Virtual Gamepad. Connected Control."
        )
        tagline.setObjectName("about_tagline")
        tagline.setWordWrap(True)
        hero_layout.addWidget(tagline)
        root.addWidget(hero)

        info = QFrame()
        info.setObjectName("about_info_card")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(22, 20, 22, 20)
        info_layout.setSpacing(10)

        heading = QLabel("Built for controller customization")
        heading.setObjectName("about_section_title")
        info_layout.addWidget(heading)

        body = QLabel(
            "VPadConnect helps you connect physical HID controllers "
            "to virtual Xbox 360 devices with flexible profiles, hotkeys, mouse mode, "
            "remote gamepad support, and HidHide integration."
        )
        body.setWordWrap(True)
        body.setObjectName("about_body")
        info_layout.addWidget(body)

        developer = QLabel(f"Developer: {DEVELOPER_NAME}")
        developer.setObjectName("about_meta")
        info_layout.addWidget(developer)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.github_button = QPushButton("GitHub Profile")
        self.github_button.setObjectName("about_primary_btn")
        self.github_button.setIcon(icon("code-branch", "#ffffff"))
        self.github_button.setIconSize(SMALL_ICON_SIZE)
        self.github_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL))
        )
        buttons.addWidget(self.github_button)

        self.repo_button = QPushButton("Project Repository")
        self.repo_button.setObjectName("about_secondary_btn")
        self.repo_button.setIcon(icon("code", "#657596"))
        self.repo_button.setIconSize(SMALL_ICON_SIZE)
        self.repo_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(REPOSITORY_URL))
        )
        buttons.addWidget(self.repo_button)
        buttons.addStretch()
        info_layout.addLayout(buttons)
        root.addWidget(info)

        tip = QLabel(
            "Tip: Create a profile for each game and switch between them in seconds."
        )
        tip.setObjectName("about_tip")
        tip.setWordWrap(True)
        root.addWidget(tip)
        root.addStretch()
