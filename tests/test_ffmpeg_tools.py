"""FFmpeg helper tests for device enumeration parsing."""
import unittest
from unittest.mock import patch

from app.services import ffmpeg_tools
from app.services.camera_enumerator import CameraDevice


class FfmpegToolsTests(unittest.TestCase):
    """Validate FFmpeg enumeration wiring and cache behavior."""

    def setUp(self):
        ffmpeg_tools._ENUM_CACHE = None

    @patch(
        "app.services.ffmpeg_tools.enumerate_video_devices",
        return_value=[
            CameraDevice(display_name="HD Webcam", ffmpeg_token="video=HD Webcam", backend="dshow", is_virtual=False),
            CameraDevice(display_name="Virtual Cam", ffmpeg_token="video=Virtual Cam", backend="dshow", is_virtual=True),
        ],
    )
    def test_list_video_devices_uses_enumerator(self, enum_mock):
        devices = ffmpeg_tools.list_video_devices()
        self.assertEqual(devices, ["HD Webcam", "Virtual Cam"])
        enum_mock.assert_called_once()

    @patch("app.services.ffmpeg_tools.enumerate_video_devices", return_value=[])
    @patch("app.services.ffmpeg_tools.resolve_ffmpeg_path", return_value="/tmp/custom-ffmpeg")
    @patch("app.services.ffmpeg_tools.platform.system", return_value="Linux")
    def test_list_video_devices_non_windows_retries_with_path_ffmpeg(self, _platform_mock, _resolve_mock, enum_mock):
        devices = ffmpeg_tools.list_video_devices(force_refresh=True)
        self.assertEqual(devices, [])
        self.assertEqual(enum_mock.call_count, 2)

    @patch(
        "app.services.ffmpeg_tools.enumerate_video_devices",
        return_value=[CameraDevice(display_name="New Cam", ffmpeg_token="video=New Cam", backend="dshow", is_virtual=False)],
    )
    def test_list_video_devices_uses_cache(self, enum_mock):
        ffmpeg_tools._ENUM_CACHE = [CameraDevice(display_name="Cached Cam", ffmpeg_token="video=Cached Cam", backend="dshow", is_virtual=False)]
        self.assertEqual(ffmpeg_tools.list_video_devices(), ["Cached Cam"])
        enum_mock.assert_not_called()

    @patch(
        "app.services.ffmpeg_tools.enumerate_video_devices",
        return_value=[CameraDevice(display_name="Fresh Cam", ffmpeg_token="video=Fresh Cam", backend="dshow", is_virtual=False)],
    )
    def test_list_video_devices_force_refresh_invalidates_cache(self, enum_mock):
        ffmpeg_tools._ENUM_CACHE = [CameraDevice(display_name="Stale Cam", ffmpeg_token="video=Stale Cam", backend="dshow", is_virtual=False)]
        self.assertEqual(ffmpeg_tools.list_video_devices(force_refresh=True), ["Fresh Cam"])
        enum_mock.assert_called_once()

    @patch(
        "app.services.ffmpeg_tools.list_camera_devices",
        return_value=[CameraDevice(display_name="OBS Virtual Camera", ffmpeg_token="video=OBS Virtual Camera", backend="dshow", is_virtual=True)],
    )
    def test_resolve_camera_device_token_exact_match(self, _mock_list):
        self.assertEqual(
            ffmpeg_tools.resolve_camera_device_token("OBS Virtual Camera"),
            "video=OBS Virtual Camera",
        )

    @patch(
        "app.services.ffmpeg_tools.list_camera_devices",
        return_value=[CameraDevice(display_name="OBS Virtual Camera", ffmpeg_token="video=OBS Virtual Camera", backend="dshow", is_virtual=True)],
    )
    def test_resolve_camera_device_token_missing_returns_none(self, _mock_list):
        self.assertIsNone(ffmpeg_tools.resolve_camera_device_token("Camera 1"))

    @patch(
        "app.services.ffmpeg_tools.list_camera_devices",
        return_value=[CameraDevice(display_name="OBS Virtual Camera", ffmpeg_token="video=OBS Virtual Camera", backend="dshow", is_virtual=True)],
    )
    @patch("app.services.ffmpeg_tools.platform.system", return_value="Windows")
    def test_build_capture_input_candidates_windows_variants(self, _platform_mock, _mock_list):
        candidates = ffmpeg_tools.build_capture_input_candidates("OBS Virtual Camera")
        tokens = [c.token for c in candidates]
        self.assertEqual(tokens[0], "video=OBS Virtual Camera")
        self.assertIn('video="OBS Virtual Camera"', tokens)
        self.assertIn("OBS Virtual Camera", tokens)



    def test_build_ffmpeg_capture_command_allows_implicit_input_defaults(self):
        config = ffmpeg_tools.CaptureConfig(
            width=1280,
            height=720,
            fps=30,
            input_width=None,
            input_height=None,
            input_fps=None,
        )
        with patch("app.services.ffmpeg_tools.resolve_ffmpeg_path", return_value="ffmpeg"):
            cmd = ffmpeg_tools.build_ffmpeg_capture_command("video=HD Webcam", config)
        self.assertNotIn("-video_size", cmd)
        self.assertNotIn("-framerate", cmd)
        self.assertIn("-s", cmd)
        self.assertIn("1280x720", cmd)

    @patch(
        "app.services.ffmpeg_tools.list_camera_devices",
        return_value=[CameraDevice(display_name="USB Webcam", ffmpeg_token="video=USB Webcam", backend="dshow", is_virtual=False)],
    )
    @patch("app.services.ffmpeg_tools.platform.system", return_value="Windows")
    def test_build_capture_input_candidates_keeps_virtual_flag(self, _platform_mock, _mock_list):
        candidates = ffmpeg_tools.build_capture_input_candidates("USB Webcam")
        self.assertTrue(candidates)
        self.assertTrue(all(not c.is_virtual for c in candidates))
    @patch("app.services.ffmpeg_tools.platform.system", return_value="Windows")
    @patch("app.services.ffmpeg_tools._run_ffmpeg_command")
    def test_verify_windows_dshow_device_token_failure_markers(self, run_mock, _platform_mock):
        run_mock.return_value = type("R", (), {"stderr": "Error opening input file", "stdout": "", "returncode": 1})()
        ok, details = ffmpeg_tools.verify_windows_dshow_device_token("video=OBS Virtual Camera")
        self.assertFalse(ok)
        self.assertIn("Error opening input", details)
