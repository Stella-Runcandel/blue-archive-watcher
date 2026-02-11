"""Tests for global FFmpeg capture lifecycle behavior."""
import unittest
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

from app.services.ffmpeg_tools import CaptureConfig


def _module_importable(module: str) -> bool:
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

    def __init__(self, input_token, config, frame_queue, allow_input_tuning=True, pipeline="monitoring"):
        self.device_name = input_token
        self.config = config
        self.queue = frame_queue
        self.allow_input_tuning = allow_input_tuning
        self.pipeline = pipeline
        self.process = DummyProcess()
        self.stop_calls = 0
        self.last_error = None
        DummyCapture.created += 1

    def start(self):
        return None

    def stop(self):
        self.stop_calls += 1

    def is_alive(self):
        return True


class FailingCapture(DummyCapture):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._alive = False
        self.last_error = "device busy"

    def is_alive(self):
        return self._alive


def _reset_globals(monitor_service):
    monitor_service._GLOBAL_CAPTURE = None
    monitor_service._GLOBAL_QUEUE = None
    monitor_service._GLOBAL_INPUT_TOKEN = None
    monitor_service._GLOBAL_CONFIG = None
    monitor_service._GLOBAL_USERS = 0
    monitor_service._PREVIEW_CAPTURE = None
    monitor_service._PREVIEW_QUEUE = None
    monitor_service._PREVIEW_INPUT_TOKEN = None
    monitor_service._PREVIEW_CONFIG = None
    monitor_service._PREVIEW_PAUSED_FOR_MONITORING = False
    monitor_service._PREVIEW_LAST_RESTART_AT = 0.0
    monitor_service._PREVIEW_STATIC_FRAME = None
    monitor_service._PREVIEW_LIVE_ENABLED = False
    monitor_service._ACTIVE_OWNER_PIPELINE = None
    monitor_service._ACTIVE_CAMERA_TOKEN = None
    monitor_service._LAST_CAMERA_RELEASE_AT = 0.0


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
            cap1, _ = self.monitor_service._ensure_global_capture("camera-1", config, allow_input_tuning=False)
            cap2, _ = self.monitor_service._ensure_global_capture("camera-1", config, allow_input_tuning=False)
            self.assertIs(cap1, cap2)
            self.assertEqual(self.monitor_service._GLOBAL_USERS, 2)

            self.monitor_service._release_global_capture()
            self.assertEqual(self.monitor_service._GLOBAL_USERS, 1)
            self.assertEqual(cap1.stop_calls, 0)

            self.monitor_service._release_global_capture()
            self.assertEqual(self.monitor_service._GLOBAL_USERS, 0)
            self.assertEqual(cap1.stop_calls, 1)

    def test_start_stop_start_creates_new_capture(self):
        """Ensure new capture starts after all users release."""
        config = CaptureConfig(width=1280, height=720, fps=30)
        with mock.patch.object(self.monitor_service, "FfmpegCapture", DummyCapture):
            cap1, _ = self.monitor_service._ensure_global_capture("camera-1", config, allow_input_tuning=False)
            self.monitor_service._release_global_capture()
            cap2, _ = self.monitor_service._ensure_global_capture("camera-1", config, allow_input_tuning=False)
            self.assertIsNot(cap1, cap2)
            self.assertEqual(DummyCapture.created, 2)

    def test_monitor_stop_is_idempotent(self):
        """Ensure stop can be called twice without double-release."""
        service = self.monitor_service.MonitorService()
        service._capture = DummyCapture("camera-1", CaptureConfig(1, 1, 1), None)
        service._capture_acquired = True
        service._state.request_start()
        service._state.mark_running()

        with mock.patch.object(self.monitor_service, "_release_global_capture") as release_mock:
            service.stop()
            service.stop()
            release_mock.assert_called_once()

    def test_get_latest_global_frame_does_not_drain_queue(self):
        """Global preview accessor should read latest frame without removing queued frames."""
        queue = self.monitor_service.FrameQueue(maxlen=4)
        queue.put(self.monitor_service.FramePacket(1.0, b"a"))
        queue.put(self.monitor_service.FramePacket(2.0, b"b"))
        self.monitor_service._GLOBAL_QUEUE = queue
        latest = self.monitor_service.get_latest_global_frame()
        self.assertEqual(latest, (2.0, b"b"))
        self.assertEqual(queue.size(), 2)

    def test_preview_same_config_does_not_restart(self):
        config = CaptureConfig(width=1280, height=720, fps=30)
        with mock.patch.object(self.monitor_service, "FfmpegCapture", DummyCapture):
            ok1, _ = self.monitor_service._ensure_preview_capture("camera-1", config, allow_input_tuning=False)
            ok2, _ = self.monitor_service._ensure_preview_capture("camera-1", config, allow_input_tuning=False)
            self.assertTrue(ok1)
            self.assertTrue(ok2)
            self.assertEqual(DummyCapture.created, 1)

    def test_preview_restart_is_debounced(self):
        config1 = CaptureConfig(width=1280, height=720, fps=30)
        config2 = CaptureConfig(width=640, height=480, fps=30)
        with mock.patch.object(self.monitor_service, "FfmpegCapture", DummyCapture):
            ok1, _ = self.monitor_service._ensure_preview_capture("camera-1", config1, allow_input_tuning=False)
            ok2, reason = self.monitor_service._ensure_preview_capture("camera-1", config2, allow_input_tuning=False)
            self.assertTrue(ok1)
            self.assertFalse(ok2)
            self.assertEqual(reason, "Preview restart debounced")

    def test_preview_pause_blocks_restart(self):
        config = CaptureConfig(width=1280, height=720, fps=30)
        with mock.patch.object(self.monitor_service, "FfmpegCapture", DummyCapture):
            self.monitor_service.pause_preview_for_monitoring()
            ok, reason = self.monitor_service._ensure_preview_capture("camera-1", config, allow_input_tuning=False)
            self.assertFalse(ok)
            self.assertEqual(reason, "Preview paused while monitoring is active")


    def test_preview_blocked_when_monitoring_owns_camera(self):
        config = CaptureConfig(width=1280, height=720, fps=30)
        self.monitor_service._ACTIVE_OWNER_PIPELINE = "monitoring"
        self.monitor_service._ACTIVE_CAMERA_TOKEN = "camera-1"
        with mock.patch.object(self.monitor_service, "FfmpegCapture", DummyCapture):
            ok, reason = self.monitor_service._ensure_preview_capture("camera-1", config, allow_input_tuning=False)
        self.assertFalse(ok)
        self.assertIn("owned by monitoring", reason)

    def test_virtual_preview_uses_single_retry(self):
        calls = {"count": 0}

        def side_effect(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return False, "Preview failed: device busy"
            return True, None

        with mock.patch.object(self.monitor_service, "build_capture_input_candidates", return_value=[SimpleNamespace(token="video=cam-a", is_virtual=True)]):
            with mock.patch.object(self.monitor_service, "_ensure_preview_capture", side_effect=side_effect):
                with mock.patch.object(self.monitor_service.time, "sleep", return_value=None):
                    ok, reason = self.monitor_service.start_preview_for_selected_camera("cam-a", 640, 480, 30)
        self.assertTrue(ok)
        self.assertIsNone(reason)
        self.assertEqual(calls["count"], 2)


    def test_snapshot_preview_releases_camera_owner(self):
        with mock.patch.object(self.monitor_service, "build_capture_input_candidates", return_value=[SimpleNamespace(token="video=cam-a", is_virtual=False)]):
            with mock.patch.object(self.monitor_service, "capture_single_frame_by_token", return_value=b"x" * (640 * 480 * 3)):
                ok, reason = self.monitor_service.capture_preview_snapshot("cam-a", 640, 480)
        self.assertTrue(ok)
        self.assertIsNone(reason)
        self.assertIsNone(self.monitor_service._ACTIVE_OWNER_PIPELINE)

    def _fail_capture_once(self, input_token, config, *, allow_input_tuning):
        queue = self.monitor_service.FrameQueue(maxlen=2)
        cap = FailingCapture(input_token, config, queue, allow_input_tuning=allow_input_tuning)
        return cap, queue


    def test_monitoring_caps_resolution_to_1280x720(self):
        service = self.monitor_service.MonitorService()
        seen = {}

        def fail_once(input_token, config, *, allow_input_tuning):
            seen["config"] = config
            return self._fail_capture_once(input_token, config, allow_input_tuning=allow_input_tuning)

        with (
            mock.patch.object(self.monitor_service, "pause_preview_for_monitoring"),
            mock.patch.object(self.monitor_service, "resume_preview_after_monitoring"),
            mock.patch.object(self.monitor_service, "get_profile_dirs"),
            mock.patch.object(self.monitor_service, "get_profile_camera_device", return_value="cam-a"),
            mock.patch.object(self.monitor_service, "get_profile_frame_size", return_value=(1920, 1080)),
            mock.patch.object(self.monitor_service, "get_profile_fps", return_value=30),
            mock.patch.object(self.monitor_service, "build_capture_input_candidates", return_value=[SimpleNamespace(token="video=cam-a", is_virtual=False)]),
            mock.patch.object(self.monitor_service, "_ensure_global_capture", side_effect=fail_once),
            mock.patch.object(self.monitor_service, "_release_global_capture"),
            mock.patch.object(self.monitor_service.time, "sleep", return_value=None),
            mock.patch.object(self.monitor_service.time, "time", side_effect=[0.0, 3.0, 4.0, 7.0, 8.0, 11.0, 12.0]),
        ):
            from app.app_state import app_state

            app_state.active_profile = "alpha"
            app_state.selected_reference = "ref"
            service.run()

        self.assertEqual(seen["config"].width, 1280)
        self.assertEqual(seen["config"].height, 720)
        self.assertEqual(seen["config"].input_width, 1280)
        self.assertEqual(seen["config"].input_height, 720)

    def test_processing_loop_uses_resolved_monitor_fps(self):
        service = self.monitor_service.MonitorService()
        service._monitor_fps = 20

        class BurstQueue:
            dropped_frames = 0
            maxlen = 2

            def __init__(self):
                self._calls = 0

            def get(self, timeout=0.5):
                self._calls += 1
                if self._calls <= 2:
                    return self.monitor_service.FramePacket(1.0, b"\x00" * (2 * 2 * 3))
                service._stop_event.set()
                return None

            def size(self):
                return 0

        queue = BurstQueue()
        queue.monitor_service = self.monitor_service

        with (
            mock.patch.object(self.monitor_service.app_state, "selected_reference", "ref"),
            mock.patch.object(service._metrics, "on_frame"),
            mock.patch.object(service._detection_consumer, "is_paused", return_value=False),
            mock.patch.object(self.monitor_service.time, "time", side_effect=[0.0, 0.02, 0.02]),
            mock.patch.object(self.monitor_service.dect, "evaluate_frame", return_value=SimpleNamespace(confidence=0.5, matched=False, timestamp=0.0)) as eval_mock,
        ):
            service._processing_loop("alpha", queue, 2, 2)

        self.assertEqual(eval_mock.call_count, 1)

    def test_monitoring_retries_limited_and_reports_failure(self):
        service = self.monitor_service.MonitorService()
        messages = []
        states = []
        service.status.connect(messages.append)
        service.state_changed.connect(states.append)

        with (
            mock.patch.object(self.monitor_service, "pause_preview_for_monitoring"),
            mock.patch.object(self.monitor_service, "resume_preview_after_monitoring"),
            mock.patch.object(self.monitor_service, "get_profile_dirs"),
            mock.patch.object(self.monitor_service, "get_profile_camera_device", return_value="cam-a"),
            mock.patch.object(self.monitor_service, "get_profile_frame_size", return_value=(640, 480)),
            mock.patch.object(self.monitor_service, "get_profile_fps", return_value=30),
            mock.patch.object(self.monitor_service, "build_capture_input_candidates", return_value=[SimpleNamespace(token="video=cam-a", is_virtual=True)]),
            mock.patch.object(self.monitor_service, "_ensure_global_capture", side_effect=self._fail_capture_once),
            mock.patch.object(self.monitor_service, "_release_global_capture") as release_mock,
            mock.patch.object(self.monitor_service.time, "sleep", return_value=None),
            mock.patch.object(self.monitor_service.time, "time", side_effect=[0.0, 3.0, 4.0, 7.0, 8.0, 11.0, 12.0]),
        ):
            from app.app_state import app_state

            app_state.active_profile = "alpha"
            app_state.selected_reference = "ref"
            service.run()

        retry_msgs = [m for m in messages if "Monitoring retrying" in m]
        self.assertEqual(len(retry_msgs), 1)
        self.assertTrue(any(m.startswith("Monitoring failed:") for m in messages))
        self.assertIn("FAILED", states)
        self.assertGreaterEqual(release_mock.call_count, 3)


if __name__ == "__main__":
    unittest.main()
