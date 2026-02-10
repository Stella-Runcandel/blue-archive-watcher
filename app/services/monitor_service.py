"""Monitoring service orchestrating FFmpeg capture and processing threads."""
import logging
import threading
import time

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from app.app_state import app_state
from app.services.ffmpeg_tools import CaptureConfig, FfmpegNotFoundError
from app.services.monitor_pipeline import FrameQueue, FfmpegCapture
from core import detector as dect
from core import notifier as notif
from core.profiles import (
    get_profile_camera_device,
    get_profile_dirs,
    get_profile_fps,
    get_profile_frame_size,
    get_profile_frame_size_fallback,
)

_GLOBAL_CAPTURE_LOCK = threading.Lock()
_GLOBAL_CAPTURE = None
_GLOBAL_QUEUE = None
_GLOBAL_DEVICE = None
_GLOBAL_CONFIG = None
_GLOBAL_CAPTURE_USERS = 0  # Tracks active monitors to keep FFmpeg alive across restarts.


def _config_matches(config, other):
    """Compare config fields explicitly to avoid relying on dataclass equality."""
    if not config or not other:
        return False
    return (
        config.width == other.width
        and config.height == other.height
        and config.fps == other.fps
    )


def _ensure_global_capture(device_name, config):
    """Start or reuse a single global capture source for monitoring."""
    global _GLOBAL_CAPTURE, _GLOBAL_QUEUE, _GLOBAL_DEVICE, _GLOBAL_CONFIG, _GLOBAL_CAPTURE_USERS
    with _GLOBAL_CAPTURE_LOCK:
        if _GLOBAL_CAPTURE and _GLOBAL_CAPTURE.process and _GLOBAL_CAPTURE.process.poll() is None:
            if _GLOBAL_DEVICE == device_name and _config_matches(_GLOBAL_CONFIG, config):
                # Reference count prevents stop() from tearing down a shared capture.
                _GLOBAL_CAPTURE_USERS += 1
                return _GLOBAL_CAPTURE, _GLOBAL_QUEUE
            _GLOBAL_CAPTURE.stop()
            _GLOBAL_CAPTURE = None

        _GLOBAL_QUEUE = FrameQueue(maxlen=8)
        _GLOBAL_DEVICE = device_name
        _GLOBAL_CONFIG = config
        _GLOBAL_CAPTURE = FfmpegCapture(device_name, config, _GLOBAL_QUEUE)
        _GLOBAL_CAPTURE.start()
        _GLOBAL_CAPTURE_USERS = 1
        return _GLOBAL_CAPTURE, _GLOBAL_QUEUE


def _release_global_capture():
    """Release a global capture user and stop FFmpeg only when unused."""
    global _GLOBAL_CAPTURE, _GLOBAL_QUEUE, _GLOBAL_DEVICE, _GLOBAL_CONFIG, _GLOBAL_CAPTURE_USERS
    with _GLOBAL_CAPTURE_LOCK:
        if _GLOBAL_CAPTURE_USERS <= 0:
            return
        _GLOBAL_CAPTURE_USERS -= 1
        # Keep FFmpeg alive while other monitors are still using it.
        if _GLOBAL_CAPTURE_USERS > 0:
            return
        if _GLOBAL_CAPTURE:
            _GLOBAL_CAPTURE.stop()
        _GLOBAL_CAPTURE = None
        _GLOBAL_QUEUE = None
        _GLOBAL_DEVICE = None
        _GLOBAL_CONFIG = None


