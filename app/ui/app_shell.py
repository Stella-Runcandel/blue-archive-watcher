from PyQt6.QtWidgets import (
    QWidget,
    QStackedLayout,
    QHBoxLayout,
    QVBoxLayout,
    QFileDialog,
    QApplication,
    QStyle,
)
from PyQt6.QtGui import QIcon, QShortcut, QKeySequence
from pathlib import Path
import logging

from PyQt6.QtCore import QSettings

from app.ui.nav_bar import NavBar
from app.ui.panels.dashboard import DashboardPanel
from app.controllers.navigation_controller import NavigationController
from app.ui.panels.references import ReferencesPanel
from app.ui.panels.profile_selector import ProfileSelectorPanel
from app.ui.panels.debug import DebugPanel
from app.ui.panels.frames import FramesPanel

logger = logging.getLogger(__name__)


class AppShell(QWidget):
    def __init__(self):
        super().__init__()

        self.settings = QSettings()

        self.setWindowTitle("Frame Trace")
        # BUG FIX #2: Larger default window size for better UX
        self.setGeometry(300, 300, 1000, 700)
        self.setMinimumSize(800, 600)

        # ---- layouts ----
        root_layout = QHBoxLayout()
        # BUG FIX #1: Add proper margins and spacing
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setLayout(root_layout)

        # Create container for stacked layout
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.stack = QStackedLayout()
        self.stack.setContentsMargins(0, 0, 0, 0)
        container_layout.addLayout(self.stack)
        container.setLayout(container_layout)

        self.nav_bar = NavBar()

        self.load_app_icon()
        self.icon_shortcut = QShortcut(QKeySequence("Ctrl+Shift+I"), self)
        self.icon_shortcut.activated.connect(self.choose_app_icon)

        # BUG FIX #4: Proper layout order - nav_bar on left, content on right
        root_layout.addWidget(self.nav_bar, 0)
        root_layout.addWidget(container, 1)

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
            try:
                icon = QIcon(icon_path)
                if not icon.isNull():
                    self.setWindowIcon(icon)
                    if app:
                        app.setWindowIcon(icon)
                    return
            except Exception as e:
                # BUG FIX #3: Add error logging
                logger.warning(f"Failed to load custom icon from {icon_path}: {e}")

        bundled_icon_path = Path(__file__).resolve().parents[2] / "assets" / "app_icon.png"
        try:
            bundled_icon = QIcon(str(bundled_icon_path))
            if not bundled_icon.isNull():
                self.setWindowIcon(bundled_icon)
                if app:
                    app.setWindowIcon(bundled_icon)
                return
        except Exception as e:
            logger.warning(f"Failed to load bundled icon from {bundled_icon_path}: {e}")

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
            logger.error(f"Invalid icon file selected: {icon_path}")
            return
        self.settings.setValue("ui/app_icon_path", icon_path)
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app:
            app.setWindowIcon(icon)