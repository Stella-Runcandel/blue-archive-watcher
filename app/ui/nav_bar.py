from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout


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
            "background-color: #332f2a; border-left: 1px solid #595148;"
            "color: #c8c1b7;"
        )
        btn_style = (
            "QPushButton { background-color: #3a352f; border: 1px solid #595148; color: #c8c1b7; }"
            "QPushButton:hover { background-color: #7a889a; }"
        )
        self.profile_btn.setStyleSheet(btn_style)
        self.frames_btn.setStyleSheet(btn_style)
        self.refs_btn.setStyleSheet(btn_style)
        self.debug_btn.setStyleSheet(btn_style)
