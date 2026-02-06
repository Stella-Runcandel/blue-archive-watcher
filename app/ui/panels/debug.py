from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.app_state import app_state
from app.ui.panel_header import PanelHeader
from app.ui.theme import Styles
from app.ui.widget_utils import disable_button_focus_rect, disable_widget_interaction, make_preview_label
from core.profiles import (
    delete_all_debug_frames,
    delete_debug_frame,
    get_debug_image_bytes,
    list_debug_frames,
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
        disable_widget_interaction(self.mode_label)
        self.mode_label.setStyleSheet(Styles.info_label("#b9b0a4"))

        self.preview_label = make_preview_label("No debug preview", 220, "preview_label")

        self.body_layout = QVBoxLayout()
        self.refresh_debug()

        delete_btn = QPushButton("🗑 Delete All Debug Frames")
        delete_btn.setStyleSheet(Styles.button())
        disable_button_focus_rect(delete_btn)
        delete_btn.clicked.connect(self.delete_all)

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
        layout.addWidget(self.mode_label)
        layout.addWidget(self.preview_label)
        layout.addWidget(scroll)
        layout.addWidget(delete_btn)
        self.setLayout(layout)

    def refresh_debug(self):
        self.selected_btn = None
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        profile = app_state.active_profile
        self.debug_profile = profile
        self.debug_fallback = not profile
        if self.debug_fallback:
            self.mode_label.setText("Fallback mode: showing global debug frames (no profile selected).")
        else:
            self.mode_label.setText(f"Profile debug frames: {profile}")

        files = list_debug_frames(profile, allow_fallback=self.debug_fallback)
        if not files:
            message = "No global debug frames found" if self.debug_fallback else "No debug frames found"
            msg = QLabel(message)
            disable_widget_interaction(msg)
            msg.setStyleSheet(Styles.info_label())
            self.body_layout.addWidget(msg)
            self.update_preview(None)
            return

        for f in files:
            row = QHBoxLayout()
            select_btn = QPushButton(f)
            select_btn.setStyleSheet(Styles.button())
            disable_button_focus_rect(select_btn)
            select_btn.clicked.connect(lambda _, n=f: self.select_debug(n))
            row.addWidget(select_btn)

            delete_btn = QPushButton("🗑 Delete")
            delete_btn.setStyleSheet(Styles.button())
            disable_button_focus_rect(delete_btn)
            delete_btn.clicked.connect(lambda _, n=f: self.delete_single(n))
            row.addWidget(delete_btn)
            self.body_layout.addLayout(row)

            if self.selected_debug == f:
                self.selected_btn = select_btn
                self.selected_btn.setStyleSheet(Styles.selected_button())

        if self.selected_debug not in files:
            self.selected_debug = None
            self.selected_btn = None
            self.update_preview(None)

    def delete_all(self):
        profile = self.debug_profile
        if not self.debug_fallback and not profile:
            return
        target = "global debug frames" if self.debug_fallback else "debug frames"
        confirm = QMessageBox.question(
            self,
            "Delete All Debug Frames",
            f"Delete all {target}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        delete_all_debug_frames(profile, allow_fallback=self.debug_fallback)
        self.selected_debug = None
        self.selected_btn = None
        self.update_preview(None)
        self.refresh_debug()

    def select_debug(self, debug_name):
        self.selected_debug = debug_name
        self.update_preview(debug_name)
        if self.selected_btn:
            self.selected_btn.setStyleSheet(Styles.button())
        self.selected_btn = self.sender()
        self.selected_btn.setStyleSheet(Styles.selected_button())

    def delete_single(self, debug_name):
        target = "global debug frame" if self.debug_fallback else "debug frame"
        confirm = QMessageBox.question(
            self,
            "Delete Debug Frame",
            f"Delete {target} '{debug_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        deleted = delete_debug_frame(self.debug_profile, debug_name, allow_fallback=self.debug_fallback)
        if not deleted:
            QMessageBox.warning(self, "Delete Debug Frame", "Debug frame could not be deleted.")
            return
        if self.selected_debug == debug_name:
            self.selected_debug = None
            self.selected_btn = None
        self.update_preview(None)
        self.refresh_debug()

    def update_preview(self, debug_name):
        if not debug_name:
            self.preview_bytes = None
            self.preview_label.setText("No debug preview")
            self.preview_label.setPixmap(QPixmap())
            return
        data = get_debug_image_bytes(self.debug_profile, debug_name, allow_fallback=self.debug_fallback)
        if not data:
            self.preview_bytes = None
            self.preview_label.setText("Debug preview unavailable")
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
