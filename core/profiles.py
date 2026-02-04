import os
import json
from datetime import datetime
import re
import shutil

BASE_DIR = os.path.join("Data", "Profiles")

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


def list_debug_frames(profile_name):
    dirs = get_profile_dirs(profile_name)
    debug_dir = dirs["debug"]
    if not os.path.isdir(debug_dir):
        return []
    files = [
        f for f in os.listdir(debug_dir)
        if f.lower().endswith(".png")
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


def get_debug_image_bytes(profile_name, debug_name):
    if not _is_valid_asset_name(debug_name):
        return None
    dirs = get_profile_dirs(profile_name)
    debug_path = _safe_realpath(dirs["debug"], debug_name)
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


def delete_all_debug_frames(profile_name):
    dirs = get_profile_dirs(profile_name)
    debug_dir = dirs["debug"]
    deleted = 0
    if not os.path.isdir(debug_dir):
        return deleted
    for name in os.listdir(debug_dir):
        path = os.path.join(debug_dir, name)
        if (
            os.path.isfile(path)
            and name.lower().endswith(".png")
            and os.path.abspath(path).startswith(os.path.abspath(debug_dir))
        ):
            os.remove(path)
            deleted += 1
    return deleted
