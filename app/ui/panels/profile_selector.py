from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.app_state import app_state
from app.controllers.profile_controller import ProfileController
from app.ui.panel_header import PanelHeader
from app.ui.theme import Styles
from app.ui.widget_utils import disable_button_focus_rect, disable_widget_interaction
from core.profiles import get_profile_icon_bytes


class ProfileSelectorPanel(QWidget):
    def __init__(self, nav):
        super().__init__()
        self.nav = nav
        self.profile_controller = ProfileController()
        self.selected_btn = None

        header = PanelHeader("Select Profile", nav)

        self.body_layout = QVBoxLayout()
        self.refresh_profiles()

        create_btn = QPushButton("➕ Create New Profile")
        create_btn.setStyleSheet(Styles.button())
        disable_button_focus_rect(create_btn)
        create_btn.clicked.connect(self.create_profile)

        icon_btn = QPushButton("Set / Change Profile Icon")
        icon_btn.setStyleSheet(Styles.button())
        disable_button_focus_rect(icon_btn)
        icon_btn.clicked.connect(self.set_profile_icon)

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
        layout.addWidget(scroll)
        layout.addWidget(icon_btn)
        layout.addWidget(create_btn)
        self.setLayout(layout)

    def refresh_profiles(self):
        self.selected_btn = None
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        success, profiles, message = self.profile_controller.list_profiles()
        if not success:
            msg = QLabel(message)
            disable_widget_interaction(msg)
            msg.setStyleSheet(Styles.info_label())
            self.body_layout.addWidget(msg)
            return

        if not profiles:
            msg = QLabel("No profiles found")
            disable_widget_interaction(msg)
            msg.setStyleSheet(Styles.info_label())
            self.body_layout.addWidget(msg)
            return

        for name in profiles:
            row = QHBoxLayout()

            icon_label = QLabel()
            icon_label.setFixedSize(24, 24)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            disable_widget_interaction(icon_label)
            data = get_profile_icon_bytes(name)
            if data:
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                icon_label.setPixmap(
                    pixmap.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
            else:
                icon_label.setText(" ")

            select_btn = QPushButton(name)
            select_btn.setStyleSheet(Styles.button())
            disable_button_focus_rect(select_btn)
            select_btn.clicked.connect(lambda _, n=name: self.select_profile(n))
            if app_state.active_profile == name:
                self.selected_btn = select_btn
                self.selected_btn.setStyleSheet(Styles.selected_button())

            delete_btn = QPushButton("🗑 Delete")
            delete_btn.setStyleSheet(Styles.button())
            disable_button_focus_rect(delete_btn)
            delete_btn.clicked.connect(lambda _, n=name: self.delete_profile(n))

            row.addWidget(icon_label)
            row.addWidget(select_btn)
            row.addWidget(delete_btn)
            self.body_layout.addLayout(row)

    def select_profile(self, name):
        success, message = self.profile_controller.select_profile(name)
        if not success:
            QMessageBox.warning(self, "Select Profile", message)
            return
        self.nav.pop()

    def create_profile(self):
        name, ok = QInputDialog.getText(self, "Create New Profile", "Enter profile name:")
        if not ok or not name.strip():
            return

        success, message = self.profile_controller.create_profile(name.strip())
        if not success:
            QMessageBox.warning(self, "Create Profile", message)
            return

        self.refresh_profiles()
        QMessageBox.information(self, "Profile Created", message)
        self.nav.pop()

    def delete_profile(self, name):
        confirm = QMessageBox.question(
            self,
            "Delete Profile",
            f"Delete profile '{name}' and all of its data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        success, message = self.profile_controller.delete_profile(name)
        if not success:
            QMessageBox.warning(self, "Delete Profile", message)
            return
        self.refresh_profiles()

    def set_profile_icon(self):
        if not app_state.active_profile:
            QMessageBox.warning(self, "Set Profile Icon", "Select a profile first.")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Profile Icon", "", "Images (*.png *.jpg *.jpeg)")
        if not file_path:
            return
        success, message = self.profile_controller.set_profile_icon(app_state.active_profile, file_path)
        if not success:
            QMessageBox.warning(self, "Set Profile Icon", message)
            return
        QMessageBox.information(self, "Set Profile Icon", message)
        self.refresh_profiles()
