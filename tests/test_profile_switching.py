"""Profile switching tests to ensure monitoring state is preserved."""
import os
import tempfile
import unittest
from pathlib import Path

from core import profiles


class ProfileSwitchingTests(unittest.TestCase):
    """Validate profile switching behavior."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)
        os.environ["APP_DB_PATH"] = str(Path(self.temp_dir.name) / "Data" / "app.db")
        from app.app_state import app_state

        app_state.active_profile = None
        app_state.monitoring_active = False

    def tearDown(self):
        os.chdir(self.original_cwd)
        os.environ.pop("APP_DB_PATH", None)
        from app.app_state import app_state

        app_state.active_profile = None
        app_state.monitoring_active = False

    def test_select_profile_does_not_toggle_monitoring(self):
        """Selecting profiles does not change monitoring_active."""
        profiles.create_profile("One")
        from app.app_state import app_state
        from app.controllers.profile_controller import ProfileController

        controller = ProfileController()
        app_state.monitoring_active = False
        success, _ = controller.select_profile("One")
        self.assertTrue(success)
        self.assertFalse(app_state.monitoring_active)

    def test_select_profile_blocked_while_monitoring(self):
        """Profile switching is blocked while monitoring is active."""
        profiles.create_profile("Two")
        from app.app_state import app_state
        from app.controllers.profile_controller import ProfileController

        controller = ProfileController()
        app_state.monitoring_active = True
        success, _ = controller.select_profile("Two")
        self.assertFalse(success)
