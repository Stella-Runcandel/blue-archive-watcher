import sys
from pathlib import Path

# Base directory (works in dev + PyInstaller)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

# Two asset locations
ROOT_ASSETS_DIR = BASE_DIR / "Assets"
APP_ASSETS_DIR = BASE_DIR / "app" / "assets"
