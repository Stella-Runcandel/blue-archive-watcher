"""Tests for global FFmpeg capture lifecycle behavior."""
import subprocess
import sys
import unittest
from unittest import mock

from app.services.ffmpeg_tools import CaptureConfig


def _module_importable(module: str) -> bool:
    """Return True when module can be imported in a subprocess."""
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


CV2_AVAILABLE = _module_importable("cv2")


class DummyProcess:
    def poll(self):
        return None


class DummyCapture:
    created = 0

    def __init__(self, device_name, config, queue):
        self.device_name = device_name
        self.config = config
        self.queue = queue
        self.process = DummyProcess()
        self.stop_calls = 0
        DummyCapture.created += 1

    def start(self):
        return None

    def stop(self):
        self.stop_calls += 1


def _reset_globals(monitor_service):
    monitor_service._GLOBAL_CAPTURE = None
    monitor_service._GLOBAL_QUEUE = None
    monitor_service._GLOBAL_DEVICE = None
    monitor_service._GLOBAL_CONFIG = None
    monitor_service._GLOBAL_CAPTURE_USERS = 0


@unittest.skipUnless(CV2_AVAILABLE, "OpenCV unavailable in test environment")
class MonitorCaptureTests(unittest.TestCase):
    """Validate reference counting and idempotent stop behavior."""

    def setUp(self):
        import app.services.monitor_service as monitor_service

        self.monitor_service = monitor_service
        _reset_globals(monitor_service)
        DummyCapture.created = 0

    def tearDown(self):
        _reset_globals(self.monitor_service)

    def test_global_capture_reference_counting(self):
        """Ensure global capture is stopped only after last release."""
        config = CaptureConfig(width=1280, height=720, fps=30)
        with mock.patch.object(self.monitor_service, "FfmpegCapture", DummyCapture):
            cap1, _ = self.monitor_service._ensure_global_capture("camera-1", config)
            cap2, _ = self.monitor_service._ensure_global_capture("camera-1", config)
            self.assertIs(cap1, cap2)
            self.assertEqual(self.monitor_service._GLOBAL_CAPTURE_USERS, 2)

            self.monitor_service._release_global_capture()
            self.assertEqual(self.monitor_service._GLOBAL_CAPTURE_USERS, 1)
            self.assertEqual(cap1.stop_calls, 0)

            self.monitor_service._release_global_capture()
            self.assertEqual(self.monitor_service._GLOBAL_CAPTURE_USERS, 0)
            self.assertEqual(cap1.stop_calls, 1)

    def test_start_stop_start_creates_new_capture(self):
        """Ensure new capture starts after all users release."""
        config = CaptureConfig(width=1280, height=720, fps=30)
        with mock.patch.object(self.monitor_service, "FfmpegCapture", DummyCapture):
            cap1, _ = self.monitor_service._ensure_global_capture("camera-1", config)
            self.monitor_service._release_global_capture()
            cap2, _ = self.monitor_service._ensure_global_capture("camera-1", config)
            self.assertIsNot(cap1, cap2)
            self.assertEqual(DummyCapture.created, 2)

    def test_monitor_stop_is_idempotent(self):
        """Ensure stop can be called twice without double-release."""
        service = self.monitor_service.MonitorService()
        service._capture = DummyCapture("camera-1", CaptureConfig(1, 1, 1), None)
        service._capture_acquired = True

        with mock.patch.object(self.monitor_service, "_release_global_capture") as release_mock:
            service.stop()
            service.stop()
            release_mock.assert_called_once()
