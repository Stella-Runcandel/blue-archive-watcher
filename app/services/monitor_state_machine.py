"""Explicit monitoring state machine with strict transition controls."""
from __future__ import annotations

import threading
from enum import Enum


class MonitoringState(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    STOPPING = "STOPPING"


class InvalidTransition(RuntimeError):
    pass


class MonitoringStateMachine:
    def __init__(self):
        self._state = MonitoringState.IDLE
        self._lock = threading.Lock()

    @property
    def state(self) -> MonitoringState:
        with self._lock:
            return self._state

    def _transition(self, expected: set[MonitoringState], new_state: MonitoringState) -> MonitoringState:
        with self._lock:
            if self._state not in expected:
                raise InvalidTransition(f"Cannot transition {self._state} -> {new_state}")
            self._state = new_state
            return self._state

    def request_start(self) -> MonitoringState:
        return self._transition({MonitoringState.IDLE}, MonitoringState.STARTING)

    def mark_running(self) -> MonitoringState:
        return self._transition({MonitoringState.STARTING}, MonitoringState.RUNNING)

    def request_stop(self) -> MonitoringState:
        return self._transition(
            {MonitoringState.RUNNING, MonitoringState.FAILED}, MonitoringState.STOPPING
        )

    def mark_failed(self) -> MonitoringState:
        return self._transition({MonitoringState.STARTING, MonitoringState.RUNNING}, MonitoringState.FAILED)

    def mark_idle(self) -> MonitoringState:
        return self._transition({MonitoringState.STOPPING}, MonitoringState.IDLE)
