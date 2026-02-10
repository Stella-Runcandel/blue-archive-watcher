"""Monitoring service orchestrating FFmpeg capture and processing threads."""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from app.app_state import app_state
from app.services.ffmpeg_capture_supervisor import LogLevel
from app.services.ffmpeg_tools import (
    CaptureConfig,
    CaptureInputCandidate,
    FfmpegNotFoundError,
    build_capture_input_candidates,
    list_camera_devices,
    verify_windows_dshow_device_token,
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


def _dedupe_capture_configs(configs: list[CaptureConfig]) -> list[CaptureConfig]:
    deduped: list[CaptureConfig] = []
    seen: set[tuple[int, int, int, int | None, int | None, int | None]] = set()
    for cfg in configs:
        key = (cfg.width, cfg.height, cfg.fps, cfg.input_width, cfg.input_height, cfg.input_fps)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cfg)
    return deduped


def _build_capture_config_ladder(width: int, height: int, fps: int, *, is_virtual: bool) -> list[CaptureConfig]:
    requested = CaptureConfig(width=width, height=height, fps=fps, input_width=width, input_height=height, input_fps=fps, label="requested")
    implicit_defaults = CaptureConfig(width=width, height=height, fps=fps, input_width=None, input_height=None, input_fps=None, label="implicit-default")
    fallbacks = [
        CaptureConfig(width=width, height=height, fps=fps, input_width=None, input_height=None, input_fps=None, label="fallback-no-size-no-fps"),
        CaptureConfig(width=width, height=height, fps=fps, input_width=1280, input_height=720, input_fps=30, label="fallback-1280x720@30"),
        CaptureConfig(width=width, height=height, fps=fps, input_width=1280, input_height=720, input_fps=25, label="fallback-1280x720@25"),
        CaptureConfig(width=width, height=height, fps=fps, input_width=640, input_height=480, input_fps=30, label="fallback-640x480@30"),
        CaptureConfig(width=width, height=height, fps=fps, input_width=None, input_height=None, input_fps=None, label="fallback-camera-default"),
    ]
    ordered = [requested, *fallbacks] if is_virtual else [implicit_defaults, requested, *fallbacks]
    return _dedupe_capture_configs(ordered)


def _probe_physical_camera(candidate: CaptureInputCandidate, config: CaptureConfig) -> bool:
    logging.info("[CAM_CAPTURE] preflight probe using implicit defaults for token=%r", candidate.token)
    _camera_debug_dump(
        "CAM_CAPTURE_PROBE",
        f"token={candidate.token}\nreason={candidate.reason}\nconfig_label={config.label}\ninput_size={config.input_width}x{config.input_height}\ninput_fps={config.input_fps}",
    )
    probe_capture = None
    try:
        probe_capture, _ = _ensure_global_capture(candidate.token, config)
        time.sleep(0.4)
        if probe_capture.is_alive():
            logging.info("[CAM_CAPTURE] preflight probe succeeded for token=%r", candidate.token)
            return True
        logging.warning("[CAM_CAPTURE] preflight probe failed for token=%r last_error=%s", candidate.token, probe_capture.last_error)
        return False
    finally:
        _release_global_capture(clear_queue=True)


def _camera_debug_enabled() -> bool:
    return os.environ.get("CAMERA_DEBUG", "").strip() in {"1", "true", "TRUE", "yes", "on"}


def _camera_debug_dump(section: str, payload: str) -> None:
    if not _camera_debug_enabled():
        return
    logs_dir = Path("Data") / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "camera_debug.log"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{section}]\n{payload}\n\n")


