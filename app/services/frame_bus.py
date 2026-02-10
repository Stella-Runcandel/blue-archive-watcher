"""Thread-safe frame bus with bounded policies and stale-marking semantics."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque


class OverflowPolicy(str, Enum):
    DROP_OLDEST = "drop_oldest"
    LAST_ONLY = "last_only"


@dataclass(frozen=True)
class FramePacket:
    timestamp: float
    payload: bytes
    stale: bool = False


class FrameQueue:
    def __init__(self, maxlen: int = 8, policy: OverflowPolicy = OverflowPolicy.DROP_OLDEST):
        self.maxlen = max(1, int(maxlen))
        self.policy = policy
        self._queue: Deque[FramePacket] = deque(maxlen=self.maxlen)
        self._cv = threading.Condition()
        self.dropped_frames = 0
        self.dropped = 0  # backward-compatible alias
        self.stale = False

    def put(self, packet: FramePacket) -> None:
        with self._cv:
            if self.policy == OverflowPolicy.LAST_ONLY:
                dropped_now = len(self._queue)
                self._queue.clear()
                self.dropped_frames += dropped_now
                self.dropped += dropped_now
            elif len(self._queue) >= self.maxlen:
                self._queue.popleft()
                self.dropped_frames += 1
                self.dropped += 1
            self._queue.append(packet)
            self._cv.notify_all()

    def get(self, timeout: float | None = None) -> FramePacket | None:
        with self._cv:
            if not self._queue:
                self._cv.wait(timeout=timeout)
            if not self._queue:
                return None
            return self._queue.popleft()

    def peek_latest(self) -> FramePacket | None:
        with self._cv:
            return self._queue[-1] if self._queue else None

    def clear(self, stale: bool = True) -> None:
        with self._cv:
            self._queue.clear()
            self.stale = stale

    def size(self) -> int:
        with self._cv:
            return len(self._queue)
