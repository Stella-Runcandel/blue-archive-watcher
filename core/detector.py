import cv2
import numpy as np
import os
from core.profiles import get_profile_dirs
import time

# ---- path setup (DO THIS ONCE) ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # core/
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

def refrence_selector(profile_name):
    # Load reference image (UNCHANGED)
    dirs = get_profile_dirs(profile_name)

    frames_dir = dirs["frames"]
    base_frames = [
        f for f in os.listdir(frames_dir)
        if f.lower().endswith(".png")
    ]

    assert base_frames, "No base frames found for this profile"

    base_path = os.path.join(frames_dir, base_frames[0])
    print("[DEBUG] Using base frame:", base_path)

    img = cv2.imread(base_path)
    assert img is not None, "Base frame could not be loaded"

    orig_h, orig_w = img.shape[:2]

    # --- scale for display only ---
    MAX_W, MAX_H = 1200, 800  # adjust if you want it bigger
    scale = min(MAX_W / orig_w, MAX_H / orig_h, 1.0)

    disp = cv2.resize(
        img,
        (int(orig_w * scale), int(orig_h * scale)),
        interpolation=cv2.INTER_AREA
    )

    # Select ROI on the scaled image <region of interest>
    roi = cv2.selectROI(
        "Select reference region (ENTER to confirm, ESC to cancel)",
        disp,
        fromCenter=False,
        showCrosshair=True
    )

    x, y, w, h = roi
    if w <= 0 or h <= 0:
        cv2.destroyAllWindows()
        return

    # map back to original coords
    x0, y0 = int(x / scale), int(y / scale)
    x1, y1 = int((x + w) / scale), int((y + h) / scale)
    crop = img[y0:y1, x0:x1]

    # 🔑 PROFILE SAVE
    dirs = get_profile_dirs(profile_name)
    ref_dir = dirs["references"]

    existing = [f for f in os.listdir(ref_dir) if f.endswith(".png")]
    ref_path = os.path.join(ref_dir, f"ref_{len(existing)+1}.png")

    cv2.imwrite(ref_path, crop)
    print(f"[REF] Saved {ref_path}")

    cv2.destroyAllWindows()

def frame_comp(profile_name):
    dirs = get_profile_dirs(profile_name)

    frame_path = os.path.join(dirs["captures"], "latest.png")
    if not os.path.exists(frame_path):
        return False

    frame = cv2.imread(frame_path, cv2.IMREAD_GRAYSCALE)
    if frame is None:
        return False


    for ref in os.listdir(dirs["references"]):
        ref_path = os.path.join(dirs["references"], ref)
        template = cv2.imread(ref_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            continue

        # ---- your existing edge + matchTemplate logic ----
        template_e = cv2.Canny(template, 80, 160)
        frame_e = cv2.Canny(frame, 80, 160)

        result = cv2.matchTemplate(
            frame_e, template_e, cv2.TM_CCOEFF_NORMED
        )
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= 0.70:
            x, y = max_loc
            th, tw = template_e.shape[:2]
            debug_path = os.path.join(
            dirs["debug"],
            f"match_{int(time.time())}.png"
            )

            debug = cv2.cvtColor(frame_e, cv2.COLOR_GRAY2BGR)
            cv2.rectangle(debug, (x, y), (x+tw, y+th), (0,255,0), 2)
            cv2.imwrite(debug_path, debug)

            return True

    return False