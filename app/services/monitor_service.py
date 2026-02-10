"""Monitoring service orchestrating FFmpeg capture and processing threads."""
from __future__ import annotations

import logging
import threading
import time

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from app.app_state import app_state
from app.services.ffmpeg_capture_supervisor import LogLevel
from app.services.ffmpeg_tools import (
    CaptureConfig,
    FfmpegNotFoundError,
    build_capture_input_candidates,
)
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
    set_profile_camera_device,
)

_GLOBAL_LOCK = threading.Lock()
_GLOBAL_CAPTURE: FfmpegCapture | None = None
_GLOBAL_QUEUE: FrameQueue | None = None
_GLOBAL_USERS = 0
_GLOBAL_INPUT_TOKEN: str | None = None
_GLOBAL_CONFIG: CaptureConfig | None = None

_PREVIEW_LOCK = threading.Lock()
_PREVIEW_CAPTURE: FfmpegCapture | None = None
_PREVIEW_QUEUE: FrameQueue | None = None
_PREVIEW_INPUT_TOKEN: str | None = None
_PREVIEW_CONFIG: CaptureConfig | None = None
_PREVIEW_PAUSED_FOR_MONITORING = False
_PREVIEW_LAST_RESTART_AT = 0.0
_PREVIEW_RESTART_DEBOUNCE_SEC = 0.5


def _build_monitoring_config_ladder(width: int, height: int, fps: int, *, is_virtual: bool) -> list[CaptureConfig]:
    requested = CaptureConfig(width=width, height=height, fps=fps, input_width=width, input_height=height, input_fps=fps, label="requested")
    implicit = CaptureConfig(width=width, height=height, fps=fps, input_width=None, input_height=None, input_fps=None, label="implicit-default")
    if is_virtual:
        return [requested, implicit]
    return [implicit]


def _ensure_global_capture(
    input_token: str,
    config: CaptureConfig,
    *,
    allow_input_tuning: bool,
) -> tuple[FfmpegCapture, FrameQueue]:
    global _GLOBAL_CAPTURE, _GLOBAL_QUEUE, _GLOBAL_USERS, _GLOBAL_INPUT_TOKEN, _GLOBAL_CONFIG
    with _GLOBAL_LOCK:
        if _GLOBAL_CAPTURE and _GLOBAL_CAPTURE.is_alive():
            same_token = _GLOBAL_INPUT_TOKEN == input_token
            same_config = _GLOBAL_CONFIG == config
            if same_token and same_config:
                _GLOBAL_USERS += 1
                return _GLOBAL_CAPTURE, _GLOBAL_QUEUE
            _GLOBAL_CAPTURE.stop()
            if _GLOBAL_QUEUE:
                _GLOBAL_QUEUE.clear(stale=True)
            _GLOBAL_CAPTURE = None
            _GLOBAL_QUEUE = None
            _GLOBAL_USERS = 0

        _GLOBAL_QUEUE = FrameQueue(maxlen=8)
        _GLOBAL_CAPTURE = FfmpegCapture(
            input_token=input_token,
            config=config,
            frame_queue=_GLOBAL_QUEUE,
            allow_input_tuning=allow_input_tuning,
            pipeline="monitoring",
        )
        _GLOBAL_CAPTURE.start()
        _GLOBAL_INPUT_TOKEN = input_token
        _GLOBAL_CONFIG = config
        _GLOBAL_USERS = 1
        return _GLOBAL_CAPTURE, _GLOBAL_QUEUE


def _release_global_capture(clear_queue: bool = False) -> None:
    global _GLOBAL_CAPTURE, _GLOBAL_QUEUE, _GLOBAL_USERS, _GLOBAL_INPUT_TOKEN, _GLOBAL_CONFIG
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
        _GLOBAL_INPUT_TOKEN = None
        _GLOBAL_CONFIG = None


