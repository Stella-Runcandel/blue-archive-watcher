#this includes the logic behind when to create 
#how to create
#and how to handle files for different games, etc
import os
import json

BASE_DIR = os.path.join("Data", "Profiles")

def profile_path(name):
    return os.path.join(BASE_DIR, name)

def create_profile(name):
    path = profile_path(name)

    os.makedirs(os.path.join(path, "references"), exist_ok=True)
    os.makedirs(os.path.join(path, "captures"), exist_ok=True)
    os.makedirs(os.path.join(path, "debug"), exist_ok=True)

    meta_path = os.path.join(path, "meta.json")
    if not os.path.exists(meta_path):
        with open(meta_path, "w") as f:
            json.dump({
                "name": name,
                "bring_to_front": False,
                "sound": True
            }, f, indent=2)

    return path

def list_profiles():
    if not os.path.exists(BASE_DIR):
        return []
    return [
        d for d in os.listdir(BASE_DIR)
        if os.path.isdir(profile_path(d))
    ]


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