import cv2
import os
import time
from core.profiles import (
    get_profile_dirs,
    get_debug_dir,
    profile_path,
    get_detection_threshold,
)

# ---- dialogue state ----
_active_dialogue = None        # name of reference currently active
_last_seen_time = 0.0          # last time dialogue was visible
EXIT_TIMEOUT = 0.6             # seconds dialogue must disappear to reset

_debug_counter = 0  # MEDIUM 1: filename-only counter; not used for logic/throttling/safety.
_event_active = False
_last_debug_frame = None
_DEBUG_SIMILARITY_THRESHOLD = 2.0  # CRITICAL 3: provisional threshold; will be tuned later.


def refrence_selector(profile_name):
    dirs = get_profile_dirs(profile_name)

    frames_dir = dirs["frames"]
    base_frames = [f for f in os.listdir(frames_dir) if f.lower().endswith(".png")]
    if not base_frames:
        return False, "No base frames found for this profile"

    base_path = os.path.join(frames_dir, base_frames[0])
    img = cv2.imread(base_path)
    if img is None:
        return False, "Base frame could not be loaded"

    orig_h, orig_w = img.shape[:2]
    scale = min(1200 / orig_w, 800 / orig_h, 1.0)

    disp = cv2.resize(
        img,
        (int(orig_w * scale), int(orig_h * scale)),
        interpolation=cv2.INTER_AREA
    )

    roi = cv2.selectROI(
        "Select reference region (ENTER to confirm, ESC to cancel)",
        disp,
        fromCenter=False,
        showCrosshair=True
    )

    x, y, w, h = roi
    if w <= 0 or h <= 0:
        cv2.destroyAllWindows()
        return False, "Reference selection cancelled"

    x0, y0 = int(x / scale), int(y / scale)
    x1, y1 = int((x + w) / scale), int((y + h) / scale)
    crop = img[y0:y1, x0:x1]

    ref_dir = dirs["references"]
    existing = [f for f in os.listdir(ref_dir) if f.endswith(".png")]
    ref_path = os.path.join(ref_dir, f"ref_{len(existing) + 1}.png")

    cv2.imwrite(ref_path, crop)
    cv2.destroyAllWindows()
    return True, f"Reference saved as {os.path.basename(ref_path)}"


def _frames_similar(current_frame, last_frame):
    if last_frame is None:
        return False
    current_gray = (
        cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
        if current_frame.ndim == 3 else current_frame
    )
    last_gray = (
        cv2.cvtColor(last_frame, cv2.COLOR_BGR2GRAY)
        if last_frame.ndim == 3 else last_frame
    )
    if current_gray.shape != last_gray.shape:
        last_gray = cv2.resize(
            last_gray,
            (current_gray.shape[1], current_gray.shape[0]),
            interpolation=cv2.INTER_AREA
        )
    diff = cv2.absdiff(current_gray, last_gray)
    return diff.mean() <= _DEBUG_SIMILARITY_THRESHOLD


def frame_comp(profile_name):
    global _active_dialogue, _last_seen_time, _debug_counter
    global _event_active, _last_debug_frame

    if not profile_name:
        return False

    # CRITICAL 1: profile validity only affects debug save location, not detection flow.
    profile_valid = os.path.isdir(profile_path(profile_name))

    dirs = get_profile_dirs(profile_name)
    frame_path = os.path.join(dirs["captures"], "latest.png")

    if not os.path.exists(frame_path):
        return False

    frame = cv2.imread(frame_path, cv2.IMREAD_GRAYSCALE)
    if frame is None:
        return False

    frame_e = cv2.Canny(frame, 80, 160)
    now = time.time()

    matched_ref = None
    match_bbox = None

    for ref in os.listdir(dirs["references"]):
        ref_path = os.path.join(dirs["references"], ref)
        template = cv2.imread(ref_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            continue

        template_e = cv2.Canny(template, 80, 160)
        result = cv2.matchTemplate(frame_e, template_e, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val < get_detection_threshold(profile_name):
            continue

        x, y = max_loc
        h, w = template_e.shape[:2]

        # stabilize position to kill jitter
        GRID = 8
        x = (x // GRID) * GRID
        y = (y // GRID) * GRID

        matched_ref = ref
        match_bbox = (x, y, w, h)
        break  # first valid match is enough

    # -------- STATE LOGIC --------

    if matched_ref is not None:
        _last_seen_time = now

        event_start = not _event_active
        if event_start:
            _event_active = True

        if _active_dialogue != matched_ref:
            _active_dialogue = matched_ref

        if event_start:
            debug = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            x, y, w, h = match_bbox
            cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 255, 0), 2)

            if not _frames_similar(debug, _last_debug_frame):
                _debug_counter += 1
                debug_dir, _ = get_debug_dir(
                    profile_name if profile_valid else None,
                    allow_fallback=True
                )
                if debug_dir:
                    debug_path = os.path.join(
                        debug_dir,
                        f"match_{_debug_counter:04d}.png"
                    )
                    cv2.imwrite(debug_path, debug)
                    _last_debug_frame = debug

        return True

    # no match this frame → check for exit
    if _active_dialogue and now - _last_seen_time > EXIT_TIMEOUT:
        _active_dialogue = None
        _event_active = False
        _last_debug_frame = None  # CRITICAL 2: reset similarity guard on event end.

    return False


def crop_existing_reference(profile_name, ref_name):
    from core.profiles import get_profile_dirs
    import cv2
    import os

    dirs = get_profile_dirs(profile_name)
    ref_path = os.path.join(dirs["references"], ref_name)

    img = cv2.imread(ref_path)
    if img is None:
        return False

    roi = cv2.selectROI(
        "Select crop (ENTER to confirm, ESC to cancel)",
        img,
        fromCenter=False,
        showCrosshair=True
    )

    x, y, w, h = roi
    if w <= 0 or h <= 0:
        cv2.destroyAllWindows()
        return False

    crop = img[y:y+h, x:x+w]

    existing = [
        f for f in os.listdir(dirs["references"])
        if f.startswith(ref_name.replace(".png", "_crop"))
    ]

    crop_name = f"{ref_name.replace('.png', '')}_crop{len(existing)+1}.png"
    crop_path = os.path.join(dirs["references"], crop_name)

    cv2.imwrite(crop_path, crop)
    cv2.destroyAllWindows()
    return True
