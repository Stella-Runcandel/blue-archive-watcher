from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout, QFileDialog
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from app.ui.panel_header import PanelHeader
from PyQt6.QtWidgets import QInputDialog, QMessageBox
from app.controllers.profile_controller import ProfileController
from app.app_state import app_state
from core.profiles import get_profile_icon_bytes


class ProfileSelectorPanel(QWidget):
    def __init__(self, nav):
        super().__init__()
        self.nav = nav
        self.profile_controller = ProfileController()

        # ---- header ----
        header = PanelHeader("Select Profile", nav)

        # ---- body ----
        self.body_layout = QVBoxLayout()

        self.refresh_profiles()

        # ---- create profile button ----
        create_btn = QPushButton("➕ Create New Profile")
        create_btn.clicked.connect(self.create_profile)

        # ---- set profile icon button ----
        icon_btn = QPushButton("Set / Change Profile Icon")
        icon_btn.clicked.connect(self.set_profile_icon)

        # ---- main layout ----
        layout = QVBoxLayout()
        layout.addWidget(header)
        layout.addLayout(self.body_layout)
        layout.addWidget(icon_btn)
        layout.addWidget(create_btn)

        self.setLayout(layout)

    def refresh_profiles(self):
        # clear old buttons
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        success, profiles, message = self.profile_controller.list_profiles()

        if not success:
            self.body_layout.addWidget(QLabel(message))
            return

        if not profiles:
            self.body_layout.addWidget(QLabel("No profiles found"))
            return

        for name in profiles:
            row = QHBoxLayout()

            icon_label = QLabel()
            icon_label.setFixedSize(24, 24)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            data = get_profile_icon_bytes(name)
            if data:
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                icon_label.setPixmap(
                    pixmap.scaled(
                        24,
                        24,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                )
            else:
                icon_label.setText(" ")

            select_btn = QPushButton(name)
            select_btn.clicked.connect(lambda _, n=name: self.select_profile(n))

            delete_btn = QPushButton("🗑 Delete")
            delete_btn.clicked.connect(lambda _, n=name: self.delete_profile(n))

            row.addWidget(icon_label)
            row.addWidget(select_btn)
            row.addWidget(delete_btn)

            self.body_layout.addLayout(row)

    def select_profile(self, name):
        success, message = self.profile_controller.select_profile(name)
        if not success:
            QMessageBox.warning(
                self,
                "Select Profile",
                message
            )
            return
        self.nav.pop()  # go back to dashboard

    def create_profile(self):
        name, ok = QInputDialog.getText(
            self,
            "Create New Profile",
            "Enter profile name:"
        )

        if not ok or not name.strip():
            return

        name = name.strip()
        success, message = self.profile_controller.create_profile(name)
        if not success:
            QMessageBox.warning(
                self,
                "Create Profile",
                message
            )
            return

        self.refresh_profiles()

        QMessageBox.information(
            self,
            "Profile Created",
            message
        )

        # Go back to dashboard
        self.nav.pop()

    def delete_profile(self, name):
        confirm = QMessageBox.question(
            self,
            "Delete Profile",
            f"Delete profile '{name}' and all of its data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        success, message = self.profile_controller.delete_profile(name)
        if not success:
            QMessageBox.warning(
                self,
                "Delete Profile",
                message
            )
            return
        self.refresh_profiles()

    def set_profile_icon(self):
        if not app_state.active_profile:
            QMessageBox.warning(
                self,
                "Set Profile Icon",
                "Select a profile first."
            )
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Profile Icon",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )
        if not file_path:
            return
        success, message = self.profile_controller.set_profile_icon(
            app_state.active_profile,
            file_path
        )
        if not success:
            QMessageBox.warning(
                self,
                "Set Profile Icon",
                message
            )
            return
        QMessageBox.information(
            self,
            "Set Profile Icon",
            message
        )
        self.refresh_profiles()
