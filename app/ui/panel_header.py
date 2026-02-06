from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from app.ui.theme import Colors
from app.ui.widget_utils import disable_button_focus_rect, disable_widget_interaction


class PanelHeader(QWidget):
    def __init__(self, title, nav):
        super().__init__()
        self.nav = nav

        self.setObjectName("panel_header")
        self.setStyleSheet(
            f"""
            QWidget#panel_header {{
                background-color: {Colors.BG_DARK};
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 6px;
                padding: 4px;
            }}
            """
        )

        back_btn = QPushButton("⬅")
        back_btn.setFixedWidth(40)
        back_btn.clicked.connect(self.nav.pop)
        disable_button_focus_rect(back_btn)

        back_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Colors.BG_MEDIUM_DARK};
                border: 1px solid {Colors.BORDER_DARK};
                color: {Colors.FG_LIGHT};
                border-radius: 4px;
                font-size: 16px;
                outline: none;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_HOVER_DARK};
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: #5a6a7a;
            }}
            QPushButton:focus {{
                outline: none;
                border: 1px solid {Colors.BORDER_DARK};
            }}
            """
        )

        title_lbl = QLabel(title)
        title_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        disable_widget_interaction(title_lbl)
        title_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {Colors.FG_LIGHT};
                font-weight: bold;
                font-size: 14px;
                background-color: transparent;
                padding: 4px 8px;
                selection-background-color: transparent;
                selection-color: {Colors.FG_LIGHT};
            }}
            """
        )

        layout = QHBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(back_btn)
        layout.addWidget(title_lbl)
        layout.addStretch()
        self.setLayout(layout)