class MonitorService(QThread):
    """Background thread that captures camera frames and runs detection. Emits status on match."""

    status = pyqtSignal(str)
    metrics = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.running = False
        self.detector_state = dect.new_detector_state()
        self._stop_event = threading.Event()
        self._capture = None
        self._processing_thread = None
        self._capture_acquired = False

    def run(self):
        """Run capture + processing loops in background threads (non-UI)."""
        try:
            profile = app_state.active_profile
            if not profile:
                self.status.emit("No profile selected")
                return

            get_profile_dirs(profile)
            device_name = get_profile_camera_device(profile)
            if not device_name:
                self.status.emit("No camera selected")
                return

            width, height = get_profile_frame_size(profile)
            if not width or not height:
                width, height = get_profile_frame_size_fallback()
                logging.warning("Profile frame size not found; using fallback %sx%s", width, height)

            fps = get_profile_fps(profile)

            app_state.monitoring_active = True
            self.running = True
            self._stop_event.clear()
            self.status.emit("Monitoring...")
            self.detector_state = dect.new_detector_state()
            logging.info(
                "Monitoring start profile=%s device=%s fps=%s size=%sx%s",
                profile,
                device_name,
                fps,
                width,
                height,
            )

            config = CaptureConfig(width=width, height=height, fps=fps)
            try:
                self._capture, queue = _ensure_global_capture(device_name, config)
                # Track acquisition so stop() is idempotent and doesn't double-release.
                self._capture_acquired = True
            except FfmpegNotFoundError as exc:
                self.status.emit(f"FFmpeg not found ({exc})")
                return
            except Exception:
                logging.error("FFmpeg capture failed to start", exc_info=True)
                self.status.emit("FFmpeg capture failed")
                return

            self._processing_thread = threading.Thread(
                target=self._processing_loop,
                args=(profile, queue, width, height),
                daemon=True,
            )
            self._processing_thread.start()

            while not self._stop_event.is_set():
                if self._capture and self._capture.process and self._capture.process.poll() is not None:
                    logging.error("FFmpeg exited unexpectedly")
                    self.status.emit("FFmpeg exited unexpectedly")
                    break
                time.sleep(0.2)
        finally:
            self.stop()
            self.running = False
            app_state.monitoring_active = False
            self.status.emit("Stopped")
            logging.info("Monitoring stopped")

    def _processing_loop(self, profile, queue, width, height):
        """Process frames off the queue and emit deterministic detection results."""
        processed = 0
        last_metrics = time.time()
        last_confidence = 0.0
        selected_reference = app_state.selected_reference
        last_detection_time = None

        while not self._stop_event.is_set():
            item = queue.get(timeout=0.5)
            if item is None:
                continue

            _timestamp, raw = item
            frame = np.frombuffer(raw, dtype=np.uint8)
            expected = width * height * 3
            if frame.size != expected:
                logging.warning("Frame size mismatch: got %s expected %s", frame.size, expected)
                continue

            frame = frame.reshape((height, width, 3))
            try:
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
                        logging.error("Alert backend failure", exc_info=True)
            except Exception:
                logging.error("Detection crash", exc_info=True)
                self.status.emit("Detection failure")
                self._stop_event.set()
                break

            processed += 1
            now = time.time()
            if now - last_metrics >= 5:
                capture_fps = 0.0
                dropped = queue.dropped
                if self._capture:
                    capture_fps = self._capture.frames_captured / max(0.001, now - last_metrics)
                    self._capture.frames_captured = 0
                process_fps = processed / max(0.001, now - last_metrics)
                logging.info(
                    "Monitor metrics: capture_fps=%.2f process_fps=%.2f dropped=%s confidence=%.4f",
                    capture_fps,
                    process_fps,
                    dropped,
                    last_confidence,
                )
                queue_fill = (queue.size() / max(1, queue.maxlen)) * 100
                self.metrics.emit(
                    {
                        "capture_fps": capture_fps,
                        "process_fps": process_fps,
                        "dropped": dropped,
                        "queue_fill": queue_fill,
                        "profile": profile,
                        "monitoring": True,
                        "last_detection_time": last_detection_time,
                    }
                )
                processed = 0
                last_metrics = now

    def stop(self):
        """Stop capture + processing and release subprocess resources."""
        self._stop_event.set()
        if self._capture and self._capture_acquired:
            _release_global_capture()
            self._capture_acquired = False
        if self._processing_thread and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=5)
        app_state.monitoring_active = False
