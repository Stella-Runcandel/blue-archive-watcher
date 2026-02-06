from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QHBoxLayout,
    QMessageBox
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from app.ui.panel_header import PanelHeader
from app.app_state import app_state
from app.controllers.reference_controller import ReferenceController
from core.profiles import (
    list_references,
    get_reference_parent_frame,
    get_reference_image_bytes
)


class ReferencesPanel(QWidget):
    """
    References Panel (FINAL)
    - Lists references
    - Shows parent frame
    - Allows selecting a reference
    - Allows creating new references from selected frame
    """

    def __init__(self, nav):
        super().__init__()
        self.selected_btn = None
        self.nav = nav
        self.reference_controller = ReferenceController()
        self.preview_bytes = None

        header = PanelHeader("References", nav)

        self.info_label = QLabel("Selected reference: None")
        self.preview_label = QLabel("No reference preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(220)
        self.preview_label.setStyleSheet(
            "border: 1px solid #595148; background-color: #332f2a; color: #c8c1b7;"
        )

        self.body_layout = QVBoxLayout()

        self.new_ref_btn = QPushButton("➕ New Reference")
        self.new_ref_btn.clicked.connect(self.create_reference)

        self.refresh_references()
        self.update_new_ref_button()

        container = QWidget()
        container.setLayout(self.body_layout)

        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)

        layout = QVBoxLayout()
        layout.addWidget(header)
        layout.addWidget(self.info_label)
        layout.addWidget(self.preview_label)
        layout.addWidget(scroll)
        layout.addWidget(self.new_ref_btn)

        self.setLayout(layout)

    # ---------------- UI Refresh ----------------

    def refresh(self):
        self.refresh_references()
        self.update_new_ref_button()

        if app_state.selected_reference:
            self.info_label.setText(
                f"Selected reference: {app_state.selected_reference}"
            )
        else:
            self.info_label.setText("Selected reference: None")

    # ---------------- Reference Listing ----------------

    def refresh_references(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        profile = app_state.active_profile
        if not profile:
            self.body_layout.addWidget(QLabel("No profile selected"))
            self.info_label.setText("Selected reference: None")
            self.update_preview(None)
            return
        refs = list_references(profile)

        if not refs:
            self.body_layout.addWidget(QLabel("No references found"))
            self.info_label.setText("Selected reference: None")
            self.update_preview(None)
            return

        for ref in refs:
            parent = get_reference_parent_frame(profile, ref)
            row = QHBoxLayout()
            select_btn = QPushButton(f"{ref}  ←  {parent}")
            select_btn.clicked.connect(
                lambda _, r=ref: self.select_reference(r)
            )

            delete_btn = QPushButton("🗑 Delete")
            delete_btn.clicked.connect(
                lambda _, r=ref: self.delete_reference(r)
            )

            row.addWidget(select_btn)
            row.addWidget(delete_btn)
            self.body_layout.addLayout(row)

            if app_state.selected_reference == ref:
                self.selected_btn = select_btn
                self.selected_btn.setStyleSheet(
                    "font-weight: bold; background-color: #6f7f94; color: #ece4d9; border: 1px solid #7f8fa3;"
                )

        if app_state.selected_reference:
            self.info_label.setText(
                f"Selected reference: {app_state.selected_reference}"
            )
        else:
            self.info_label.setText("Selected reference: None")
        self.update_preview(app_state.selected_reference)


    # ---------------- Actions ----------------

    def select_reference(self, ref_name):
        success, message = self.reference_controller.select_reference(ref_name)
        if not success:
            QMessageBox.warning(
                self,
                "Select Reference",
                message
            )
            return
        self.update_preview(ref_name)
        self.info_label.setText(f"Selected reference: {ref_name}")

        if self.selected_btn:
            self.selected_btn.setStyleSheet("")

        self.selected_btn = self.sender()
        self.selected_btn.setStyleSheet(
            "font-weight: bold; background-color: #6f7f94; color: #ece4d9; border: 1px solid #7f8fa3;"
        )


    def create_reference(self):
        if not app_state.selected_frame:
            return

        from app.ui.panels.crop_panel import CropPanel
        self.nav.push(CropPanel(self.nav), "crop")

    def update_new_ref_button(self):
        if app_state.selected_frame:
            self.new_ref_btn.setEnabled(True)
            self.new_ref_btn.setText(
                f"➕ New Reference (from {app_state.selected_frame})"
            )
        else:
            self.new_ref_btn.setEnabled(False)
            self.new_ref_btn.setText(
                "➕ New Reference (select a frame first)"
            )

    def delete_reference(self, ref_name):
        confirm = QMessageBox.question(
            self,
            "Delete Reference",
            f"Delete reference '{ref_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        success, message = self.reference_controller.delete_reference(ref_name)
        if not success:
            QMessageBox.warning(
                self,
                "Delete Reference",
                message
            )
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
