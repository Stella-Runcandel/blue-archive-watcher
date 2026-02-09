"""Storage tests for SQLite metadata and filesystem linkage."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from core import profiles
from core import storage


class StorageTests(unittest.TestCase):
    """Validate SQLite storage behavior and migrations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)
        os.environ["APP_DB_PATH"] = str(Path(self.temp_dir.name) / "Data" / "app.db")

    def tearDown(self):
        os.chdir(self.original_cwd)
        os.environ.pop("APP_DB_PATH", None)

    def test_profile_create_and_list(self):
        """Profiles create and list via SQLite."""
        success, _ = profiles.create_profile("Alpha")
        self.assertTrue(success)
        names = profiles.list_profiles()
        self.assertIn("Alpha", names)

    def test_frames_and_references_linkage(self):
        """Frames and references are linked and listed from SQLite."""
        profiles.create_profile("Beta")
        frame_dir = Path("Data") / "Profiles" / "Beta" / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        frame_path = frame_dir / "frame.png"
        frame_path.write_bytes(b"fake")
        storage.add_frame("Beta", frame_path.name, str(frame_path))
        self.assertIn("frame.png", profiles.list_frames("Beta"))

        ref_dir = Path("Data") / "Profiles" / "Beta" / "references"
        ref_dir.mkdir(parents=True, exist_ok=True)
        ref_path = ref_dir / "ref_1.png"
        ref_path.write_bytes(b"fake")
        storage.add_reference("Beta", ref_path.name, str(ref_path), "frame.png")
        self.assertIn("ref_1.png", profiles.list_references("Beta"))
        self.assertEqual(
            profiles.get_reference_parent_frame("Beta", "ref_1.png"),
            "frame.png",
        )

    def test_debug_eviction(self):
        """Debug eviction removes oldest entries and files."""
        profiles.create_profile("Gamma")
        debug_dir = Path(profiles.get_debug_dir())
        debug_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i in range(3):
            path = debug_dir / f"debug_{i}.png"
            path.write_bytes(b"x" * 10)
            storage.add_debug_entry("Gamma", None, str(path), 10)
            paths.append(path)
        removed = storage.prune_debug_entries(max_bytes=15, max_count=2)
        for path in removed:
            if os.path.exists(path):
                os.remove(path)
        self.assertLessEqual(len(storage.list_debug_entries("Gamma")), 2)

    def test_filesystem_migration(self):
        """Profiles in filesystem migrate into SQLite on list."""
        legacy_dir = Path("Data") / "Profiles" / "Legacy"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        names = profiles.list_profiles()
        self.assertIn("Legacy", names)
