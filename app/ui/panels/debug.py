from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QScrollArea, QHBoxLayout
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from app.ui.panel_header import PanelHeader
from app.app_state import app_state
from core.profiles import (
    list_debug_frames,
    get_debug_image_bytes,
    delete_all_debug_frames
)


class DebugPanel(QWidget):
    def __init__(self, nav):
        super().__init__()
        self.nav = nav
        self.selected_btn = None
        self.selected_debug = None
        self.preview_bytes = None

        header = PanelHeader("Debug Frames", nav)

        self.preview_label = QLabel("No debug preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(220)
        self.preview_label.setStyleSheet(
            "border: 1px solid #3a3a3a; color: #aaa;"
        )

        self.body_layout = QVBoxLayout()
        self.refresh_debug()

        delete_btn = QPushButton("🗑 Delete All Debug Frames")
        delete_btn.clicked.connect(self.delete_all)

        container = QWidget()
        container.setLayout(self.body_layout)

        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)

        layout = QVBoxLayout()
        layout.addWidget(header)
        layout.addWidget(self.preview_label)
        layout.addWidget(scroll)
        layout.addWidget(delete_btn)

        self.setLayout(layout)

    def refresh_debug(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        profile = app_state.active_profile
        if not profile:
            self.body_layout.addWidget(QLabel("No profile selected"))
            self.update_preview(None)
            return

        files = list_debug_frames(profile)

        if not files:
            self.body_layout.addWidget(QLabel("No debug frames found"))
            self.update_preview(None)
            return

        for f in files:
            row = QHBoxLayout()
            select_btn = QPushButton(f)
            select_btn.clicked.connect(
                lambda _, n=f: self.select_debug(n)
            )
            row.addWidget(select_btn)
            self.body_layout.addLayout(row)

            if self.selected_debug == f:
                self.selected_btn = select_btn
                self.selected_btn.setStyleSheet(
                    "font-weight: bold; background-color: #2d6cdf; color: white;"
                )

        if self.selected_debug not in files:
            self.selected_debug = None
            self.selected_btn = None
            self.update_preview(None)

    def delete_all(self):
        profile = app_state.active_profile
        if not profile:
            return
        delete_all_debug_frames(profile)
        self.selected_debug = None
        self.selected_btn = None
        self.update_preview(None)
        self.refresh_debug()

    def select_debug(self, debug_name):
        self.selected_debug = debug_name
        self.update_preview(debug_name)

        if self.selected_btn:
            self.selected_btn.setStyleSheet("")

        self.selected_btn = self.sender()
        self.selected_btn.setStyleSheet(
            "font-weight: bold; background-color: #2d6cdf; color: white;"
        )

    def update_preview(self, debug_name):
        if not debug_name:
            self.preview_bytes = None
            self.preview_label.setText("No debug preview")
            self.preview_label.setPixmap(QPixmap())
            return
        data = get_debug_image_bytes(app_state.active_profile, debug_name)
        if not data:
            self.preview_bytes = None
            self.preview_label.setText("Debug preview unavailable")
            self.preview_label.setPixmap(QPixmap())
            return
        self.preview_bytes = data
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        scaled = pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.preview_label.setPixmap(scaled)
        self.preview_label.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.preview_bytes:
            pixmap = QPixmap()
            pixmap.loadFromData(self.preview_bytes)
            scaled = pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled)
