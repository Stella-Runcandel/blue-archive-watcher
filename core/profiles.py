import os
import json
from datetime import datetime
import re
import shutil

BASE_DIR = os.path.join("Data", "Profiles")
DEBUG_FALLBACK_DIR = os.path.join("Data", "Debug")
DEBUG_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_DETECTION_THRESHOLD = 0.70
MIN_DETECTION_THRESHOLD = 0.50
MAX_DETECTION_THRESHOLD = 0.95

def profile_path(name):
    return os.path.join(BASE_DIR, name)

def validate_profile_name(profile_name):
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
    if not os.path.exists(BASE_DIR):
        return []
    profiles = [
        d for d in os.listdir(BASE_DIR)
        if os.path.isdir(profile_path(d))
    ]
    return sorted(profiles, key=str.lower)


def get_profile_dirs(profile_name):
    root = os.path.join(BASE_DIR, profile_name)

    dirs = {
        "root": root,
        "references": os.path.join(root, "references"),
        "captures": os.path.join(root, "captures"),
        "frames": os.path.join(root, "frames"),
        "debug": os.path.join(root, "debug"),
        "meta": os.path.join(root, "meta.json"),
    }

    for k, path in dirs.items():
        if k != "meta":
            os.makedirs(path, exist_ok=True)

    if not os.path.exists(dirs["meta"]):
        with open(dirs["meta"], "w") as f:
            json.dump({"name": profile_name}, f, indent=2)

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
    os.makedirs(os.path.join(base, "debug"), exist_ok=True)

    meta_path = os.path.join(base, "meta.json")
    with open(meta_path, "w") as f:
        json.dump(
            {
                "name": profile_name,
                "created_at": datetime.now().isoformat()
            },
            f,
            indent=2
        )

    return True, f"Profile '{profile_name}' created."

def delete_profile(profile_name):
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
    return True, f"Profile '{profile_name}' deleted."


def _is_valid_asset_name(name):
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
    path = os.path.realpath(os.path.join(base_dir, name))
    base = os.path.realpath(base_dir)
    if not path.startswith(base + os.path.sep):
        return None
    return path


def _is_supported_debug_name(name):
    return name.lower().endswith(DEBUG_EXTENSIONS)


def get_debug_dir(profile_name, allow_fallback=False):
    if profile_name:
        valid, _ = validate_profile_name(profile_name)
        if valid:
            root = profile_path(profile_name)
            if os.path.isdir(root):
                debug_dir = os.path.join(root, "debug")
                os.makedirs(debug_dir, exist_ok=True)
                return debug_dir, False
    if allow_fallback:
        os.makedirs(DEBUG_FALLBACK_DIR, exist_ok=True)
        return DEBUG_FALLBACK_DIR, True
    return None, False


