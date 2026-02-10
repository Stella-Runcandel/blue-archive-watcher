"""FFmpeg helper tests for device enumeration parsing."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services import ffmpeg_tools


class FfmpegToolsTests(unittest.TestCase):
    """Validate FFmpeg output parsing."""

    def setUp(self):
        ffmpeg_tools._ENUM_CACHE = None

    def test_parse_dshow_devices(self):
        """Parse DirectShow device list from stderr text."""
        sample = """
[dshow @ 0000000001] DirectShow video devices (some may be both video and audio devices)
[dshow @ 0000000001]  "Camera One"
[dshow @ 0000000001]  "Camera Two"
[dshow @ 0000000001] DirectShow audio devices
[dshow @ 0000000001]  "Microphone"
"""
        devices = ffmpeg_tools._parse_dshow_video_devices(sample)
        self.assertEqual(devices, ["Camera One", "Camera Two"])

    @patch("app.services.ffmpeg_tools.subprocess.run")
    def test_list_video_devices_reads_stderr(self, mock_run):
        """Device enumeration should parse DirectShow names from stderr output."""
        mock_run.return_value = SimpleNamespace(
            stdout="",
            stderr=(
                "[dshow @ a] DirectShow video devices\n"
                "[dshow @ a]  \"HD Webcam\"\n"
                "[dshow @ a]  \"Virtual Cam\"\n"
                "[dshow @ a] DirectShow audio devices\n"
                "[dshow @ a]  \"Microphone\"\n"
            ),
            returncode=1,
        )

        devices = ffmpeg_tools.list_video_devices()

        self.assertEqual(devices, ["HD Webcam", "Virtual Cam"])

    @patch("app.services.ffmpeg_tools.subprocess.run", side_effect=FileNotFoundError)
    def test_list_video_devices_returns_empty_on_failure(self, _):
        """Device enumeration should fail safely when FFmpeg is unavailable."""
        self.assertEqual(ffmpeg_tools.list_video_devices(), [])


    @patch("app.services.ffmpeg_tools.enumerate_video_devices", side_effect=RuntimeError("boom"))
    @patch("app.services.ffmpeg_tools.platform.system", return_value="Windows")
    def test_list_video_devices_windows_no_opencv_fallback(self, _platform_mock, _enum_mock):
        """Windows path does not use OpenCV fallback and fails safe to []."""
        ffmpeg_tools._ENUM_CACHE = None
        devices = ffmpeg_tools.list_video_devices(force_refresh=True)
        self.assertEqual(devices, [])

    @patch("app.services.ffmpeg_tools._run_ffmpeg_command")
    def test_list_video_devices_uses_cache(self, run_mock):
        """Enumeration cache should be reused until force_refresh."""
        run_mock.return_value = SimpleNamespace(stdout="", stderr="", returncode=1)
        ffmpeg_tools._ENUM_CACHE = ["Cached Cam"]
        self.assertEqual(ffmpeg_tools.list_video_devices(), ["Cached Cam"])
        run_mock.assert_not_called()
