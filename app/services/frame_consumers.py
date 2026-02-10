"""Frame consumer interfaces for preview, detection, snapshot, and metrics."""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod

from app.services.frame_bus import FramePacket, FrameQueue


class FrameConsumer(ABC):
    @abstractmethod
    def consume(self, packet: FramePacket) -> None:
        raise NotImplementedError


class SnapshotConsumer:
    """Fetch immutable copy of latest frame without pausing capture/detection."""

    def __init__(self, frame_queue: FrameQueue):
        self._queue = frame_queue

    def capture_snapshot(self) -> FramePacket | None:
        packet = self._queue.peek_latest()
        if not packet:
            return None
        return FramePacket(timestamp=packet.timestamp, payload=bytes(packet.payload), stale=packet.stale)


class DetectionConsumer:
    def __init__(self):
        self._paused = threading.Event()
        self._paused.clear()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def is_paused(self) -> bool:
        return self._paused.is_set()


class MetricsConsumer:
    def __init__(self):
        self.capture_fps = 0.0
        self.last_ts = time.time()
        self.frames = 0

    def on_frame(self):
        self.frames += 1
        now = time.time()
        delta = now - self.last_ts
        if delta >= 1.0:
            self.capture_fps = self.frames / delta
            self.frames = 0
            self.last_ts = now
