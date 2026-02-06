from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QScrollArea, QHBoxLayout,
    QMessageBox
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from app.ui.panel_header import PanelHeader
from app.app_state import app_state
from core.profiles import (
    list_debug_frames,
    get_debug_image_bytes,
    delete_all_debug_frames,
    delete_debug_frame
)


class DebugPanel(QWidget):
    def __init__(self, nav):
        super().__init__()
        self.nav = nav
        self.selected_btn = None
        self.selected_debug = None
        self.preview_bytes = None
        self.debug_profile = None
        self.debug_fallback = False

        header = PanelHeader("Debug Frames", nav)

        self.mode_label = QLabel()
        self.mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_label.setStyleSheet("color: #b9b0a4;")

        self.preview_label = QLabel("No debug preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(220)
        self.preview_label.setStyleSheet(
            "border: 1px solid #595148; background-color: #332f2a; color: #c8c1b7;"
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
        layout.addWidget(self.mode_label)
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
        self.debug_profile = profile
        self.debug_fallback = not profile
        if self.debug_fallback:
            # MEDIUM 2: fallback mode is exclusive; do not mix profile/global lists.
            self.mode_label.setText(
                "Fallback mode: showing global debug frames (no profile selected)."
            )
        else:
            self.mode_label.setText(f"Profile debug frames: {profile}")

        files = list_debug_frames(profile, allow_fallback=self.debug_fallback)

        if not files:
            message = (
                "No global debug frames found"
                if self.debug_fallback else "No debug frames found"
            )
            self.body_layout.addWidget(QLabel(message))
            self.update_preview(None)
            return

        for f in files:
            row = QHBoxLayout()
            select_btn = QPushButton(f)
            select_btn.clicked.connect(
                lambda _, n=f: self.select_debug(n)
            )
            row.addWidget(select_btn)
            delete_btn = QPushButton("🗑 Delete")
            delete_btn.clicked.connect(
                lambda _, n=f: self.delete_single(n)
            )
            row.addWidget(delete_btn)
            self.body_layout.addLayout(row)

            if self.selected_debug == f:
                self.selected_btn = select_btn
                self.selected_btn.setStyleSheet(
                    "font-weight: bold; background-color: #6f7f94; color: #ece4d9; border: 1px solid #7f8fa3;"
                )

        if self.selected_debug not in files:
            self.selected_debug = None
            self.selected_btn = None
            self.update_preview(None)

    def delete_all(self):
        profile = self.debug_profile
        if not self.debug_fallback and not profile:
            return
        title = "Delete All Debug Frames"
        target = "global debug frames" if self.debug_fallback else "debug frames"
        confirm = QMessageBox.question(
            self,
            title,
            f"Delete all {target}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        delete_all_debug_frames(profile, allow_fallback=self.debug_fallback)
        self.selected_debug = None
        self.selected_btn = None
        self.update_preview(None)  # MEDIUM 4: clear preview before refresh after deletes.
        self.refresh_debug()

    def select_debug(self, debug_name):
        self.selected_debug = debug_name
        self.update_preview(debug_name)

        if self.selected_btn:
            self.selected_btn.setStyleSheet("")

        self.selected_btn = self.sender()
        self.selected_btn.setStyleSheet(
            "font-weight: bold; background-color: #6f7f94; color: #ece4d9; border: 1px solid #7f8fa3;"
        )

    def delete_single(self, debug_name):
        title = "Delete Debug Frame"
        target = "global debug frame" if self.debug_fallback else "debug frame"
        confirm = QMessageBox.question(
            self,
            title,
            f"Delete {target} '{debug_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        deleted = delete_debug_frame(
            self.debug_profile,
            debug_name,
            allow_fallback=self.debug_fallback
        )
        if not deleted:
            QMessageBox.warning(
                self,
                title,
                "Debug frame could not be deleted."
            )
            return
        if self.selected_debug == debug_name:
            self.selected_debug = None
            self.selected_btn = None
        self.update_preview(None)  # MEDIUM 4: clear preview before refresh after deletes.
        self.refresh_debug()

    def update_preview(self, debug_name):
        if not debug_name:
            self.preview_bytes = None
            self.preview_label.setText("No debug preview")
            self.preview_label.setPixmap(QPixmap())
            return
        data = get_debug_image_bytes(
            self.debug_profile,
            debug_name,
            allow_fallback=self.debug_fallback
        )
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
