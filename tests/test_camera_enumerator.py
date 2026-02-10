import unittest
from unittest.mock import patch

from app.services import camera_enumerator


class CameraEnumeratorTests(unittest.TestCase):
    def test_parse_dshow_video_devices(self):
        sample = """
[dshow @ 0000000001] DirectShow video devices
[dshow @ 0000000001]  \"Camera One\"
[dshow @ 0000000001]  \"Camera Two\"
[dshow @ 0000000001] DirectShow audio devices
[dshow @ 0000000001]  \"Microphone\"
"""
        self.assertEqual(camera_enumerator._parse_dshow_video_devices(sample), ["Camera One", "Camera Two"])

    def test_parse_avfoundation_video_devices(self):
        sample = """
[AVFoundation indev @ 0x0] AVFoundation video devices:
[AVFoundation indev @ 0x0] [0] FaceTime HD Camera
[AVFoundation indev @ 0x0] [1] OBS Virtual Camera
[AVFoundation indev @ 0x0] AVFoundation audio devices:
[AVFoundation indev @ 0x0] [0] Built-in Microphone
"""
        self.assertEqual(
            camera_enumerator._parse_avfoundation_video_devices(sample),
            ["FaceTime HD Camera", "OBS Virtual Camera"],
        )

    def test_parse_dshow_skips_alternative_name_lines(self):
        sample = """
[dshow @ 0000000001] DirectShow video devices
[dshow @ 0000000001]  \"OBS Virtual Camera\"
[dshow @ 0000000001]     Alternative name \"@device_pnp_\\?\\usb#vid\"
[dshow @ 0000000001] DirectShow audio devices
"""
        self.assertEqual(camera_enumerator._parse_dshow_video_devices(sample), ["OBS Virtual Camera"])

    def test_parse_v4l2_sources(self):
        sample = """
Auto-detected sources for v4l2:
  * video4linux2,v4l2 [/dev/video0]
  * video4linux2,v4l2 [/dev/video2]
"""
        self.assertEqual(camera_enumerator._parse_v4l2_sources(sample), ["/dev/video0", "/dev/video2"])

    def test_dedupe_case_insensitive_preserves_order(self):
        devices = ["OBS Virtual Camera", "obs virtual camera", "USB Cam"]
        self.assertEqual(camera_enumerator._dedupe(devices), ["OBS Virtual Camera", "USB Cam"])

    @patch("app.services.camera_enumerator.platform.system", return_value="Windows")
    @patch("app.services.camera_enumerator._run_ffmpeg", side_effect=RuntimeError("boom"))
    def test_enumerate_video_devices_fails_safe_to_empty(self, _run_mock, _platform_mock):
        self.assertEqual(camera_enumerator.enumerate_video_devices(), [])
