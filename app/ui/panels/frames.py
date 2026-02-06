from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.app_state import app_state
from app.controllers.frame_controller import FrameController
from app.ui.panel_header import PanelHeader
from app.ui.theme import Styles
from app.ui.widget_utils import (
    disable_button_focus_rect,
    disable_widget_interaction,
    make_preview_label,
)
from core.profiles import get_frame_image_bytes, import_frames, list_frames


class FramesPanel(QWidget):
    def __init__(self, nav):
        super().__init__()
        self.selected_btn = None
        self.nav = nav
        self.frame_controller = FrameController()
        self.preview_bytes = None

        header = PanelHeader("Frames", nav)

        self.selected_label = QLabel("Selected frame: None")
        disable_widget_interaction(self.selected_label)
        self.selected_label.setStyleSheet(Styles.info_label())

        self.preview_label = make_preview_label("No frame preview", 220, "preview_label")

        self.body_layout = QVBoxLayout()
        self.refresh_frames()

        add_btn = QPushButton("➕ Add Frames")
        add_btn.setStyleSheet(Styles.button())
        disable_button_focus_rect(add_btn)
        add_btn.clicked.connect(self.add_frames)

        container = QWidget()
        container.setLayout(self.body_layout)
        container.setObjectName("scroll_container")
        container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setObjectName("scroll_area")
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(Styles.scroll_area())

        layout = QVBoxLayout()
        layout.addWidget(header)
        layout.addWidget(self.selected_label)
        layout.addWidget(self.preview_label)
        layout.addWidget(scroll)
        layout.addWidget(add_btn)
        self.setLayout(layout)

    def refresh_frames(self):
        self.selected_btn = None
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        profile = app_state.active_profile
        if not profile:
            msg = QLabel("No profile selected")
            disable_widget_interaction(msg)
            msg.setStyleSheet(Styles.info_label())
            self.body_layout.addWidget(msg)
            self.selected_label.setText("Selected frame: None")
            self.update_preview(None)
            return

        frames = list_frames(profile)
        if not frames:
            msg = QLabel("No frames uploaded")
            disable_widget_interaction(msg)
            msg.setStyleSheet(Styles.info_label())
            self.body_layout.addWidget(msg)
            self.selected_label.setText("Selected frame: None")
            self.update_preview(None)
            return

        for frame in frames:
            row = QHBoxLayout()
            select_btn = QPushButton(frame)
            select_btn.setStyleSheet(Styles.button())
            disable_button_focus_rect(select_btn)
            select_btn.clicked.connect(lambda _, f=frame: self.select_frame(f))

            delete_btn = QPushButton("🗑 Delete")
            delete_btn.setStyleSheet(Styles.button())
            disable_button_focus_rect(delete_btn)
            delete_btn.clicked.connect(lambda _, f=frame: self.delete_frame(f))

            row.addWidget(select_btn)
            row.addWidget(delete_btn)
            self.body_layout.addLayout(row)

            if app_state.selected_frame == frame:
                self.selected_btn = select_btn
                self.selected_btn.setStyleSheet(Styles.selected_button())

        self.selected_label.setText(
            f"Selected frame: {app_state.selected_frame}" if app_state.selected_frame else "Selected frame: None"
        )
        self.update_preview(app_state.selected_frame)

    def add_frames(self):
        profile = app_state.active_profile
        if not profile:
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Select frame images", "", "Images (*.png *.jpg *.jpeg)")
        if not files:
            return
        import_frames(profile, files)
        self.refresh_frames()

    def select_frame(self, frame_name):
        success, message = self.frame_controller.select_frame(frame_name)
        if not success:
            QMessageBox.warning(self, "Select Frame", message)
            return

        self.selected_label.setText(f"Selected frame: {frame_name}")
        self.update_preview(frame_name)
        if self.selected_btn:
            self.selected_btn.setStyleSheet(Styles.button())
        self.selected_btn = self.sender()
        self.selected_btn.setStyleSheet(Styles.selected_button())

    def delete_frame(self, frame_name):
        confirm = QMessageBox.question(
            self,
            "Delete Frame",
            f"Delete frame '{frame_name}' and its derived references?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        success, message = self.frame_controller.delete_frame(frame_name)
        if not success:
            QMessageBox.warning(self, "Delete Frame", message)
            return
        self.selected_btn = None
        self.refresh_frames()

    def update_preview(self, frame_name):
        if not frame_name:
            self.preview_bytes = None
            self.preview_label.setText("No frame preview")
            self.preview_label.setPixmap(QPixmap())
            return
        data = get_frame_image_bytes(app_state.active_profile, frame_name)
        if not data:
            self.preview_bytes = None
            self.preview_label.setText("Frame preview unavailable")
            self.preview_label.setPixmap(QPixmap())
            return
        self.preview_bytes = data
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.preview_label.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.preview_bytes:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(self.preview_bytes)
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