def _clamp_detection_threshold(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = DEFAULT_DETECTION_THRESHOLD
    return max(MIN_DETECTION_THRESHOLD, min(MAX_DETECTION_THRESHOLD, numeric))


def get_detection_threshold(profile_name):
    threshold = None
    if profile_name:
        dirs = get_profile_dirs(profile_name)
        meta_path = dirs["meta"]
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r") as f:
                    data = json.load(f) or {}
                if "detection_threshold" in data:
                    threshold = data.get("detection_threshold")
            except Exception:
                threshold = None
    if threshold is None:
        threshold = DEFAULT_DETECTION_THRESHOLD
    return _clamp_detection_threshold(threshold)


def update_profile_detection_threshold(profile_name, threshold):
    if not profile_name:
        return False
    dirs = get_profile_dirs(profile_name)
    meta_path = dirs["meta"]
    data = {"name": profile_name}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as f:
                data.update(json.load(f) or {})
        except Exception:
            pass
    threshold_value = _clamp_detection_threshold(threshold)
    if threshold_value == DEFAULT_DETECTION_THRESHOLD:
        if "detection_threshold" not in data:
            return False
        data.pop("detection_threshold", None)
    else:
        data["detection_threshold"] = threshold_value
    with open(meta_path, "w") as f:
        json.dump(data, f, indent=2)
    return True




def has_profile_camera_index(profile_name):
    if not profile_name:
        return False
    dirs = get_profile_dirs(profile_name)
    meta_path = dirs["meta"]
    if not os.path.exists(meta_path):
        return False
    try:
        with open(meta_path, "r") as f:
            data = json.load(f) or {}
        return "camera_index" in data
    except Exception:
        return False


def get_profile_camera_index(profile_name):
    camera_index = 2
    if not profile_name:
        return camera_index
    dirs = get_profile_dirs(profile_name)
    meta_path = dirs["meta"]
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as f:
                data = json.load(f) or {}
            camera_index = int(data.get("camera_index", camera_index))
        except Exception:
            camera_index = 2
    return camera_index


def set_profile_camera_index(profile_name, camera_index):
    if not profile_name:
        return False
    dirs = get_profile_dirs(profile_name)
    meta_path = dirs["meta"]
    data = {"name": profile_name}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as f:
                data.update(json.load(f) or {})
        except Exception:
            pass
    try:
        data["camera_index"] = int(camera_index)
    except (TypeError, ValueError):
        return False
    with open(meta_path, "w") as f:
        json.dump(data, f, indent=2)
    return True

def list_frames(profile_name):
    dirs = get_profile_dirs(profile_name)
    frames_dir = dirs["frames"]
    if not os.path.isdir(frames_dir):
        return []
    frames = [
        f for f in os.listdir(frames_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ]
    return sorted(frames, key=str.lower)


def list_references(profile_name):
    dirs = get_profile_dirs(profile_name)
    ref_dir = dirs["references"]
    if not os.path.isdir(ref_dir):
        return []
    refs = [
        f for f in os.listdir(ref_dir)
        if f.lower().endswith(".png")
    ]
    return sorted(refs, key=str.lower)


def list_debug_frames(profile_name, allow_fallback=False):
    # MEDIUM 2: fallback listing is exclusive (profile OR global), never both.
    debug_dir, _ = get_debug_dir(profile_name, allow_fallback=allow_fallback)
    if not debug_dir or not os.path.isdir(debug_dir):
        return []
    files = [
        f for f in os.listdir(debug_dir)
        if f.lower().endswith(DEBUG_EXTENSIONS)
    ]
    return sorted(files, key=str.lower)


def get_reference_parent_frame(profile_name, ref_name):
    dirs = get_profile_dirs(profile_name)
    meta_path = os.path.join(
        dirs["references"],
        ref_name.replace(".png", ".json")
    )

    if not os.path.exists(meta_path):
        return "legacy"

    try:
        with open(meta_path, "r") as f:
            content = f.read().strip()
            if not content:
                return "legacy"
            data = json.loads(content)
            return data.get("parent_frame", "legacy")
    except Exception:
        return "legacy"


def _load_image_bytes(path):
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
    if not _is_valid_asset_name(frame_name):
        return None
    dirs = get_profile_dirs(profile_name)
    frame_path = _safe_realpath(dirs["frames"], frame_name)
    return _load_image_bytes(frame_path)


def get_reference_image_bytes(profile_name, ref_name):
    if not _is_valid_asset_name(ref_name):
        return None
    dirs = get_profile_dirs(profile_name)
    ref_path = _safe_realpath(dirs["references"], ref_name)
    return _load_image_bytes(ref_path)


def get_debug_image_bytes(profile_name, debug_name, allow_fallback=False):
    if not _is_valid_asset_name(debug_name):
        return None
    if not _is_supported_debug_name(debug_name):
        return None
    debug_dir, _ = get_debug_dir(profile_name, allow_fallback=allow_fallback)
    if not debug_dir:
        return None
    debug_path = _safe_realpath(debug_dir, debug_name)
    return _load_image_bytes(debug_path)


def get_profile_icon_bytes(profile_name):
    dirs = get_profile_dirs(profile_name)
    meta_path = dirs["meta"]
    candidates = []

    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as f:
                data = json.load(f)
            icon_name = data.get("icon")
            if icon_name and _is_valid_asset_name(icon_name):
                candidates.append(icon_name)
        except Exception:
            pass

    candidates.extend(["icon.png", "icon.jpg", "icon.jpeg"])
    for name in candidates:
        icon_path = _safe_realpath(dirs["root"], name)
        data = _load_image_bytes(icon_path)
        if data:
            return data
    return None


def set_profile_icon(profile_name, source_path):
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

    meta_path = dirs["meta"]
    data = {"name": profile_name}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as f:
                data.update(json.load(f) or {})
        except Exception:
            pass

    old_icon = data.get("icon")
    if old_icon and _is_valid_asset_name(old_icon):
        old_path = _safe_realpath(dirs["root"], old_icon)
        if (
            old_path
            and os.path.isfile(old_path)
            and os.path.abspath(old_path) != os.path.abspath(dest_path)
        ):
            os.remove(old_path)

    os.makedirs(dirs["root"], exist_ok=True)
    shutil.copy2(source_path, dest_path)
    data["icon"] = dest_name

    with open(meta_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Profile icon set for '{profile_name}': {dest_name}")
    return True, f"Profile icon set for '{profile_name}'."


def import_frames(profile_name, file_paths):
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
            added += 1
    return added


def delete_reference_files(profile_name, ref_name):
    if not _is_valid_asset_name(ref_name):
        return False, "Invalid reference name."
    dirs = get_profile_dirs(profile_name)
    ref_dir = dirs["references"]
    ref_path = _safe_realpath(ref_dir, ref_name)
    if not ref_path or not os.path.exists(ref_path):
        return False, "Reference not found."
    if os.path.isfile(ref_path):
        os.remove(ref_path)

    meta_name = f"{os.path.splitext(ref_name)[0]}.json"
    meta_path = _safe_realpath(ref_dir, meta_name)
    if meta_path and os.path.exists(meta_path) and os.path.isfile(meta_path):
        os.remove(meta_path)
    return True, f"Reference '{ref_name}' deleted."


def delete_frame_and_references(profile_name, frame_name):
    if not _is_valid_asset_name(frame_name):
        return False, "Invalid frame name.", []
    dirs = get_profile_dirs(profile_name)
    frame_dir = dirs["frames"]
    frame_path = _safe_realpath(frame_dir, frame_name)
    if not frame_path or not os.path.exists(frame_path):
        return False, "Frame not found.", []
    if os.path.isfile(frame_path):
        os.remove(frame_path)

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
    if not _is_valid_asset_name(debug_name):
        return False
    if not _is_supported_debug_name(debug_name):
        return False
    debug_dir, _ = get_debug_dir(profile_name, allow_fallback=allow_fallback)
    if not debug_dir:
        return False
    debug_path = _safe_realpath(debug_dir, debug_name)
    if not debug_path or not os.path.exists(debug_path):
        return False
    if os.path.isfile(debug_path):
        os.remove(debug_path)
        return True
    return False


def delete_all_debug_frames(profile_name, allow_fallback=False):
    debug_dir, _ = get_debug_dir(profile_name, allow_fallback=allow_fallback)
    deleted = 0
    if not debug_dir or not os.path.isdir(debug_dir):
        return deleted
    for name in os.listdir(debug_dir):
        if not _is_supported_debug_name(name):
            continue
        path = os.path.join(debug_dir, name)
        if (
            os.path.isfile(path)
            and os.path.abspath(path).startswith(os.path.abspath(debug_dir))
        ):
            os.remove(path)
            deleted += 1
    return deleted
