from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QScrollArea,
    QHBoxLayout,
    QMessageBox
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from app.ui.panel_header import PanelHeader
from app.app_state import app_state
from app.controllers.frame_controller import FrameController
from core.profiles import (
    import_frames,
    list_frames,
    get_frame_image_bytes
)


class FramesPanel(QWidget):
    """
    Frames Panel
    - Shows all base frames for the active profile
    - Allows uploading multiple images
    - Allows selecting ONE frame for cropping
    """

    def __init__(self, nav):
        super().__init__()
        self.selected_btn = None
        self.nav = nav
        self.frame_controller = FrameController()
        self.preview_bytes = None

        header = PanelHeader("Frames", nav)

        self.selected_label = QLabel("Selected frame: None")
        self.preview_label = QLabel("No frame preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(220)
        self.preview_label.setStyleSheet(
            "border: 1px solid #595148; background-color: #332f2a; color: #c8c1b7;"
        )

        self.body_layout = QVBoxLayout()
        self.refresh_frames()

        add_btn = QPushButton("➕ Add Frames")
        add_btn.clicked.connect(self.add_frames)

        container = QWidget()
        container.setLayout(self.body_layout)

        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)

        layout = QVBoxLayout()
        layout.addWidget(header)
        layout.addWidget(self.selected_label)
        layout.addWidget(self.preview_label)
        layout.addWidget(scroll)
        layout.addWidget(add_btn)

        self.setLayout(layout)

    def refresh_frames(self):
        # clear old entries
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        profile = app_state.active_profile
        if not profile:
            self.body_layout.addWidget(QLabel("No profile selected"))
            self.selected_label.setText("Selected frame: None")
            self.update_preview(None)
            return

        frames = list_frames(profile)

        if not frames:
            self.body_layout.addWidget(QLabel("No frames uploaded"))
            self.selected_label.setText("Selected frame: None")
            self.update_preview(None)
            return

        for frame in frames:
            row = QHBoxLayout()
            select_btn = QPushButton(frame)
            select_btn.clicked.connect(
                lambda _, f=frame: self.select_frame(f)
            )

            delete_btn = QPushButton("🗑 Delete")
            delete_btn.clicked.connect(
                lambda _, f=frame: self.delete_frame(f)
            )

            row.addWidget(select_btn)
            row.addWidget(delete_btn)
            self.body_layout.addLayout(row)

            if app_state.selected_frame == frame:
                self.selected_btn = select_btn
                self.selected_btn.setStyleSheet(
                    "font-weight: bold; background-color: #6f7f94; color: #ece4d9; border: 1px solid #7f8fa3;"
                )

        if app_state.selected_frame:
            self.selected_label.setText(
                f"Selected frame: {app_state.selected_frame}"
            )
        else:
            self.selected_label.setText("Selected frame: None")
        self.update_preview(app_state.selected_frame)

    def add_frames(self):
        profile = app_state.active_profile
        if not profile:
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select frame images",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )

        if not files:
            return

        import_frames(profile, files)

        self.refresh_frames()

    def select_frame(self, frame_name):
        success, message = self.frame_controller.select_frame(frame_name)
        if not success:
            QMessageBox.warning(
                self,
                "Select Frame",
                message
            )
            return
        self.selected_label.setText(f"Selected frame: {frame_name}")
        self.update_preview(frame_name)

        if self.selected_btn:
            self.selected_btn.setStyleSheet("")

        self.selected_btn = self.sender()
        self.selected_btn.setStyleSheet(
            "font-weight: bold; background-color: #6f7f94; color: #ece4d9; border: 1px solid #7f8fa3;"
        )

    def delete_frame(self, frame_name):
        confirm = QMessageBox.question(
            self,
            "Delete Frame",
            f"Delete frame '{frame_name}' and its derived references?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        success, message = self.frame_controller.delete_frame(frame_name)
        if not success:
            QMessageBox.warning(
                self,
                "Delete Frame",
                message
            )
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
