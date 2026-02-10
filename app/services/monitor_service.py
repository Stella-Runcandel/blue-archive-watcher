"""Monitoring service orchestrating FFmpeg capture and processing threads."""
from __future__ import annotations

import logging
import threading
import time

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from app.app_state import app_state
from app.services.ffmpeg_capture_supervisor import LogLevel
from app.services.ffmpeg_tools import CaptureConfig, FfmpegNotFoundError
from app.services.frame_bus import FrameQueue
from app.services.frame_consumers import DetectionConsumer, MetricsConsumer, SnapshotConsumer
from app.services.monitor_state_machine import InvalidTransition, MonitoringState, MonitoringStateMachine
from app.services.monitor_pipeline import FfmpegCapture
from core import detector as dect
from core import notifier as notif
from core.profiles import (
    get_profile_camera_device,
    get_profile_dirs,
    get_profile_fps,
    get_profile_frame_size,
    get_profile_frame_size_fallback,
)

_GLOBAL_LOCK = threading.Lock()
_GLOBAL_CAPTURE: FfmpegCapture | None = None
_GLOBAL_QUEUE: FrameQueue | None = None
_GLOBAL_USERS = 0


def _ensure_global_capture(device_name: str, config: CaptureConfig) -> tuple[FfmpegCapture, FrameQueue]:
    global _GLOBAL_CAPTURE, _GLOBAL_QUEUE, _GLOBAL_USERS
    with _GLOBAL_LOCK:
        if _GLOBAL_CAPTURE and _GLOBAL_CAPTURE.is_alive():
            _GLOBAL_USERS += 1
            return _GLOBAL_CAPTURE, _GLOBAL_QUEUE

        _GLOBAL_QUEUE = FrameQueue(maxlen=8)
        _GLOBAL_CAPTURE = FfmpegCapture(device_name=device_name, config=config, frame_queue=_GLOBAL_QUEUE)
        _GLOBAL_CAPTURE.start()
        _GLOBAL_USERS = 1
        return _GLOBAL_CAPTURE, _GLOBAL_QUEUE


def _release_global_capture(clear_queue: bool = False) -> None:
    global _GLOBAL_CAPTURE, _GLOBAL_QUEUE, _GLOBAL_USERS
    with _GLOBAL_LOCK:
        if _GLOBAL_USERS <= 0:
            return
        _GLOBAL_USERS -= 1
        if _GLOBAL_USERS > 0:
            return
        if _GLOBAL_CAPTURE:
            _GLOBAL_CAPTURE.stop()
        if _GLOBAL_QUEUE and clear_queue:
            _GLOBAL_QUEUE.clear(stale=True)
        _GLOBAL_CAPTURE = None
        _GLOBAL_QUEUE = None


def get_latest_global_frame():
    with _GLOBAL_LOCK:
        if not _GLOBAL_QUEUE:
            return None
        packet = _GLOBAL_QUEUE.peek_latest()
        if packet is None:
            return None
        return (packet.timestamp, packet.payload)


def freeze_latest_global_frame():
    with _GLOBAL_LOCK:
        if not _GLOBAL_QUEUE:
            return None
        snap = SnapshotConsumer(_GLOBAL_QUEUE).capture_snapshot()
        if not snap:
            return None
        return (snap.timestamp, snap.payload)


