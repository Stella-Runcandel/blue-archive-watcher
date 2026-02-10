"""Dashboard panel showing monitoring controls and live metrics."""
import time

import numpy as np
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.app_state import app_state
from app.controllers.monitor_controller import MonitorController
from app.services.ffmpeg_tools import list_video_devices
from app.services.monitor_service import (
    MonitorService,
    freeze_latest_global_frame,
    get_latest_global_frame,
)
from app.ui.theme import Styles
from app.ui.widget_utils import disable_button_focus_rect, disable_widget_interaction, make_preview_label
from core import detector as dect
from core.profiles import (
    get_detection_threshold,
    get_profile_camera_device,
    get_profile_fps,
    get_profile_frame_size,
    get_profile_frame_size_fallback,
    get_profile_icon_bytes,
    list_profiles,
    set_profile_camera_device,
    update_profile_detection_threshold,
    update_profile_fps,
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
        self.profile_preview_bytes = None
        self._frozen_frame = None
        self._cached_available_camera_indices = None

        self.profile_label = QLabel("Profile: None")
        self.frame_label = QLabel("Selected Frame: None")
        self.ref_label = QLabel("Selected Reference: None")
        self.monitor_label = QLabel("Monitoring: Stopped")
        self.status_label = QLabel("Status: Idle")
        self.capture_fps_label = QLabel("Capture FPS: --")
        self.process_fps_label = QLabel("Processing FPS: --")
        self.dropped_label = QLabel("Dropped Frames: --")
        self.queue_label = QLabel("Queue Fill: --")
        self.last_detection_label = QLabel("Last Detection: --")
        self.strictness_label = QLabel("Detection Strictness")
        self.camera_label = QLabel("Camera Device")
        self.fps_label = QLabel("Target FPS")
        self.camera_preview_title = QLabel("Camera Preview")
        self.camera_preview_hint = QLabel("Preview reads from monitoring frame queue")

        for label in [
            self.profile_label,
            self.frame_label,
            self.ref_label,
            self.monitor_label,
            self.status_label,
            self.capture_fps_label,
            self.process_fps_label,
            self.dropped_label,
            self.queue_label,
            self.last_detection_label,
            self.strictness_label,
            self.camera_label,
            self.fps_label,
            self.camera_preview_title,
            self.camera_preview_hint,
        ]:
            disable_widget_interaction(label)
            label.setStyleSheet(Styles.info_label())

        self.profile_preview = make_preview_label("No profile preview", 180, "profile_preview")
        self.profile_preview.setFixedHeight(220)

        self.strictness_combo = QComboBox()
        self.strictness_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.strictness_combo.setStyleSheet(
            """
            QComboBox { background-color: #ffffff; color: #111111; border: 1px solid #d6d6d6; border-radius: 6px; padding: 6px 10px; outline: none; }
            QComboBox:hover { border-color: #cdcdcd; }
            QComboBox:focus { border: 2px solid #7f8fa3; outline: none; }
            QComboBox::drop-down { background-color: #ffffff; border: 0; width: 20px; }
            QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #111111; width: 0; height: 0; }
            QComboBox QAbstractItemView { background-color: #ffffff; color: #111111; selection-background-color: #6f7f94; selection-color: #ffffff; border: 1px solid #d6d6d6; outline: none; }
            """
        )
        for label, _ in self.STRICTNESS_OPTIONS:
            self.strictness_combo.addItem(label)

        self.camera_combo = QComboBox()
        self.camera_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.camera_combo.setStyleSheet(self.strictness_combo.styleSheet())
        self.camera_refresh_btn = QPushButton("↻ Refresh")
        self.camera_refresh_btn.setStyleSheet(Styles.button())
        disable_button_focus_rect(self.camera_refresh_btn)

        self.fps_spinbox = QSpinBox()
        self.fps_spinbox.setRange(1, 60)
        self.fps_spinbox.setSuffix(" FPS")
        self.fps_spinbox.setStyleSheet(self.strictness_combo.styleSheet())

        self.start_btn = QPushButton("▶ Start Monitoring")
        self.stop_btn = QPushButton("⏹ Stop")
        self.freeze_btn = QPushButton("📸 Capture Snapshot")
        self.unfreeze_btn = QPushButton("▶ Live Preview")
        for button in [self.start_btn, self.stop_btn, self.freeze_btn, self.unfreeze_btn]:
            button.setStyleSheet(Styles.button())
            disable_button_focus_rect(button)

        self.camera_preview = QLabel("Camera preview unavailable")
        self.camera_preview.setFixedHeight(260)
        self.camera_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview.setScaledContents(False)
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

        content_layout = QVBoxLayout()
        profile_row = QHBoxLayout()
        profile_row.addWidget(self.profile_label)
        profile_row.addWidget(self.monitor_label)

        selected_row = QHBoxLayout()
        selected_row.addWidget(self.frame_label)
        selected_row.addWidget(self.ref_label)

        settings_row = QHBoxLayout()
        settings_row.addWidget(self.strictness_label)
        settings_row.addWidget(self.strictness_combo)
        settings_row.addWidget(self.fps_label)
        settings_row.addWidget(self.fps_spinbox)

        camera_row = QHBoxLayout()
        camera_row.addWidget(self.camera_label)
        camera_row.addWidget(self.camera_combo)
        camera_row.addWidget(self.camera_refresh_btn)

        controls_row = QHBoxLayout()
        controls_row.addWidget(self.start_btn)
        controls_row.addWidget(self.stop_btn)
        controls_row.addWidget(self.freeze_btn)
        controls_row.addWidget(self.unfreeze_btn)

        metrics_row = QHBoxLayout()
        metrics_row.addWidget(self.capture_fps_label)
        metrics_row.addWidget(self.process_fps_label)
        metrics_row.addWidget(self.dropped_label)

        metrics_row2 = QHBoxLayout()
        metrics_row2.addWidget(self.queue_label)
        metrics_row2.addWidget(self.last_detection_label)

        content_layout.addLayout(profile_row)
        content_layout.addLayout(selected_row)
        content_layout.addLayout(settings_row)
        content_layout.addLayout(camera_row)
        content_layout.addLayout(controls_row)
        content_layout.addWidget(self.status_label)
        content_layout.addLayout(metrics_row)
        content_layout.addLayout(metrics_row2)
        content_layout.addWidget(self.camera_preview_title)
        content_layout.addWidget(self.camera_preview_hint)
        content_layout.addWidget(self.camera_preview)
        content_layout.addWidget(self.profile_preview)
        content_layout.addStretch()

        content_widget = QWidget()
        content_widget.setLayout(content_layout)

        scroll = QScrollArea()
        scroll.setWidget(content_widget)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(Styles.scroll_area())

        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)

        self.monitor = MonitorService()
        self.monitor.status.connect(self.status_label.setText)
        self.monitor.metrics.connect(self.on_metrics_update)
        self.monitor_controller = MonitorController(self.monitor)

        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.freeze_btn.clicked.connect(self.freeze_frame)
        self.unfreeze_btn.clicked.connect(self.unfreeze_frame)
        self.strictness_combo.currentIndexChanged.connect(self.on_strictness_changed)
        self.camera_combo.currentIndexChanged.connect(self.on_camera_changed)
        self.camera_refresh_btn.clicked.connect(self.refresh_camera_devices)
        self.fps_spinbox.valueChanged.connect(self.on_fps_changed)

        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(120)
        self.preview_timer.timeout.connect(self.update_camera_preview)
        self.preview_timer.start()

        self.refresh_camera_devices()
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
        _, message = dect.reference_selector(app_state.active_profile)
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
        self._frozen_frame = None
        self.monitor_controller.start()
        self.status_label.setText(f"Monitoring started ({app_state.selected_reference})")
        self.refresh()

    def stop(self):
        if not app_state.monitoring_active:
            self.status_label.setText("Monitoring is not running")
            return
        self.monitor_controller.stop()
        self.status_label.setText("Monitoring stopped")
        self.refresh()

    def freeze_frame(self):
        frozen = freeze_latest_global_frame()
        if frozen is None:
            self.status_label.setText("No frame available to capture")
            return
        self._frozen_frame = frozen
        self.status_label.setText("Snapshot captured")
        self.update_camera_preview()

    def unfreeze_frame(self):
        self._frozen_frame = None
        self.status_label.setText("Live preview")

    def closeEvent(self, event):
        self.preview_timer.stop()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.update_camera_preview()

    def close(self):
        self.preview_timer.stop()
        self.monitor_controller.stop()

    def refresh(self):
        self.profile_label.setText(f"Profile: {app_state.active_profile or 'None'}")
        self.frame_label.setText(f"Selected Frame: {app_state.selected_frame or 'None'}")
        self.ref_label.setText(f"Selected Reference: {app_state.selected_reference or 'None'}")

        if app_state.monitoring_active:
            self.monitor_label.setText(f"Monitoring: Running ({app_state.selected_reference})")
        else:
            self.monitor_label.setText("Monitoring: Stopped")
            self.capture_fps_label.setText("Capture FPS: --")
            self.process_fps_label.setText("Processing FPS: --")
            self.dropped_label.setText("Dropped Frames: --")
            self.queue_label.setText("Queue Fill: --")
            self.last_detection_label.setText("Last Detection: --")

        self.start_btn.setEnabled(app_state.selected_reference is not None and not self.monitor.isRunning())
        self.stop_btn.setEnabled(self.monitor.isRunning())
        self.freeze_btn.setEnabled(True)
        self.unfreeze_btn.setEnabled(True)
        self.update_detection_strictness()
        self.update_fps_setting()
        self.update_camera_indices()
        self.update_profile_preview()

    def update_detection_strictness(self):
        profile = app_state.active_profile
        resolved = get_detection_threshold(profile)
        index = self._strictness_index_for_threshold(resolved)
        self.strictness_combo.blockSignals(True)
        self.strictness_combo.setCurrentIndex(index)
        self.strictness_combo.blockSignals(False)
        self.strictness_combo.setEnabled(bool(profile))

    def update_fps_setting(self):
        profile = app_state.active_profile
        self.fps_spinbox.blockSignals(True)
        self.fps_spinbox.setValue(get_profile_fps(profile))
        self.fps_spinbox.blockSignals(False)
        self.fps_spinbox.setEnabled(bool(profile))

    def _strictness_index_for_threshold(self, threshold):
        try:
            target = float(threshold)
        except (TypeError, ValueError):
            target = get_detection_threshold(None)
        distances = [abs(target - value) for _, value in self.STRICTNESS_OPTIONS]
        return distances.index(min(distances))

    def on_fps_changed(self, value):
        if app_state.active_profile:
            update_profile_fps(app_state.active_profile, value)

    def on_strictness_changed(self, index):
        if index < 0 or not app_state.active_profile:
            return
        _, threshold = self.STRICTNESS_OPTIONS[index]
        update_profile_detection_threshold(app_state.active_profile, threshold)

    def update_camera_indices(self):
        profile = app_state.active_profile
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        if not profile:
            self.camera_combo.blockSignals(False)
            self.camera_combo.setEnabled(False)
            self.camera_refresh_btn.setEnabled(False)
            return

        current_device = get_profile_camera_device(profile)
        devices = list(self._cached_available_camera_indices or [])
        if current_device and current_device not in devices:
            devices.append(current_device)

        unique_devices = list(dict.fromkeys(devices))
        if not unique_devices:
            self.camera_combo.addItem("No cameras found")
            self.camera_combo.model().item(0).setEnabled(False)
            self.camera_combo.setEnabled(False)
        else:
            for device in unique_devices:
                self.camera_combo.addItem(str(device), device)
            selected = self.camera_combo.findData(current_device)
            if selected >= 0:
                self.camera_combo.setCurrentIndex(selected)
            self.camera_combo.setEnabled(True)

        self.camera_combo.blockSignals(False)
        self.camera_refresh_btn.setEnabled(True)

    def on_camera_changed(self, index):
        if index < 0 or not app_state.active_profile:
            return
        device_name = self.camera_combo.itemData(index)
        if device_name is None:
            return
        set_profile_camera_device(app_state.active_profile, device_name)

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

    def on_metrics_update(self, payload):
        capture_fps = payload.get("capture_fps", 0.0)
        process_fps = payload.get("process_fps", 0.0)
        dropped = payload.get("dropped", 0)
        queue_fill = payload.get("queue_fill", 0.0)
        last_detection_time = payload.get("last_detection_time")
        self.capture_fps_label.setText(f"Capture FPS: {capture_fps:.2f}")
        self.process_fps_label.setText(f"Processing FPS: {process_fps:.2f}")
        self.dropped_label.setText(f"Dropped Frames: {dropped}")
        self.queue_label.setText(f"Queue Fill: {queue_fill:.0f}%")
        if last_detection_time:
            self.last_detection_label.setText(f"Last Detection: {time.ctime(last_detection_time)}")
        else:
            self.last_detection_label.setText("Last Detection: --")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.profile_preview_bytes:
            pixmap = QPixmap()
            pixmap.loadFromData(self.profile_preview_bytes)
            self.profile_preview.setPixmap(
                pixmap.scaled(
                    self.profile_preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.update_camera_preview()

    def refresh_camera_devices(self):
        self._cached_available_camera_indices = list_video_devices(force_refresh=True)
        self.update_camera_indices()

    def update_camera_preview(self):
        if not self.isVisible():
            return

        frame_item = self._frozen_frame or get_latest_global_frame()
        if frame_item is None:
            self.camera_preview.setPixmap(QPixmap())
            self.camera_preview.setText("Camera preview unavailable")
            return

        profile = app_state.active_profile
        width, height = get_profile_frame_size(profile)
        if not width or not height:
            width, height = get_profile_frame_size_fallback()

        _, raw = frame_item
        frame = np.frombuffer(raw, dtype=np.uint8)
        expected = width * height * 3
        if frame.size != expected:
            self.camera_preview.setPixmap(QPixmap())
            self.camera_preview.setText("Preview size mismatch")
            return

        rgb = frame.reshape((height, width, 3))[:, :, ::-1].copy()
        image = QImage(
            rgb.data,
            width,
            height,
            width * 3,
            QImage.Format.Format_RGB888,
        ).copy()
        pixmap = QPixmap.fromImage(image)
        self.camera_preview.setPixmap(
            pixmap.scaled(
                self.camera_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.camera_preview.setText("")
