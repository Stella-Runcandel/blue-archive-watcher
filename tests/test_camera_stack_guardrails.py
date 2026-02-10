"""Guardrails for FFmpeg-only camera enumeration stack."""

from pathlib import Path
import unittest


class CameraStackGuardrailsTests(unittest.TestCase):
    def test_no_forbidden_camera_stack_tokens_in_app_services(self):
        services_dir = Path("app/services")
        forbidden = {
            "import ctypes",
            "from ctypes",
            "CoInitialize",
            "MFCreate",
            "IMF",
            "cv2.VideoCapture",
        }

        for file_path in services_dir.glob("*.py"):
            text = file_path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, msg=f"Forbidden token {token!r} in {file_path}")

    def test_no_media_foundation_compat_module(self):
        self.assertFalse(Path("app/services/mf_enumerator.py").exists())