class MonitorService(QThread):
    status = pyqtSignal(str)
    metrics = pyqtSignal(dict)
    state_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.detector_state = dect.new_detector_state()
        self._stop_event = threading.Event()
        self._capture = None
        self._processing_thread = None
        self._capture_acquired = False
        self._state = MonitoringStateMachine()
        self._detection_consumer = DetectionConsumer()
        self._metrics = MetricsConsumer()

    def current_state(self) -> MonitoringState:
        return self._state.state

    def _set_state(self, text: str, transition) -> bool:
        try:
            transition()
        except InvalidTransition as exc:
            self.status.emit(f"State error: {exc}")
            return False
        self.state_changed.emit(text)
        return True

    def run(self):
        if not self._set_state(MonitoringState.STARTING.value, self._state.request_start):
            return
        try:
            profile = app_state.active_profile
            if not profile:
                self.status.emit("No profile selected")
                self._state.mark_failed()
                return

            get_profile_dirs(profile)
            if not app_state.selected_reference:
                self.status.emit("No reference selected")
                self._state.mark_failed()
                return

            device_name = get_profile_camera_device(profile)
            if not device_name:
                self.status.emit("No camera selected")
                self._state.mark_failed()
                return

            width, height = get_profile_frame_size(profile)
            if not width or not height:
                width, height = get_profile_frame_size_fallback()
            fps = get_profile_fps(profile)

            config = CaptureConfig(width=width, height=height, fps=fps)
            self._capture, queue = _ensure_global_capture(device_name, config)
            self._capture_acquired = True

            self._state.mark_running()
            self.state_changed.emit(MonitoringState.RUNNING.value)
            app_state.monitoring_active = True
            self.running = True
            self.status.emit("Monitoring...")

            self._processing_thread = threading.Thread(
                target=self._processing_loop,
                args=(profile, queue, width, height),
                daemon=True,
            )
            self._processing_thread.start()

            while not self._stop_event.is_set():
                if self._capture and not self._capture.is_alive():
                    self.status.emit("FFmpeg exited unexpectedly")
                    self._state.mark_failed()
                    break
                self._drain_ffmpeg_logs()
                time.sleep(0.15)
        except FfmpegNotFoundError as exc:
            self.status.emit(f"FFmpeg not found ({exc})")
            self._state.mark_failed()
        except Exception as exc:
            logging.error("Monitoring crash", exc_info=True)
            self.status.emit(f"Monitoring failure ({exc})")
            try:
                self._state.mark_failed()
            except InvalidTransition:
                pass
        finally:
            self.stop(clear_queue=self._state.state == MonitoringState.FAILED)

    def _drain_ffmpeg_logs(self):
        if not self._capture:
            return
        while not self._capture.log_events.empty():
            event = self._capture.log_events.get_nowait()
            if event.level == LogLevel.ERROR:
                self.status.emit(f"FFmpeg error: {event.message}")

    def _processing_loop(self, profile, queue: FrameQueue, width: int, height: int):
        processed = 0
        start = time.time()
        last_confidence = 0.0
        selected_reference = app_state.selected_reference
        last_detection_time = None

        while not self._stop_event.is_set():
            pkt = queue.get(timeout=0.5)
            if pkt is None:
                continue

            self._metrics.on_frame()
            raw = pkt.payload
            frame = np.frombuffer(raw, dtype=np.uint8)
            expected = width * height * 3
            if frame.size != expected:
                continue
            if self._detection_consumer.is_paused():
                continue

            frame = frame.reshape((height, width, 3))
            result = dect.evaluate_frame(
                profile,
                frame,
                self.detector_state,
                selected_reference=selected_reference,
            )
            last_confidence = result.confidence
            if result.matched:
                self.status.emit("Dialogue detected!")
                last_detection_time = result.timestamp
                try:
                    notif.alert()
                except Exception:
                    logging.exception("Alert backend failure")

            processed += 1
            now = time.time()
            if now - start >= 5:
                self.metrics.emit(
                    {
                        "capture_fps": self._metrics.capture_fps,
                        "process_fps": processed / max(0.001, now - start),
                        "dropped": queue.dropped_frames,
                        "queue_fill": (queue.size() / max(1, queue.maxlen)) * 100,
                        "profile": profile,
                        "monitoring": True,
                        "last_detection_time": last_detection_time,
                        "confidence": last_confidence,
                    }
                )
                processed = 0
                start = now

    def stop(self, clear_queue: bool = False):
        if self._state.state in (MonitoringState.IDLE, MonitoringState.STOPPING):
            return

        try:
            self._state.request_stop()
            self.state_changed.emit(MonitoringState.STOPPING.value)
        except InvalidTransition:
            pass

        self._stop_event.set()
        if self._processing_thread and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=5)

        if self._capture and self._capture_acquired:
            _release_global_capture(clear_queue=clear_queue)
            self._capture_acquired = False

        self.running = False
        app_state.monitoring_active = False

        try:
            self._state.mark_idle()
        except InvalidTransition:
            self._state = MonitoringStateMachine()
        self.state_changed.emit(MonitoringState.IDLE.value)
        self.status.emit("Stopped")
