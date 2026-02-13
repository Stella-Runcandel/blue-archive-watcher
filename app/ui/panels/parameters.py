"""Parameters panel with sandboxed runtime debug configuration."""
from __future__ import annotations

import time

import cv2
import numpy as np
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.app_state import app_state
from app.services.monitor_service import get_latest_global_frame, get_latest_preview_frame
from app.services.capture_constants import CANONICAL_HEIGHT, CANONICAL_WIDTH
from app.services.parameters_config import BaseProfileConfig, RuntimeDebugConfig, apply_debug_settings
from app.ui.panel_header import PanelHeader
from app.ui.theme import Styles
from app.ui.widget_utils import disable_button_focus_rect, disable_widget_interaction
from core import detector as dect


class ParametersPanel(QWidget):
    def __init__(self, nav):
        super().__init__()
        self.nav = nav
        self.base_config: BaseProfileConfig | None = None
        self.runtime_config: RuntimeDebugConfig | None = None
        self.detector_state = dect.new_detector_state()
        self.snapshot_frame: np.ndarray | None = None
        self._last_preview_ts = 0.0

        self.header = PanelHeader("Parameters", nav)
        self.sandbox_label = QLabel("SANDBOX MODE ACTIVE")
        disable_widget_interaction(self.sandbox_label)
        self.sandbox_label.setStyleSheet(Styles.info_label("#b86f3e"))

        self.threshold_label = QLabel("Detection Threshold")
        disable_widget_interaction(self.threshold_label)
        self.threshold_label.setStyleSheet(Styles.info_label())

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.50, 0.95)
        self.threshold_spin.setSingleStep(0.01)
        self.threshold_spin.setDecimals(2)

        self.apply_btn = QPushButton("Apply Debug Settings")
        self.capture_btn = QPushButton("Capture Snapshot")
        self.clear_snapshot_btn = QPushButton("Clear Snapshot")
        self.test_btn = QPushButton("Test Detection")
        for button in [self.apply_btn, self.capture_btn, self.clear_snapshot_btn, self.test_btn]:
            button.setStyleSheet(Styles.button())
            disable_button_focus_rect(button)

        self.preview_label = QLabel("Preview unavailable")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedHeight(320)
        self.preview_label.setStyleSheet(
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

        self.metrics_label = QLabel("Confidence: -- | FPS: -- | Latency: -- ms")
        disable_widget_interaction(self.metrics_label)
        self.metrics_label.setStyleSheet(Styles.info_label())

        self.test_output = QLabel("Test output: --")
        self.test_output.setWordWrap(True)
        disable_widget_interaction(self.test_output)
        self.test_output.setStyleSheet(Styles.info_label())

        left = QVBoxLayout()
        left.addWidget(self.sandbox_label)
        left.addWidget(self.threshold_label)
        left.addWidget(self.threshold_spin)
        left.addWidget(self.capture_btn)
        left.addWidget(self.clear_snapshot_btn)
        left.addWidget(self.test_btn)
        left.addWidget(self.apply_btn)
        left.addStretch()

        right = QVBoxLayout()
        right.addWidget(self.preview_label)
        right.addWidget(self.metrics_label)
        right.addWidget(self.test_output)

        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addLayout(right, 2)

        root = QVBoxLayout()
        root.addWidget(self.header)
        root.addLayout(body)
        self.setLayout(root)

        self.threshold_spin.valueChanged.connect(self._on_threshold_changed)
        self.apply_btn.clicked.connect(self._on_apply)
        self.capture_btn.clicked.connect(self._capture_snapshot)
        self.clear_snapshot_btn.clicked.connect(self._clear_snapshot)
        self.test_btn.clicked.connect(self._test_detection)

        self._init_runtime_config()
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self._refresh_preview)
        self.preview_timer.start(250)

    def _init_runtime_config(self):
        profile = app_state.active_profile
        if not profile:
            self.test_output.setText("Test output: Select a profile to use Parameters.")
            self.threshold_spin.setEnabled(False)
            self.apply_btn.setEnabled(False)
            self.runtime_config = None
            self.base_config = None
            return
        self.base_config = BaseProfileConfig.from_profile(profile)
        self.runtime_config = RuntimeDebugConfig.from_base(self.base_config)
        self.threshold_spin.blockSignals(True)
        self.threshold_spin.setValue(self.runtime_config.detection_threshold)
        self.threshold_spin.blockSignals(False)

    def _on_threshold_changed(self, value: float):
        if self.runtime_config:
            self.runtime_config.detection_threshold = float(value)

    def _capture_snapshot(self):
        frame = self._get_source_frame()
        if frame is None:
            self.test_output.setText("Test output: No frame available for snapshot.")
            return
        self.snapshot_frame = frame.copy()
        self.test_output.setText("Test output: Snapshot captured and preview frozen.")

    def _clear_snapshot(self):
        self.snapshot_frame = None
        self.test_output.setText("Test output: Snapshot cleared.")

    def _get_source_frame(self) -> np.ndarray | None:
        packet = get_latest_preview_frame() or get_latest_global_frame()
        if not packet:
            return None
        _ts, payload = packet
        if isinstance(payload, np.ndarray):
            return payload.copy()
        frame = np.frombuffer(payload, dtype=np.uint8)
        expected = CANONICAL_WIDTH * CANONICAL_HEIGHT
        if frame.size != expected:
            return None
        return frame.reshape((CANONICAL_HEIGHT, CANONICAL_WIDTH)).copy()

    def _detection_config(self) -> dect.DetectionConfig | None:
        if not self.runtime_config:
            return None
        return dect.DetectionConfig(detection_threshold=self.runtime_config.detection_threshold)

    def _run_detection_once(self, frame: np.ndarray):
        profile = app_state.active_profile
        if not profile:
            return None, 0.0
        started = time.perf_counter()
        result = dect.evaluate_frame(
            profile,
            frame,
            self.detector_state,
            selected_reference=app_state.selected_reference,
            config=self._detection_config(),
            sandbox_mode=True,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return result, latency_ms

    def _refresh_preview(self):
        if not self.runtime_config:
            return
        frame = self.snapshot_frame if self.snapshot_frame is not None else self._get_source_frame()
        if frame is None:
            self.preview_label.setText("Preview unavailable")
            return
        result, latency_ms = self._run_detection_once(frame)
        if result is None:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        if result.bbox:
            x, y, w, h = result.bbox
            cv2.rectangle(rgb, (x, y), (x + w, y + h), (0, 220, 0), 2)
        cv2.putText(rgb, f"Conf: {result.confidence:.3f}", (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 220, 50), 2)
        img = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(pix)
        now = time.time()
        fps = 0.0 if self._last_preview_ts <= 0 else (1.0 / max(0.001, now - self._last_preview_ts))
        self._last_preview_ts = now
        self.metrics_label.setText(f"Confidence: {result.confidence:.3f} | FPS: {fps:.1f} | Latency: {latency_ms:.1f} ms")

    def _test_detection(self):
        frame = self.snapshot_frame if self.snapshot_frame is not None else self._get_source_frame()
        if frame is None:
            self.test_output.setText("Test output: No frame available.")
            return
        result, latency_ms = self._run_detection_once(frame)
        if result is None:
            self.test_output.setText("Test output: Detection unavailable.")
            return
        self.test_output.setText(
            f"Test output: matched={result.matched}, reference={result.reference}, confidence={result.confidence:.3f}, latency={latency_ms:.1f}ms"
        )

    def _on_apply(self):
        if not self.base_config or not self.runtime_config:
            return
        self.base_config = apply_debug_settings(self.base_config, self.runtime_config)
        self.test_output.setText("Test output: Debug settings applied to profile.")

    def on_panel_close(self):
        if hasattr(self, "preview_timer"):
            self.preview_timer.stop()
        self.runtime_config = None
        self.snapshot_frame = None