def _ensure_global_capture(input_token: str, config: CaptureConfig) -> tuple[FfmpegCapture, FrameQueue]:
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
        _GLOBAL_CAPTURE = FfmpegCapture(input_token=input_token, config=config, frame_queue=_GLOBAL_QUEUE)
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
            self._stop_event.clear()
            self._capture = None
            self._capture_acquired = False
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

            selected_display_name = get_profile_camera_device(profile)
            if not selected_display_name:
                self.status.emit("No camera selected")
                self._state.mark_failed()
                return

            enumerated_devices = list_camera_devices(force_refresh=True)
            enumerated_names = [d.display_name for d in enumerated_devices]
            logging.info(
                "[CAM_UI] profile=%r stored camera selection=%r available devices=%s",
                profile,
                selected_display_name,
                enumerated_names,
            )
            _camera_debug_dump("CAMERA_SELECTION", f"profile={profile}\nstored={selected_display_name}\navailable={enumerated_names}")
            input_candidates = build_capture_input_candidates(selected_display_name)
            if not input_candidates:
                logging.warning(
                    "[CAM_CAPTURE] selected camera %r missing from current enumeration; invalidating profile field",
                    selected_display_name,
                )
                set_profile_camera_device(profile, "")
                summary = f"Capture blocked: stored camera {selected_display_name!r} is not in current FFmpeg enumeration."
                _camera_debug_dump("FAIL_SUMMARY", summary)
                self.status.emit(f"Camera not found: {selected_display_name}. Re-select camera and retry.")
                self._state.mark_failed()
                return

            width, height = get_profile_frame_size(profile)
            if not width or not height:
                width, height = get_profile_frame_size_fallback()
            fps = get_profile_fps(profile)

            force_start = os.environ.get("CAMERA_FORCE_START", "").strip() in {"1", "true", "TRUE", "yes", "on"}
            verified_candidates = []
            for candidate in input_candidates:
                ok, details = verify_windows_dshow_device_token(candidate.token)
                _camera_debug_dump("CAM_VERIFY_RESULT", f"token={candidate.token}\nreason={candidate.reason}\nok={ok}\ndetails={details}")
                if ok:
                    verified_candidates.append(candidate)
            if not verified_candidates and not force_start:
                self.status.emit("Selected camera appears temporarily unavailable. Retry or set CAMERA_FORCE_START=1.")
                self._state.mark_failed()
                return

            attempts = verified_candidates or input_candidates
            queue = None
            self._capture = None
            selected_config = None
            for idx, candidate in enumerate(attempts, start=1):
                logging.info(
                    "[CAM_CAPTURE] input attempt %s using token=%r reason=%s is_virtual=%s",
                    idx,
                    candidate.token,
                    candidate.reason,
                    candidate.is_virtual,
                )
                _camera_debug_dump(
                    "CAM_CAPTURE_ATTEMPT",
                    f"attempt={idx}\ntoken={candidate.token}\nreason={candidate.reason}\nis_virtual={candidate.is_virtual}",
                )

                if not candidate.is_virtual:
                    probe_ok = _probe_physical_camera(
                        candidate,
                        CaptureConfig(
                            width=width,
                            height=height,
                            fps=fps,
                            input_width=None,
                            input_height=None,
                            input_fps=None,
                            label="preflight-no-size-no-fps",
                        ),
                    )
                    if not probe_ok:
                        _camera_debug_dump("CAM_CAPTURE_PROBE_FAIL", f"attempt={idx}\ntoken={candidate.token}")

                config_ladder = _build_capture_config_ladder(width, height, fps, is_virtual=candidate.is_virtual)
                for cfg_idx, candidate_config in enumerate(config_ladder, start=1):
                    logging.info(
                        "[CAM_CAPTURE] input attempt %s config attempt %s label=%s input_size=%sx%s input_fps=%s",
                        idx,
                        cfg_idx,
                        candidate_config.label,
                        candidate_config.input_width,
                        candidate_config.input_height,
                        candidate_config.input_fps,
                    )
                    _camera_debug_dump(
                        "CAM_CAPTURE_CONFIG_ATTEMPT",
                        "\n".join(
                            [
                                f"input_attempt={idx}",
                                f"config_attempt={cfg_idx}",
                                f"token={candidate.token}",
                                f"config_label={candidate_config.label}",
                                f"input_size={candidate_config.input_width}x{candidate_config.input_height}",
                                f"input_fps={candidate_config.input_fps}",
                            ]
                        ),
                    )

                    cap, queue = _ensure_global_capture(candidate.token, candidate_config)
                    self._capture = cap
                    self._capture_acquired = True
                    time.sleep(0.6)
                    if cap.is_alive():
                        selected_config = candidate_config
                        if candidate_config.label != "requested":
                            self.status.emit(
                                f"Camera fallback active: {candidate_config.label.replace('fallback-', '').replace('-', ' ')}"
                            )
                        logging.info(
                            "[CAM_CAPTURE] capture succeeded with token=%r config_label=%s",
                            candidate.token,
                            candidate_config.label,
                        )
                        _camera_debug_dump(
                            "CAM_CAPTURE_SUCCESS",
                            f"token={candidate.token}\nconfig_label={candidate_config.label}\ninput_size={candidate_config.input_width}x{candidate_config.input_height}\ninput_fps={candidate_config.input_fps}",
                        )
                        break

                    logging.warning(
                        "[CAM_CAPTURE] config attempt failed token=%r config_label=%s last_error=%s",
                        candidate.token,
                        candidate_config.label,
                        cap.last_error,
                    )
                    _camera_debug_dump(
                        "CAM_CAPTURE_ATTEMPT_FAIL",
                        f"input_attempt={idx}\nconfig_attempt={cfg_idx}\ntoken={candidate.token}\nconfig_label={candidate_config.label}\nlast_error={cap.last_error}",
                    )
                    _release_global_capture(clear_queue=True)
                    self._capture_acquired = False
                    self._capture = None

                if self._capture and self._capture.is_alive():
                    break
            if not self._capture or not self._capture.is_alive() or queue is None:
                self.status.emit("FFmpeg capture failed. Retry monitoring or reselect camera.")
                self._state.mark_failed()
                return
            if selected_config and selected_config.label != "requested":
                logging.info("[CAM_CAPTURE] final successful config=%s", selected_config.label)

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
                    _camera_debug_dump("FAIL_SUMMARY", "Capture failed: FFmpeg process exited unexpectedly. Check CAM_CAPTURE stderr lines above.")
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
                _camera_debug_dump("FFMPEG_STDERR", event.message)

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