def _ensure_preview_capture(input_token: str, config: CaptureConfig, *, allow_input_tuning: bool) -> tuple[bool, str | None]:
    global _PREVIEW_CAPTURE, _PREVIEW_QUEUE, _PREVIEW_INPUT_TOKEN, _PREVIEW_CONFIG, _PREVIEW_LAST_RESTART_AT
    with _PREVIEW_LOCK:
        if _PREVIEW_PAUSED_FOR_MONITORING:
            return False, "Preview paused while monitoring is active"

        if _PREVIEW_CAPTURE and _PREVIEW_CAPTURE.is_alive() and _PREVIEW_INPUT_TOKEN == input_token and _PREVIEW_CONFIG == config:
            return True, None

        now = time.time()
        if now - _PREVIEW_LAST_RESTART_AT < _PREVIEW_RESTART_DEBOUNCE_SEC:
            return False, "Preview restart debounced"

        if _PREVIEW_CAPTURE:
            _PREVIEW_CAPTURE.stop()
        if _PREVIEW_QUEUE:
            _PREVIEW_QUEUE.clear(stale=True)

        _PREVIEW_LAST_RESTART_AT = now
        _PREVIEW_QUEUE = FrameQueue(maxlen=4)
        _PREVIEW_CAPTURE = FfmpegCapture(
            input_token=input_token,
            config=config,
            frame_queue=_PREVIEW_QUEUE,
            allow_input_tuning=allow_input_tuning,
            pipeline="preview",
        )
        _PREVIEW_CAPTURE.start()
        _PREVIEW_INPUT_TOKEN = input_token
        _PREVIEW_CONFIG = config
        return True, None


def release_preview_capture() -> None:
    global _PREVIEW_CAPTURE, _PREVIEW_QUEUE, _PREVIEW_INPUT_TOKEN, _PREVIEW_CONFIG, _PREVIEW_LAST_RESTART_AT
    with _PREVIEW_LOCK:
        if _PREVIEW_CAPTURE:
            _PREVIEW_CAPTURE.stop()
        if _PREVIEW_QUEUE:
            _PREVIEW_QUEUE.clear(stale=True)
        _PREVIEW_CAPTURE = None
        _PREVIEW_QUEUE = None
        _PREVIEW_INPUT_TOKEN = None
        _PREVIEW_CONFIG = None
        _PREVIEW_LAST_RESTART_AT = time.time()


def pause_preview_for_monitoring() -> None:
    global _PREVIEW_PAUSED_FOR_MONITORING
    with _PREVIEW_LOCK:
        _PREVIEW_PAUSED_FOR_MONITORING = True
    logging.info("[CAM_PREVIEW] pause for monitoring")
    release_preview_capture()


def resume_preview_after_monitoring() -> None:
    global _PREVIEW_PAUSED_FOR_MONITORING
    with _PREVIEW_LOCK:
        _PREVIEW_PAUSED_FOR_MONITORING = False
    logging.info("[CAM_PREVIEW] resume allowed")


def start_preview_for_selected_camera(selected_display_name: str, width: int, height: int, fps: int) -> tuple[bool, str | None]:
    candidates = build_capture_input_candidates(selected_display_name)
    if not candidates:
        release_preview_capture()
        return False, "Preview failed: selected camera not found"

    candidate = candidates[0]
    config = _build_monitoring_config_ladder(width, height, fps, is_virtual=candidate.is_virtual)[0]
    try:
        started, skip_reason = _ensure_preview_capture(candidate.token, config, allow_input_tuning=candidate.is_virtual)
    except FfmpegNotFoundError as exc:
        return False, f"Preview failed: FFmpeg not found ({exc})"
    except Exception as exc:
        logging.warning("[CAM_PREVIEW] failed to start", exc_info=True)
        return False, f"Preview failed: {exc}"

    if not started:
        return False, skip_reason

    time.sleep(0.15)
    with _PREVIEW_LOCK:
        if _PREVIEW_CAPTURE and _PREVIEW_CAPTURE.is_alive():
            return True, None
        reason = _PREVIEW_CAPTURE.last_error if _PREVIEW_CAPTURE else "ffmpeg exited"
    return False, f"Preview failed: {reason or 'ffmpeg exited'}"


def get_latest_preview_frame():
    with _PREVIEW_LOCK:
        if not _PREVIEW_QUEUE:
            return None
        packet = _PREVIEW_QUEUE.peek_latest()
        if packet is None:
            return None
        return (packet.timestamp, packet.payload)


def get_latest_global_frame():
    with _GLOBAL_LOCK:
        if not _GLOBAL_QUEUE:
            return None
        packet = _GLOBAL_QUEUE.peek_latest()
        if packet is None:
            return None
        return (packet.timestamp, packet.payload)


