"""FFmpeg capture pipeline helpers with a bounded in-memory queue."""
import logging
import subprocess
import threading
import time
from collections import deque

from app.services.ffmpeg_tools import (
    CaptureConfig,
    FfmpegNotFoundError,
    build_ffmpeg_capture_command,
)


class FrameQueue:
    """Thread-safe bounded queue for raw frames."""
    def __init__(self, maxlen: int):
        self._queue = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self.dropped = 0
        self.maxlen = maxlen

    def put(self, item):
        """Insert a frame, dropping oldest when full (non-blocking)."""
        with self._not_empty:
            if len(self._queue) == self._queue.maxlen:
                self._queue.popleft()
                self.dropped += 1
            self._queue.append(item)
            self._not_empty.notify()

    def get(self, timeout=None):
        """Retrieve a frame, waiting up to timeout seconds."""
        with self._not_empty:
            if not self._queue:
                self._not_empty.wait(timeout=timeout)
            if not self._queue:
                return None
            return self._queue.popleft()

    def clear(self):
        """Clear queued frames without blocking producers."""
        with self._not_empty:
            self._queue.clear()

    def size(self) -> int:
        """Return current queue length (thread-safe)."""
        with self._lock:
            return len(self._queue)


class FfmpegCapture:
    """Spawn FFmpeg and stream raw frames into a FrameQueue."""
    def __init__(self, device_name: str, config: CaptureConfig, frame_queue: FrameQueue):
        self.device_name = device_name
        self.config = config
        self.frame_queue = frame_queue
        self.process = None
        self.thread = None
        self.stderr_thread = None
        self.stop_event = threading.Event()
        self.error = None
        self.frames_captured = 0

    def start(self):
        """Launch FFmpeg subprocess and reader threads."""
        command = build_ffmpeg_capture_command(self.device_name, self.config)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                creationflags=creationflags,
            )
        except FileNotFoundError as exc:
            self.error = f"FFmpeg executable not found ({exc})"
            raise FfmpegNotFoundError(self.error) from exc

        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self.thread.start()
        self.stderr_thread.start()

    def _stderr_loop(self):
        """Log FFmpeg stderr for diagnostics."""
        if not self.process or not self.process.stderr:
            return
        for line in iter(self.process.stderr.readline, b""):
            if self.stop_event.is_set():
                break
            if not line:
                break
            logging.error("FFmpeg: %s", line.decode(errors="ignore").strip())

    def _reader_loop(self):
        """Read fixed-size frames from FFmpeg stdout."""
        if not self.process or not self.process.stdout:
            return
        frame_size = self.config.width * self.config.height * 3
        while not self.stop_event.is_set():
            data = self._read_exact(self.process.stdout, frame_size)
            if not data:
                break
            timestamp = time.time()
            self.frame_queue.put((timestamp, data))
            self.frames_captured += 1

        if self.process and self.process.poll() is None:
            self.process.terminate()

    def _read_exact(self, stream, size):
        """Read exactly size bytes unless stream ends."""
        data = bytearray()
        while len(data) < size and not self.stop_event.is_set():
            chunk = stream.read(size - len(data))
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    def stop(self):
        """Terminate FFmpeg and join reader threads."""
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.thread:
            self.thread.join(timeout=2)
        if self.stderr_thread:
            self.stderr_thread.join(timeout=2)
