from PyQt6.QtWidgets import QWidget, QStackedLayout, QHBoxLayout

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

        self.setWindowTitle("B.A Game Analysis")
        self.setGeometry(300, 300, 520, 300)

        # ---- layouts ----
        root_layout = QHBoxLayout()
        self.setLayout(root_layout)

        self.stack = QStackedLayout()
        self.nav_bar = NavBar()

        self.setStyleSheet(
            "QPushButton:hover { background-color: #7a889a; }"
        )

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