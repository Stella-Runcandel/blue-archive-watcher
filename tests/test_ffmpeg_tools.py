"""FFmpeg helper tests for device enumeration parsing."""
import unittest

from app.services import ffmpeg_tools


class FfmpegToolsTests(unittest.TestCase):
    """Validate FFmpeg output parsing."""

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
