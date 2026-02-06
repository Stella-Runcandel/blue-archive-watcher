from PyQt6.QtWidgets import QWidget, QPushButton, QLabel, QHBoxLayout


class PanelHeader(QWidget):
    def __init__(self, title, nav):
        super().__init__()
        self.nav = nav

        back_btn = QPushButton("⬅")
        back_btn.setFixedWidth(40)
        back_btn.clicked.connect(self.nav.pop)

        title_lbl = QLabel(title)

        self.setStyleSheet(
            "background-color: #332f2a; border: 1px solid #595148;"
            "color: #c8c1b7;"
        )
        back_btn.setStyleSheet(
            "background-color: #3a352f; border: 1px solid #595148; color: #c8c1b7;"
        )
        title_lbl.setStyleSheet("color: #c8c1b7; font-weight: bold;")

        layout = QHBoxLayout()
        layout.addWidget(back_btn)
        layout.addWidget(title_lbl)
        layout.addStretch()

        self.setLayout(layout)
