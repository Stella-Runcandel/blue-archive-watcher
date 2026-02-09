"""Profile and data management for FrameTrace.

Design:
- SQLite stores metadata (profiles, frames, references, debug).
- Filesystem stores images under Data/Profiles and Data/Debug.
"""
import os
import re
import shutil

from core import storage

BASE_DIR = os.path.join("Data", "Profiles")
DEBUG_DIR = os.path.join("Data", "Debug")
DEBUG_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_DETECTION_THRESHOLD = 0.70
MIN_DETECTION_THRESHOLD = 0.50
MAX_DETECTION_THRESHOLD = 0.95
DEFAULT_TARGET_FPS = 30
MIN_TARGET_FPS = 1
MAX_TARGET_FPS = 60
DEFAULT_FRAME_SIZE = (1280, 720)

def profile_path(name):
    """Return filesystem path for a profile root directory."""
    return os.path.join(BASE_DIR, name)

def validate_profile_name(profile_name):
    """Validate profile name for safe filesystem storage."""
    if not profile_name:
        return False, "Profile name cannot be empty."
    name = profile_name.strip()
    if not name:
        return False, "Profile name cannot be empty."
    if name in {".", ".."}:
        return False, "Profile name is not allowed."
    if os.path.sep in name or (os.path.altsep and os.path.altsep in name):
        return False, "Profile name cannot include path separators."
    if name != os.path.basename(name):
        return False, "Profile name is not allowed."
    if not re.match(r"^[A-Za-z0-9 _-]+$", name):
        return False, "Profile name can only include letters, numbers, spaces, _ or -."
    return True, ""

def list_profiles():
    """Return profile names from SQLite, migrating filesystem directories if needed."""
    profiles = storage.list_profiles()
    if profiles:
        return profiles
    if not os.path.exists(BASE_DIR):
        return []
    discovered = [
        d for d in os.listdir(BASE_DIR)
        if os.path.isdir(profile_path(d))
    ]
    for name in discovered:
        try:
            storage.create_profile(name)
        except Exception:
            continue
    return sorted(discovered, key=str.lower)


def get_profile_dirs(profile_name):
    """Ensure profile directories exist and return paths dict (root, frames, references, captures)."""
    root = os.path.join(BASE_DIR, profile_name)

    dirs = {
        "root": root,
        "references": os.path.join(root, "references"),
        "captures": os.path.join(root, "captures"),
        "frames": os.path.join(root, "frames"),
    }

    for k, path in dirs.items():
        os.makedirs(path, exist_ok=True)

    return dirs

def create_profile(profile_name):
    """
    Create a new profile with required folder structure.
    Returns (success, message).
    """
    valid, message = validate_profile_name(profile_name)
    if not valid:
        return False, message
    base = os.path.join(BASE_DIR, profile_name)
    if os.path.exists(base):
        return False, "A profile with that name already exists."
    os.makedirs(os.path.join(base, "frames"), exist_ok=True)
    os.makedirs(os.path.join(base, "references"), exist_ok=True)
    os.makedirs(os.path.join(base, "captures"), exist_ok=True)
    storage.create_profile(profile_name)
    return True, f"Profile '{profile_name}' created."

def delete_profile(profile_name):
    """Delete a profile and its filesystem contents."""
    """Remove a profile and its data. Returns (success, message). Validates path to prevent traversal."""
    valid, message = validate_profile_name(profile_name)
    if not valid:
        return False, message
    base = os.path.realpath(BASE_DIR)
    target = os.path.realpath(profile_path(profile_name))
    if not target.startswith(base + os.path.sep):
        return False, "Invalid profile path."
    if not os.path.exists(target):
        return False, "Profile not found."
    shutil.rmtree(target)
    storage.delete_profile(profile_name)
    return True, f"Profile '{profile_name}' deleted."


def _is_valid_asset_name(name):
    """Validate asset filenames to avoid traversal."""
    if not name:
        return False
    if name in {".", ".."}:
        return False
    if os.path.sep in name or (os.path.altsep and os.path.altsep in name):
        return False
    if name != os.path.basename(name):
        return False
    return True


def _safe_realpath(base_dir, name):
    """Return safe realpath or None if outside base_dir."""
    path = os.path.realpath(os.path.join(base_dir, name))
    base = os.path.realpath(base_dir)
    if not path.startswith(base + os.path.sep):
        return None
    return path


def _is_supported_debug_name(name):
    """Return True if filename is a supported debug image."""
    return name.lower().endswith(DEBUG_EXTENSIONS)


def get_debug_dir():
    """Return global debug directory path (created if missing)."""
    os.makedirs(DEBUG_DIR, exist_ok=True)
    return DEBUG_DIR