def freeze_latest_global_frame():
    frame = get_latest_preview_frame() or get_latest_global_frame()
    if frame is not None:
        return frame
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

        failed = False
        pause_preview_for_monitoring()
        try:
            self._stop_event.clear()
            self._capture = None
            self._capture_acquired = False
            profile = app_state.active_profile
            if not profile:
                self.status.emit("No profile selected")
                self._state.mark_failed()
                failed = True
                return

            get_profile_dirs(profile)
            if not app_state.selected_reference:
                self.status.emit("No reference selected")
                self._state.mark_failed()
                failed = True
                return

            selected_display_name = get_profile_camera_device(profile)
            if not selected_display_name:
                self.status.emit("No camera selected")
                self._state.mark_failed()
                failed = True
                return

            input_candidates = build_capture_input_candidates(selected_display_name, force_refresh=True)
            if not input_candidates:
                set_profile_camera_device(profile, "")
                self.status.emit(f"Monitoring failed: camera not found ({selected_display_name})")
                self._state.mark_failed()
                failed = True
                return

            candidate = input_candidates[0]
            width, height = get_profile_frame_size(profile)
            if not width or not height:
                width, height = get_profile_frame_size_fallback()
            fps = get_profile_fps(profile)

            configs = _build_monitoring_config_ladder(width, height, fps, is_virtual=candidate.is_virtual)
            max_retries = 3
            queue = None
            failure_reason = "unknown capture failure"

            for attempt in range(1, max_retries + 1):
                if self._stop_event.is_set():
                    break
                config = configs[min(attempt - 1, len(configs) - 1)]
                if attempt > 1:
                    self.status.emit(f"Monitoring retrying ({attempt}/{max_retries})")
                    if self._stop_event.wait(0.3):
                        break
                logging.info("[CAM_CAPTURE] start attempt=%s/%s camera=%r config=%s", attempt, max_retries, candidate.token, config.label)

                cap, queue = _ensure_global_capture(
                    candidate.token,
                    config,
                    allow_input_tuning=candidate.is_virtual,
                )
                self._capture = cap
                self._capture_acquired = True

                grace_started = time.time()
                while not self._stop_event.is_set() and time.time() - grace_started < 2.5:
                    self._drain_ffmpeg_logs()
                    if cap.is_alive():
                        time.sleep(0.1)
                        continue
                    break

                if not cap.is_alive():
                    failure_reason = cap.last_error or "ffmpeg exited during startup"
                    logging.warning("[CAM_CAPTURE] retry camera=%r reason=%s", candidate.token, failure_reason)
                    _release_global_capture(clear_queue=True)
                    self._capture_acquired = False
                    self._capture = None
                    continue

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

                while not self._stop_event.is_set() and cap.is_alive():
                    self._drain_ffmpeg_logs()
                    time.sleep(0.15)

                if self._stop_event.is_set():
                    break

                failure_reason = cap.last_error or "ffmpeg exited unexpectedly"
                logging.warning("[CAM_CAPTURE] retry camera=%r reason=%s", candidate.token, failure_reason)
                _release_global_capture(clear_queue=True)
                self._capture_acquired = False
                self._capture = None

            if self._stop_event.is_set():
                return

            if self._processing_thread and self._processing_thread.is_alive():
                self._processing_thread.join(timeout=2)
            self._processing_thread = None

            if not self.running:
                self.status.emit(f"Monitoring failed: {failure_reason}")
                self._state.mark_failed()
                failed = True

        except FfmpegNotFoundError as exc:
            self.status.emit(f"Monitoring failed: FFmpeg not found ({exc})")
            self._state.mark_failed()
            failed = True
        except Exception as exc:
            logging.error("Monitoring crash", exc_info=True)
            self.status.emit(f"Monitoring failed: {exc}")
            try:
                self._state.mark_failed()
            except InvalidTransition:
                pass
            failed = True
        finally:
            self.stop(clear_queue=failed, emit_status=not failed)
            resume_preview_after_monitoring()

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

    def stop(self, clear_queue: bool = False, *, emit_status: bool = True):
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
        self._processing_thread = None

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
        if emit_status:
            self.status.emit("Stopped")
