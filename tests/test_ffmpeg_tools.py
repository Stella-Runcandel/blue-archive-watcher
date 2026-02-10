"""FFmpeg helper tests for device enumeration parsing."""
import unittest
from unittest.mock import patch

from app.services import ffmpeg_tools


class FfmpegToolsTests(unittest.TestCase):
    """Validate FFmpeg enumeration wiring and cache behavior."""

    def setUp(self):
        ffmpeg_tools._ENUM_CACHE = None

    @patch("app.services.ffmpeg_tools.enumerate_video_devices", return_value=["HD Webcam", "Virtual Cam"])
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

    @patch("app.services.ffmpeg_tools.enumerate_video_devices", return_value=["New Cam"])
    def test_list_video_devices_uses_cache(self, enum_mock):
        ffmpeg_tools._ENUM_CACHE = ["Cached Cam"]
        self.assertEqual(ffmpeg_tools.list_video_devices(), ["Cached Cam"])
        enum_mock.assert_not_called()

    @patch("app.services.ffmpeg_tools.enumerate_video_devices", return_value=["Fresh Cam"])
    def test_list_video_devices_force_refresh_invalidates_cache(self, enum_mock):
        ffmpeg_tools._ENUM_CACHE = ["Stale Cam"]
        self.assertEqual(ffmpeg_tools.list_video_devices(force_refresh=True), ["Fresh Cam"])
        enum_mock.assert_called_once()
