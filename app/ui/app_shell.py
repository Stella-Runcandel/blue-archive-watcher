from PyQt6.QtWidgets import (
    QWidget,
    QStackedLayout,
    QHBoxLayout,
    QFileDialog,
    QApplication,
    QStyle,
)
from PyQt6.QtGui import QIcon, QShortcut, QKeySequence
from pathlib import Path

from PyQt6.QtCore import QSettings

from app.ui.nav_bar import NavBar
from app.ui.panels.dashboard import DashboardPanel
from app.controllers.navigation_controller import NavigationController
from app.ui.panels.references import ReferencesPanel
from app.ui.panels.profile_selector import ProfileSelectorPanel
from app.ui.panels.debug import DebugPanel
from app.ui.panels.frames import FramesPanel


class AppShell(QWidget):
    def __init__(self):
        super().__init__()

        self.settings = QSettings()

        self.setWindowTitle("Frame Trace")
        self.setGeometry(300, 300, 520, 300)

        # ---- layouts ----
        root_layout = QHBoxLayout()
        self.setLayout(root_layout)

        self.stack = QStackedLayout()
        self.nav_bar = NavBar()

        self.load_app_icon()
        self.icon_shortcut = QShortcut(QKeySequence("Ctrl+Shift+I"), self)
        self.icon_shortcut.activated.connect(self.choose_app_icon)

        root_layout.addLayout(self.stack)
        root_layout.addWidget(self.nav_bar)

        # ---- navigation ----
        self.nav = NavigationController(self.stack)

        # ---- panels (Dashboard Setup)----
        self.dashboard = DashboardPanel(self.nav)
        self.stack.addWidget(self.dashboard)
        self.stack.setCurrentWidget(self.dashboard)

        self.nav_bar.profile_btn.clicked.connect(
            lambda: self.nav.push(ProfileSelectorPanel(self.nav), "profile")
        )

        self.nav_bar.refs_btn.clicked.connect(
            lambda: self.nav.push(ReferencesPanel(self.nav), "references")
        )

        self.nav_bar.debug_btn.clicked.connect(
            lambda: self.nav.push(DebugPanel(self.nav), "debug")
        )
        self.nav_bar.frames_btn.clicked.connect(
            lambda: self.nav.push(FramesPanel(self.nav), "frames")
        )

    def load_app_icon(self):
        app = QApplication.instance()
        icon_path = self.settings.value("ui/app_icon_path", "", str)
        if icon_path:
            icon = QIcon(icon_path)
            if not icon.isNull():
                self.setWindowIcon(icon)
                if app:
                    app.setWindowIcon(icon)
                return
        bundled_icon_path = Path(__file__).resolve().parents[2] / "assets" / "app_icon.png"
        bundled_icon = QIcon(str(bundled_icon_path))
        if not bundled_icon.isNull():
            self.setWindowIcon(bundled_icon)
            if app:
                app.setWindowIcon(bundled_icon)
            return

        default_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_ComputerIcon
        )
        self.setWindowIcon(default_icon)
        if app:
            app.setWindowIcon(default_icon)

    def choose_app_icon(self):
        icon_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose App Icon",
            "",
            "Images (*.png *.jpg *.jpeg *.ico)"
        )
        if not icon_path:
            return
        icon = QIcon(icon_path)
        if icon.isNull():
            return
        self.settings.setValue("ui/app_icon_path", icon_path)
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app:
            app.setWindowIcon(icon)
