import cv2

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.app_state import app_state
from app.controllers.monitor_controller import MonitorController
from app.services.monitor_service import MonitorService
from app.ui.theme import Styles
from app.ui.widget_utils import disable_button_focus_rect, disable_widget_interaction, make_preview_label
from core import detector as dect
from core.profiles import (
    get_detection_threshold,
    get_profile_camera_index,
    get_profile_icon_bytes,
    list_profiles,
    set_profile_camera_index,
    update_profile_detection_threshold,
)


class DashboardPanel(QWidget):
    STRICTNESS_OPTIONS = [
        ("Very Loose", 0.55),
        ("Loose", 0.65),
        ("Balanced", 0.70),
        ("Strict", 0.80),
        ("Very Strict", 0.88),
        ("Extreme", 0.93),
    ]

    def __init__(self, nav):
        super().__init__()
        self.nav = nav

        self.profile_label = QLabel("Profile: None")
        self.frame_label = QLabel("Selected Frame: None")
        self.ref_label = QLabel("Selected Reference: None")
        self.monitor_label = QLabel("Monitoring: Stopped")
        self.status_label = QLabel("Status: Idle")
        self.strictness_label = QLabel("Detection Strictness")
        self.camera_label = QLabel("Camera Index")
        self.camera_preview_title = QLabel("Camera Preview")
        self.camera_preview_hint = QLabel("Is this the right input?")

        for label in [
            self.profile_label,
            self.frame_label,
            self.ref_label,
            self.monitor_label,
            self.status_label,
            self.strictness_label,
            self.camera_label,
            self.camera_preview_title,
            self.camera_preview_hint,
        ]:
            disable_widget_interaction(label)
            label.setStyleSheet(Styles.info_label())

        self.profile_preview_bytes = None
        self.profile_preview = make_preview_label("No profile preview", 180, "profile_preview")

        self.strictness_combo = QComboBox()
        self.strictness_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.strictness_combo.setStyleSheet(
            """
            QComboBox {
                background-color: #ffffff;
                color: #111111;
                border: 1px solid #d6d6d6;
                border-radius: 6px;
                padding: 6px 10px;
                outline: none;
            }
            QComboBox:hover {
                border-color: #cdcdcd;
            }
            QComboBox:focus {
                border: 2px solid #7f8fa3;
                outline: none;
            }
            QComboBox::drop-down {
                background-color: #ffffff;
                border: 0;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #111111;
                width: 0;
                height: 0;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #111111;
                selection-background-color: #6f7f94;
                selection-color: #ffffff;
                border: 1px solid #d6d6d6;
                outline: none;
            }
            """
        )
        for label, _ in self.STRICTNESS_OPTIONS:
            self.strictness_combo.addItem(label)

        self.camera_combo = QComboBox()
        self.camera_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.camera_combo.setStyleSheet(self.strictness_combo.styleSheet())

        self.start_btn = QPushButton("▶ Start Monitoring")
        self.stop_btn = QPushButton("⏹ Stop")
        for button in [self.start_btn, self.stop_btn]:
            button.setStyleSheet(Styles.button())
            disable_button_focus_rect(button)

        self.camera_preview = QLabel("Camera preview unavailable")
        self.camera_preview.setMinimumHeight(180)
        self.camera_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview.setStyleSheet(
            """
            QLabel {
                background-color: #f5f6f8;
                color: #444444;
                border: 1px solid #d7dbe1;
                border-radius: 8px;
                padding: 6px;
            }
            """
        )

        layout = QVBoxLayout()
        profile_row = QHBoxLayout()
        profile_row.addWidget(self.profile_label)
        profile_row.addStretch(1)
        layout.addLayout(profile_row)

        strictness_row = QHBoxLayout()
        strictness_row.addWidget(self.strictness_label)
        strictness_row.addWidget(self.strictness_combo)
        layout.addLayout(strictness_row)

        camera_row = QHBoxLayout()
        camera_row.addWidget(self.camera_label)
        camera_row.addWidget(self.camera_combo)
        layout.addLayout(camera_row)

        layout.addWidget(self.frame_label)
        layout.addWidget(self.ref_label)
        layout.addWidget(self.camera_preview_title)
        layout.addWidget(self.camera_preview_hint)
        layout.addWidget(self.camera_preview)
        layout.addWidget(self.profile_preview)
        layout.addWidget(self.monitor_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        self.setLayout(layout)

        self.monitor = MonitorService()
        self.monitor.status.connect(self.status_label.setText)
        self.monitor_controller = MonitorController(self.monitor)
        self._cached_available_camera_indices = None
        self._camera_indices_profile = None

        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.strictness_combo.currentIndexChanged.connect(self.on_strictness_changed)
        self.camera_combo.currentIndexChanged.connect(self.on_camera_changed)

        self.refresh()

    def select_profile(self):
        profiles = list_profiles()
        if not profiles:
            self.status_label.setText("No profiles found")
            return

        app_state.active_profile = profiles[0]
        self.profile_label.setText(f"Profile: {profiles[0]}")
        self.status_label.setText("Profile selected")

    def select_reference(self):
        if not app_state.active_profile:
            self.status_label.setText("Select a profile first")
            return

        self.status_label.setText("Select reference region…")
        _, message = dect.refrence_selector(app_state.active_profile)
        self.status_label.setText(message)

    def start(self):
        if app_state.monitoring_active:
            self.status_label.setText("Monitoring already running")
            return
        if not app_state.active_profile:
            self.status_label.setText("Select a profile first")
            return
        if not app_state.selected_reference:
            self.status_label.setText("Select a reference first")
            return

        self.monitor_controller.start()
        self.camera_preview.setPixmap(QPixmap())
        self.camera_preview.setText("Snapshot paused while monitoring")
        self.status_label.setText(f"Monitoring started ({app_state.selected_reference})")
        self.refresh()

    def stop(self):
        if not app_state.monitoring_active:
            self.status_label.setText("Monitoring is not running")
            return
        self.monitor_controller.stop()
        self.status_label.setText("Monitoring stopped")
        self.refresh()

    def closeEvent(self, event):
        super().closeEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.capture_camera_snapshot()

    def close(self):
        self.monitor_controller.stop()

    def refresh(self):
        self.profile_label.setText(f"Profile: {app_state.active_profile or 'None'}")
        self.frame_label.setText(f"Selected Frame: {app_state.selected_frame or 'None'}")
        self.ref_label.setText(f"Selected Reference: {app_state.selected_reference or 'None'}")

        if app_state.monitoring_active:
            self.monitor_label.setText(f"Monitoring: Running ({app_state.selected_reference})")
        else:
            self.monitor_label.setText("Monitoring: Stopped")

        self.start_btn.setEnabled(app_state.selected_reference is not None and not self.monitor.isRunning())
        self.update_detection_strictness()
        self.update_camera_indices()
        self.update_profile_preview()
        if app_state.monitoring_active:
            self.camera_preview.setPixmap(QPixmap())
            self.camera_preview.setText("Snapshot paused while monitoring")

    def update_detection_strictness(self):
        profile = app_state.active_profile
        resolved = get_detection_threshold(profile)
        index = self._strictness_index_for_threshold(resolved)
        self.strictness_combo.blockSignals(True)
        self.strictness_combo.setCurrentIndex(index)
        self.strictness_combo.blockSignals(False)
        self.strictness_combo.setEnabled(bool(profile))

    def _strictness_index_for_threshold(self, threshold):
        try:
            target = float(threshold)
        except (TypeError, ValueError):
            target = get_detection_threshold(None)
        distances = [abs(target - value) for _, value in self.STRICTNESS_OPTIONS]
        return distances.index(min(distances))

    def on_strictness_changed(self, index):
        if index < 0:
            return
        profile = app_state.active_profile
        if not profile:
            return
        _, threshold = self.STRICTNESS_OPTIONS[index]
        update_profile_detection_threshold(profile, threshold)


    def update_camera_indices(self):
        profile = app_state.active_profile
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()

        if not profile:
            self.camera_combo.blockSignals(False)
            self.camera_combo.setEnabled(False)
            self._camera_indices_profile = None
            return

        if self._cached_available_camera_indices is None or self._camera_indices_profile != profile:
            self._cached_available_camera_indices = self.monitor.list_available_camera_indices()
            self._camera_indices_profile = profile

        current_index = get_profile_camera_index(profile)
        options = list(self._cached_available_camera_indices)
        if current_index not in options:
            options.append(current_index)
        for idx in sorted(set(options)):
            self.camera_combo.addItem(str(idx), idx)
        selected = self.camera_combo.findData(current_index)
        if selected >= 0:
            self.camera_combo.setCurrentIndex(selected)
        self.camera_combo.blockSignals(False)
        self.camera_combo.setEnabled(self.camera_combo.count() > 0)

    def on_camera_changed(self, index):
        if index < 0:
            return
        profile = app_state.active_profile
        if not profile:
            return
        camera_index = self.camera_combo.itemData(index)
        if camera_index is None:
            return
        set_profile_camera_index(profile, camera_index)
        self.capture_camera_snapshot()

    def capture_camera_snapshot(self):
        if app_state.monitoring_active:
            self.camera_preview.setPixmap(QPixmap())
            self.camera_preview.setText("Snapshot paused while monitoring")
            return
        if not self.isVisible():
            return

        profile = app_state.active_profile
        if not profile:
            self.camera_preview.setPixmap(QPixmap())
            self.camera_preview.setText("Camera preview unavailable")
            return

        camera_index = get_profile_camera_index(profile)
        # One-shot snapshots avoid camera contention with monitoring capture and keep UI threading simple.
        cap = cv2.VideoCapture(camera_index)
        try:
            if not cap.isOpened():
                self.camera_preview.setPixmap(QPixmap())
                self.camera_preview.setText(f"No signal from camera {camera_index}")
                return

            ok, frame = cap.read()
            if not ok:
                self.camera_preview.setPixmap(QPixmap())
                self.camera_preview.setText(f"No signal from camera {camera_index}")
                return
        finally:
            cap.release()

        max_preview_width = 420
        height, width = frame.shape[:2]
        if width > max_preview_width:
            scale = max_preview_width / float(width)
            frame = cv2.resize(
                frame,
                (max_preview_width, max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = frame.shape
        image = QImage(frame.data, width, height, channels * width, QImage.Format.Format_RGB888).copy()

        painter = QPainter(image)
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.drawText(10, 24, f"Camera Index: {camera_index}")
        painter.end()

        pixmap = QPixmap.fromImage(image)
        self.camera_preview.setPixmap(
            pixmap.scaled(
                self.camera_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.camera_preview.setText("")

    def update_profile_preview(self):
        if not app_state.active_profile:
            self.profile_preview_bytes = None
            self.profile_preview.setText("No profile preview")
            self.profile_preview.setPixmap(QPixmap())
            return
        data = get_profile_icon_bytes(app_state.active_profile)
        if not data:
            self.profile_preview_bytes = None
            self.profile_preview.setText("Profile icon not found")
            self.profile_preview.setPixmap(QPixmap())
            return
        self.profile_preview_bytes = data
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.profile_preview.setPixmap(
            pixmap.scaled(
                self.profile_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.profile_preview.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.profile_preview_bytes:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(self.profile_preview_bytes)
        self.profile_preview.setPixmap(
            pixmap.scaled(
                self.profile_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
