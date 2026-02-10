"""UI behavior tests for panels and validation flows."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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


class DummyNav:
    def pop(self):
        return None

    def push(self, widget, name):
        return None


@unittest.skipUnless(QT_AVAILABLE, "PyQt6 unavailable in test environment")
class UiBehaviorTests(unittest.TestCase):
    """Validate UI refresh logic and validation messaging."""
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        from PyQt6.QtWidgets import QPushButton, QScrollArea
        from app.app_state import app_state
        from app.ui.panels.dashboard import DashboardPanel
        from app.ui.panels.references import ReferencesPanel
        from core import profiles
        from core import storage

        self.QPushButton = QPushButton
        self.QScrollArea = QScrollArea
        self.app_state = app_state
        self.DashboardPanel = DashboardPanel
        self.ReferencesPanel = ReferencesPanel
        self.profiles = profiles
        self.storage = storage

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)
        os.environ["APP_DB_PATH"] = str(Path(self.temp_dir.name) / "Data" / "app.db")
        app_state.active_profile = None
        app_state.selected_frame = None
        app_state.selected_reference = None
        app_state.monitoring_active = False

    def tearDown(self):
        os.chdir(self.original_cwd)
        os.environ.pop("APP_DB_PATH", None)

    def test_reference_list_refresh_after_insert(self):
        """References panel refreshes list when a new reference is added."""
        self.profiles.create_profile("Alpha")
        self.app_state.active_profile = "Alpha"
        panel = self.ReferencesPanel(DummyNav())
        self.assertEqual(panel.info_label.text(), "Selected reference: None")

        frame_dir = Path("Data") / "Profiles" / "Alpha" / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        frame_path = frame_dir / "frame.png"
        frame_path.write_bytes(b"fake")
        self.storage.add_frame("Alpha", frame_path.name, str(frame_path))

        ref_dir = Path("Data") / "Profiles" / "Alpha" / "references"
        ref_dir.mkdir(parents=True, exist_ok=True)
        ref_path = ref_dir / "ref.png"
        ref_path.write_bytes(b"fake")
        self.storage.add_reference("Alpha", ref_path.name, str(ref_path), frame_path.name)

        panel.refresh_references()
        button_texts = [btn.text() for btn in panel.findChildren(self.QPushButton)]
        self.assertTrue(any("ref.png" in text for text in button_texts))

    def test_dashboard_scroll_layout(self):
        """Dashboard panel uses scroll area for resizable layouts."""
        panel = self.DashboardPanel(DummyNav())
        scrolls = panel.findChildren(self.QScrollArea)
        self.assertTrue(scrolls)

    def test_monitor_start_requires_reference(self):
        """Dashboard start shows error when reference is missing."""
        self.profiles.create_profile("Beta")
        self.app_state.active_profile = "Beta"
        panel = self.DashboardPanel(DummyNav())
        panel.start()
        self.assertEqual(panel.status_label.text(), "Select a reference first")
