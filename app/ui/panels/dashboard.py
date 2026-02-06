from PyQt6.QtWidgets import (
    QWidget,
    QPushButton,
    QLabel,
    QVBoxLayout,
    QComboBox,
    QHBoxLayout,
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from core import detector as dect
from core.profiles import (
    list_profiles,
    get_profile_icon_bytes,
    get_detection_threshold,
    update_profile_detection_threshold,
)

from app.app_state import app_state
from app.services.monitor_service import MonitorService
from app.controllers.monitor_controller import MonitorController


class DashboardPanel(QWidget):
    """
    Main dashboard panel.
    Responsibilities:
    - Show current profile
    - Show monitoring state
    - Start / stop monitoring
    - Entry point to other panels
    """

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

        # ---- status labels ----
        self.profile_label = QLabel("Profile: None")
        self.frame_label = QLabel("Selected Frame: None")
        self.ref_label = QLabel("Selected Reference: None")
        self.profile_preview_bytes = None
        self.profile_preview = QLabel("No profile preview")
        self.profile_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.profile_preview.setMinimumHeight(180)
        self.profile_preview.setStyleSheet(
            "border: 1px solid #595148; background-color: #332f2a; color: #c8c1b7;"
        )
        self.monitor_label = QLabel("Monitoring: Stopped")
        self.status_label = QLabel("Status: Idle")
        self.strictness_label = QLabel("Detection Strictness")
        self.strictness_combo = QComboBox()
        for label, _ in self.STRICTNESS_OPTIONS:
            self.strictness_combo.addItem(label)

        # ---- action buttons ----
        self.start_btn = QPushButton("▶ Start Monitoring")
        self.stop_btn = QPushButton("⏹ Stop")

        # ---- layout ----
        layout = QVBoxLayout()
        profile_row = QHBoxLayout()
        profile_row.addWidget(self.profile_label)
        profile_row.addStretch(1)
        layout.addLayout(profile_row)
        strictness_row = QHBoxLayout()
        strictness_row.addWidget(self.strictness_label)
        strictness_row.addWidget(self.strictness_combo)
        layout.addLayout(strictness_row)
        layout.addWidget(self.frame_label)
        layout.addWidget(self.ref_label)
        layout.addWidget(self.profile_preview)
        layout.addWidget(self.monitor_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        self.setLayout(layout)

        # ---- services ----
        self.monitor = MonitorService()
        self.monitor.status.connect(self.status_label.setText)

        # ---- controllers ----
        self.monitor_controller = MonitorController(self.monitor)

        # ---- signals ----
        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.strictness_combo.currentIndexChanged.connect(
            self.on_strictness_changed
        )

        # initial state
        self.refresh()


    def select_profile(self):
        profiles = list_profiles()
        if not profiles:
            self.label.setText("No profiles found")
            return

        app_state.active_profile = profiles[0]
        self.profile_label.setText(f"Profile: {profiles[0]}")
        self.label.setText("Profile selected")

    def select_reference(self):
        if not app_state.active_profile:
            self.label.setText("Select a profile first")
            return

        self.label.setText("Select reference region…")
        dect.refrence_selector(app_state.active_profile)

        # 🔍 show result clearly
        from core.profiles import get_profile_dirs
        import os

        refs = os.listdir(get_profile_dirs(app_state.active_profile)["references"])
        if refs:
            self.label.setText(f"Reference added: {refs[-1]}")
        else:
            self.label.setText("No reference saved")

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
        self.status_label.setText(
            f"Monitoring started ({app_state.selected_reference})"
        )

        self.refresh()

    def stop(self):
        if not app_state.monitoring_active:
            self.status_label.setText("Monitoring is not running")
            return

        self.monitor_controller.stop()
        self.status_label.setText("Monitoring stopped")
        self.refresh()


    def close(self):
        self.monitor_controller.stop()

    def refresh(self):
        self.profile_label.setText(
            f"Profile: {app_state.active_profile or 'None'}"
        )

        self.frame_label.setText(
            f"Selected Frame: {app_state.selected_frame or 'None'}"
        )

        self.ref_label.setText(
            f"Selected Reference: {app_state.selected_reference or 'None'}"
        )

        if self.monitor.isRunning():
            self.monitor_label.setText("Monitoring: Running")
        else:
            self.monitor_label.setText("Monitoring: Stopped")

        if app_state.monitoring_active:
            self.monitor_label.setText(
                f"Monitoring: Running ({app_state.selected_reference})"
            )
        else:
            self.monitor_label.setText("Monitoring: Stopped")

        # Start is guarded, Stop is NOT
        self.start_btn.setEnabled(
            app_state.selected_reference is not None
            and not self.monitor.isRunning()
        )
        self.update_detection_strictness()
        self.update_profile_preview()

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
        distances = [
            abs(target - value)
            for _, value in self.STRICTNESS_OPTIONS
        ]
        return distances.index(min(distances))

    def on_strictness_changed(self, index):
        if index < 0:
            return
        profile = app_state.active_profile
        if not profile:
            return
        _, threshold = self.STRICTNESS_OPTIONS[index]
        update_profile_detection_threshold(profile, threshold)

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
        scaled = pixmap.scaled(
            self.profile_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.profile_preview.setPixmap(scaled)
        self.profile_preview.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.profile_preview_bytes:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(self.profile_preview_bytes)
        scaled = pixmap.scaled(
            self.profile_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.profile_preview.setPixmap(scaled)
