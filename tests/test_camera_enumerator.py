import unittest

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
