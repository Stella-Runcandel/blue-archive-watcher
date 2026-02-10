"""Supervise FFmpeg capture process and publish raw frames to FrameQueue."""
from __future__ import annotations

import logging
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum

from app.services.ffmpeg_tools import CaptureConfig, FfmpegNotFoundError, build_ffmpeg_capture_command
from app.services.frame_bus import FramePacket, FrameQueue


class LogLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class FfmpegLogEvent:
    level: LogLevel
    message: str


class FfmpegCaptureSupervisor:
    def __init__(self, device_name: str, config: CaptureConfig, frame_queue: FrameQueue):
        self.device_name = device_name
        self.config = config
        self.frame_queue = frame_queue
        self.process: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self.frames_captured = 0
        self.log_events: "queue.Queue[FfmpegLogEvent]" = queue.Queue(maxsize=512)
        self.last_error: str | None = None

    def start(self) -> None:
        cmd = build_ffmpeg_capture_command(self.device_name, self.config)
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError as exc:
            raise FfmpegNotFoundError(str(exc)) from exc

        self._stop.clear()
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread.start()

    def _reader_loop(self) -> None:
        if not self.process or not self.process.stdout:
            return
        frame_size = self.config.width * self.config.height * 3
        try:
            while not self._stop.is_set():
                frame = self._read_exact(self.process.stdout, frame_size)
                if frame is None:
                    break
                self.frame_queue.put(FramePacket(timestamp=time.time(), payload=frame))
                self.frames_captured += 1
        except Exception as exc:
            self.last_error = f"FFmpeg frame reader failed: {exc}"
            self._emit_log(LogLevel.ERROR, self.last_error)
        finally:
            if self.process and self.process.poll() is None and not self._stop.is_set():
                self.process.terminate()

    def _stderr_loop(self) -> None:
        if not self.process or not self.process.stderr:
            return
        for raw in iter(self.process.stderr.readline, b""):
            if self._stop.is_set():
                break
            text = raw.decode(errors="ignore").strip()
            if not text:
                continue
            level = self._classify_log(text)
            self._emit_log(level, text)
            if level == LogLevel.ERROR:
                self.last_error = text

    def _emit_log(self, level: LogLevel, message: str) -> None:
        event = FfmpegLogEvent(level=level, message=message)
        try:
            self.log_events.put_nowait(event)
        except queue.Full:
            pass
        getattr(logging, level.value.lower())("FFmpeg %s", message)

    @staticmethod
    def _classify_log(text: str) -> LogLevel:
        lowered = text.lower()
        if any(token in lowered for token in ("error", "failed", "invalid", "unable", "i/o")):
            return LogLevel.ERROR
        if any(token in lowered for token in ("warning", "deprecated", "buffer")):
            return LogLevel.WARNING
        return LogLevel.INFO

    @staticmethod
    def _read_exact(stream, size: int) -> bytes | None:
        data = bytearray()
        while len(data) < size:
            chunk = stream.read(size - len(data))
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self._reader_thread:
            self._reader_thread.join(timeout=timeout)
        if self._stderr_thread:
            self._stderr_thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return bool(self.process and self.process.poll() is None)
