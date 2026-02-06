from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from app.ui.theme import Colors, Styles
from app.ui.widget_utils import disable_button_focus_rect


class NavBar(QWidget):
    def __init__(self):
        super().__init__()

        self.profile_btn = QPushButton("👤 Profile")
        self.frames_btn = QPushButton("🖼 Frames")
        self.refs_btn = QPushButton("✂ References")
        self.debug_btn = QPushButton("🐞 Debug")

        layout = QVBoxLayout()
        layout.addWidget(self.profile_btn)
        layout.addWidget(self.frames_btn)
        layout.addWidget(self.refs_btn)
        layout.addWidget(self.debug_btn)
        layout.addStretch()
        self.setLayout(layout)
        self.setFixedWidth(140)

        self.setStyleSheet(
            f"background-color: {Colors.BG_DARK}; border-left: 1px solid {Colors.BORDER_DARK};"
            f"color: {Colors.FG_LIGHT};"
        )

        btn_style = Styles.button(dark=True)
        for button in [
            self.profile_btn,
            self.frames_btn,
            self.refs_btn,
            self.debug_btn,
        ]:
            button.setStyleSheet(btn_style)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            disable_button_focus_rect(button)
