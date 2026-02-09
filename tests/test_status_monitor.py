"""Status monitor tests for UI metrics updates."""
import os
import subprocess
import sys
import unittest


def _module_importable(module: str) -> bool:
    """Return True when module can be imported in a subprocess."""
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


QT_AVAILABLE = _module_importable("PyQt6.QtWidgets")


@unittest.skipUnless(QT_AVAILABLE, "PyQt6 unavailable in test environment")
class StatusMonitorTests(unittest.TestCase):
    """Validate status label updates from metrics payloads."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_metrics_labels_update(self):
        """Dashboard metrics labels update with payload values."""
        from app.ui.panels.dashboard import DashboardPanel
        panel = DashboardPanel(nav=None)
        payload = {
            "capture_fps": 30.5,
            "process_fps": 28.2,
            "dropped": 3,
            "queue_fill": 50.0,
            "last_detection_time": None,
        }
        panel.on_metrics_update(payload)
        self.assertIn("30.50", panel.capture_fps_label.text())
        self.assertIn("28.20", panel.process_fps_label.text())
        self.assertIn("3", panel.dropped_label.text())
        self.assertIn("50%", panel.queue_label.text())
