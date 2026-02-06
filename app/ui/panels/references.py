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
from app.controllers.reference_controller import ReferenceController
from app.ui.panel_header import PanelHeader
from app.ui.theme import Styles
from app.ui.widget_utils import disable_button_focus_rect, disable_widget_interaction, make_preview_label
from core.profiles import get_reference_image_bytes, get_reference_parent_frame, list_references


class ReferencesPanel(QWidget):
    def __init__(self, nav):
        super().__init__()
        self.selected_btn = None
        self.nav = nav
        self.reference_controller = ReferenceController()
        self.preview_bytes = None

        header = PanelHeader("References", nav)

        self.info_label = QLabel("Selected reference: None")
        disable_widget_interaction(self.info_label)
        self.info_label.setStyleSheet(Styles.info_label())

        self.preview_label = make_preview_label("No reference preview", 220, "preview_label")

        self.body_layout = QVBoxLayout()
        self.new_ref_btn = QPushButton("➕ New Reference")
        self.new_ref_btn.setStyleSheet(Styles.button())
        disable_button_focus_rect(self.new_ref_btn)
        self.new_ref_btn.clicked.connect(self.create_reference)

        self.refresh_references()
        self.update_new_ref_button()

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
        layout.addWidget(self.info_label)
        layout.addWidget(self.preview_label)
        layout.addWidget(scroll)
        layout.addWidget(self.new_ref_btn)
        self.setLayout(layout)

    def refresh(self):
        self.refresh_references()
        self.update_new_ref_button()
        self.info_label.setText(
            f"Selected reference: {app_state.selected_reference}" if app_state.selected_reference else "Selected reference: None"
        )

    def refresh_references(self):
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
            self.info_label.setText("Selected reference: None")
            self.update_preview(None)
            return

        refs = list_references(profile)
        if not refs:
            msg = QLabel("No references found")
            disable_widget_interaction(msg)
            msg.setStyleSheet(Styles.info_label())
            self.body_layout.addWidget(msg)
            self.info_label.setText("Selected reference: None")
            self.update_preview(None)
            return

        for ref in refs:
            parent = get_reference_parent_frame(profile, ref)
            row = QHBoxLayout()

            select_btn = QPushButton(f"{ref}  ←  {parent}")
            select_btn.setStyleSheet(Styles.button())
            disable_button_focus_rect(select_btn)
            select_btn.clicked.connect(lambda _, r=ref: self.select_reference(r))

            delete_btn = QPushButton("🗑 Delete")
            delete_btn.setStyleSheet(Styles.button())
            disable_button_focus_rect(delete_btn)
            delete_btn.clicked.connect(lambda _, r=ref: self.delete_reference(r))

            row.addWidget(select_btn)
            row.addWidget(delete_btn)
            self.body_layout.addLayout(row)

            if app_state.selected_reference == ref:
                self.selected_btn = select_btn
                self.selected_btn.setStyleSheet(Styles.selected_button())

        self.info_label.setText(
            f"Selected reference: {app_state.selected_reference}" if app_state.selected_reference else "Selected reference: None"
        )
        self.update_preview(app_state.selected_reference)

    def select_reference(self, ref_name):
        success, message = self.reference_controller.select_reference(ref_name)
        if not success:
            QMessageBox.warning(self, "Select Reference", message)
            return

        self.update_preview(ref_name)
        self.info_label.setText(f"Selected reference: {ref_name}")
        if self.selected_btn:
            self.selected_btn.setStyleSheet(Styles.button())
        self.selected_btn = self.sender()
        self.selected_btn.setStyleSheet(Styles.selected_button())

    def create_reference(self):
        if not app_state.selected_frame:
            return
        from app.ui.panels.crop_panel import CropPanel

        self.nav.push(CropPanel(self.nav), "crop")

    def update_new_ref_button(self):
        if app_state.selected_frame:
            self.new_ref_btn.setEnabled(True)
            self.new_ref_btn.setText(f"➕ New Reference (from {app_state.selected_frame})")
        else:
            self.new_ref_btn.setEnabled(False)
            self.new_ref_btn.setText("➕ New Reference (select a frame first)")

    def delete_reference(self, ref_name):
        confirm = QMessageBox.question(
            self,
            "Delete Reference",
            f"Delete reference '{ref_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        success, message = self.reference_controller.delete_reference(ref_name)
        if not success:
            QMessageBox.warning(self, "Delete Reference", message)
            return
        self.selected_btn = None
        self.refresh()

    def update_preview(self, ref_name):
        if not ref_name:
            self.preview_bytes = None
            self.preview_label.setText("No reference preview")
            self.preview_label.setPixmap(QPixmap())
            return
        data = get_reference_image_bytes(app_state.active_profile, ref_name)
        if not data:
            self.preview_bytes = None
            self.preview_label.setText("Reference preview unavailable")
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