def _clamp_detection_threshold(value):
    """Clamp detection threshold within bounds."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = DEFAULT_DETECTION_THRESHOLD
    return max(MIN_DETECTION_THRESHOLD, min(MAX_DETECTION_THRESHOLD, numeric))


def get_detection_threshold(profile_name):
    """Fetch profile detection threshold from SQLite with defaults."""
    record = storage.get_profile(profile_name) if profile_name else None
    threshold = record.detection_threshold if record else None
    if threshold is None:
        threshold = DEFAULT_DETECTION_THRESHOLD
    return _clamp_detection_threshold(threshold)


def update_profile_detection_threshold(profile_name, threshold):
    """Persist detection threshold for a profile."""
    if not profile_name:
        return False
    threshold_value = _clamp_detection_threshold(threshold)
    storage.update_profile_fields(profile_name, detection_threshold=threshold_value)
    return True


def _clamp_target_fps(value):
    """Clamp target FPS within bounds."""
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = DEFAULT_TARGET_FPS
    return max(MIN_TARGET_FPS, min(MAX_TARGET_FPS, numeric))


def get_profile_fps(profile_name):
    """Fetch target FPS for a profile from SQLite."""
    fps = None
    if profile_name:
        record = storage.get_profile(profile_name)
        fps = record.target_fps if record else None
    if fps is None:
        fps = DEFAULT_TARGET_FPS
    return _clamp_target_fps(fps)


def update_profile_fps(profile_name, fps):
    """Persist target FPS for a profile."""
    if not profile_name:
        return False
    fps_value = _clamp_target_fps(fps)
    storage.update_profile_fields(profile_name, target_fps=fps_value)
    return True


def get_profile_camera_device(profile_name):
    """Fetch camera device name for a profile."""
    if not profile_name:
        return None
    record = storage.get_profile(profile_name)
    return record.camera_device if record else None


def set_profile_camera_device(profile_name, device_name):
    """Persist camera device name for a profile."""
    if not profile_name:
        return False
    if not device_name:
        return False
    storage.update_profile_fields(profile_name, camera_device=str(device_name))
    return True


def get_profile_frame_size(profile_name):
    """Return width/height of first frame image for the profile."""
    import cv2
    if not profile_name:
        return None, None
    dirs = get_profile_dirs(profile_name)
    frames_dir = dirs["frames"]
    if not os.path.isdir(frames_dir):
        return None, None
    for name in sorted(os.listdir(frames_dir), key=str.lower):
        if not name.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        path = os.path.join(frames_dir, name)
        frame = cv2.imread(path)
        if frame is None:
            continue
        height, width = frame.shape[:2]
        if width > 0 and height > 0:
            return width, height
    return None, None


def get_profile_frame_size_fallback():
    """Return fallback capture resolution when frames are missing."""
    return DEFAULT_FRAME_SIZE




def list_frames(profile_name):
    """List frame names for a profile from SQLite."""
    return storage.list_frames(profile_name)


def list_references(profile_name):
    """List reference names for a profile from SQLite."""
    return storage.list_references(profile_name)


def list_debug_frames(profile_name, allow_fallback=False):
    """List debug image names, optionally filtering by profile."""
    profile_filter = profile_name if not allow_fallback else None
    entries = storage.list_debug_entries(profile_filter)
    return [os.path.basename(entry["path"]) for entry in entries]


def get_reference_parent_frame(profile_name, ref_name):
    """Return parent frame name stored for the reference."""
    frame_name = storage.get_reference_parent_frame(profile_name, ref_name)
    return frame_name or "legacy"


def _load_image_bytes(path):
    """Read image bytes from disk or return None."""
    if not path or not os.path.exists(path):
        return None
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def get_frame_image_bytes(profile_name, frame_name):
    """Load frame image bytes from disk."""
    if not _is_valid_asset_name(frame_name):
        return None
    dirs = get_profile_dirs(profile_name)
    frame_path = _safe_realpath(dirs["frames"], frame_name)
    return _load_image_bytes(frame_path)


def get_reference_image_bytes(profile_name, ref_name):
    """Load reference image bytes from disk."""
    if not _is_valid_asset_name(ref_name):
        return None
    dirs = get_profile_dirs(profile_name)
    ref_path = _safe_realpath(dirs["references"], ref_name)
    return _load_image_bytes(ref_path)


def get_debug_image_bytes(profile_name, debug_name, allow_fallback=False):
    """Load debug image bytes from global debug directory."""
    if not _is_valid_asset_name(debug_name):
        return None
    if not _is_supported_debug_name(debug_name):
        return None
    debug_path = _safe_realpath(get_debug_dir(), debug_name)
    return _load_image_bytes(debug_path)


def get_profile_icon_bytes(profile_name):
    """Load profile icon image bytes."""
    dirs = get_profile_dirs(profile_name)
    candidates = []
    record = storage.get_profile(profile_name)
    if record and record.icon_path and _is_valid_asset_name(record.icon_path):
        candidates.append(record.icon_path)
    candidates.extend(["icon.png", "icon.jpg", "icon.jpeg"])
    for name in candidates:
        icon_path = _safe_realpath(dirs["root"], name)
        data = _load_image_bytes(icon_path)
        if data:
            return data
    return None


def set_profile_icon(profile_name, source_path):
    """Copy and register a profile icon image."""
    valid, message = validate_profile_name(profile_name)
    if not valid:
        return False, message
    if not source_path or not os.path.isfile(source_path):
        return False, "Icon file not found."
    ext = os.path.splitext(source_path)[1].lower()
    if ext not in {".png", ".jpg", ".jpeg"}:
        return False, "Icon must be a PNG or JPG image."

    dirs = get_profile_dirs(profile_name)
    dest_name = f"{profile_name}_profile_icon{ext}"
    if not _is_valid_asset_name(dest_name):
        return False, "Invalid icon filename."
    dest_path = _safe_realpath(dirs["root"], dest_name)
    if not dest_path:
        return False, "Invalid icon path."

    os.makedirs(dirs["root"], exist_ok=True)
    shutil.copy2(source_path, dest_path)
    storage.update_profile_fields(profile_name, icon_path=dest_name)

    print(f"Profile icon set for '{profile_name}': {dest_name}")
    return True, f"Profile icon set for '{profile_name}'."


def import_frames(profile_name, file_paths):
    """Import external images into profile frames directory."""
    dirs = get_profile_dirs(profile_name)
    frames_dir = dirs["frames"]
    added = 0
    for src in file_paths:
        if not os.path.isfile(src):
            continue
        name = os.path.basename(src)
        dst = os.path.join(frames_dir, name)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
            storage.add_frame(profile_name, name, dst)
            added += 1
    return added


def delete_reference_files(profile_name, ref_name):
    """Delete reference image file and metadata."""
    if not _is_valid_asset_name(ref_name):
        return False, "Invalid reference name."
    dirs = get_profile_dirs(profile_name)
    ref_dir = dirs["references"]
    ref_path = _safe_realpath(ref_dir, ref_name)
    if not ref_path or not os.path.exists(ref_path):
        return False, "Reference not found."
    if os.path.isfile(ref_path):
        os.remove(ref_path)
    storage.delete_reference(profile_name, ref_name)
    return True, f"Reference '{ref_name}' deleted."


def delete_frame_and_references(profile_name, frame_name):
    """Delete a frame and any references derived from it."""
    if not _is_valid_asset_name(frame_name):
        return False, "Invalid frame name.", []
    dirs = get_profile_dirs(profile_name)
    frame_dir = dirs["frames"]
    frame_path = _safe_realpath(frame_dir, frame_name)
    if not frame_path or not os.path.exists(frame_path):
        return False, "Frame not found.", []
    if os.path.isfile(frame_path):
        os.remove(frame_path)
    storage.delete_frame(profile_name, frame_name)

    deleted_refs = []
    for ref_name in list_references(profile_name):
        parent_frame = get_reference_parent_frame(profile_name, ref_name)
        if parent_frame == frame_name:
            success, _ = delete_reference_files(profile_name, ref_name)
            if success:
                deleted_refs.append(ref_name)

    if deleted_refs:
        message = (
            f"Frame '{frame_name}' deleted "
            f"({len(deleted_refs)} references removed)."
        )
    else:
        message = f"Frame '{frame_name}' deleted."
    return True, message, deleted_refs


def delete_debug_frame(profile_name, debug_name, allow_fallback=False):
    """Delete a single debug frame. Returns (success, bytes_freed)."""
    if not _is_valid_asset_name(debug_name):
        return False, 0
    if not _is_supported_debug_name(debug_name):
        return False, 0
    debug_path = _safe_realpath(get_debug_dir(), debug_name)
    if not debug_path or not os.path.exists(debug_path):
        return False, 0
    if os.path.isfile(debug_path):
        try:
            bytes_freed = os.path.getsize(debug_path)
        except Exception:
            bytes_freed = 0
        os.remove(debug_path)
        entries = storage.list_debug_entries(profile_name if not allow_fallback else None)
        for entry in entries:
            if os.path.basename(entry["path"]) == debug_name:
                storage.delete_debug_entries([entry["id"]])
                break
        return True, bytes_freed
    return False, 0


def delete_all_debug_frames(profile_name, allow_fallback=False):
    """Delete all debug frames. Returns (deleted_count, bytes_freed)."""
    entries = storage.list_debug_entries(profile_name if not allow_fallback else None)
    deleted = 0
    bytes_freed = 0
    for entry in entries:
        path = entry["path"]
        if os.path.isfile(path):
            try:
                bytes_freed += os.path.getsize(path)
            except Exception:
                pass
            os.remove(path)
            deleted += 1
    storage.delete_debug_entries([entry["id"] for entry in entries])
    return deleted, bytes_freed
