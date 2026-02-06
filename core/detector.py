import cv2
import os
import time
import logging
from dataclasses import dataclass
from core.profiles import (
    BASE_DIR,
    DEBUG_EXTENSIONS,
    DEBUG_FALLBACK_DIR,
    get_profile_dirs,
    get_debug_dir,
    profile_path,
    get_detection_threshold,
)

EXIT_TIMEOUT = 0.6             # seconds dialogue must disappear to reset
DEBUG_STORAGE_LIMIT_BYTES = 1_073_741_824  # 1 GB



@dataclass
class DetectorState:
    active_dialogue: str | None = None
    event_active: bool = False
    last_seen_time: float = 0.0
    last_debug_frame: object = None
    debug_counter: int = 0
    debug_limit_warning_emitted: bool = False
    total_debug_storage_bytes: int = 0


def new_detector_state():
    state = DetectorState()
    initialize_debug_storage_tracking(state)
    return state


def _iter_all_debug_dirs_for_initialization():
    if os.path.isdir(BASE_DIR):
        for profile_name in os.listdir(BASE_DIR):
            profile_dir = profile_path(profile_name)
            if not os.path.isdir(profile_dir):
                continue
            debug_dir = os.path.join(profile_dir, "debug")
            if os.path.isdir(debug_dir):
                yield debug_dir

    if os.path.isdir(DEBUG_FALLBACK_DIR):
        yield DEBUG_FALLBACK_DIR


def _compute_initial_debug_storage_bytes():
    total = 0
    for debug_dir in _iter_all_debug_dirs_for_initialization():
        try:
            names = os.listdir(debug_dir)
        except Exception:
            continue

        for name in names:
            if not name.lower().endswith(DEBUG_EXTENSIONS):
                continue
            path = os.path.join(debug_dir, name)
            try:
                if os.path.isfile(path):
                    total += os.path.getsize(path)
            except Exception:
                continue
    return total


def initialize_debug_storage_tracking(state):
    try:
        state.total_debug_storage_bytes = _compute_initial_debug_storage_bytes()
    except Exception:
        logging.warning("Failed to initialize debug storage accounting.", exc_info=True)
        state.total_debug_storage_bytes = DEBUG_STORAGE_LIMIT_BYTES


def _emit_debug_limit_warning_once(state):
    if state.debug_limit_warning_emitted:
        return
    logging.warning(
        "Debug storage limit reached (1 GB). "
        "Debug images are paused. Monitoring continues normally."
    )
    state.debug_limit_warning_emitted = True


def _save_debug_image_if_allowed(debug_dir, debug_image, state):
    try:
        if state.total_debug_storage_bytes >= DEBUG_STORAGE_LIMIT_BYTES:
            _emit_debug_limit_warning_once(state)
            return

        state.debug_counter += 1
        debug_path = os.path.join(
            debug_dir,
            f"match_{time.time_ns()}_{state.debug_counter:04d}.png"
        )
        if not cv2.imwrite(debug_path, debug_image):
            logging.warning("Failed to write debug image; continuing monitoring.")
            return

        try:
            state.total_debug_storage_bytes += os.path.getsize(debug_path)
        except Exception:
            logging.warning("Failed to read debug image size; continuing monitoring.", exc_info=True)

        state.last_debug_frame = debug_image
    except Exception:
        logging.warning("Failed to write debug image; continuing monitoring.", exc_info=True)



_default_detector_state = new_detector_state()

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


def _save_capture_snapshot(profile_name, frame):
    dirs = get_profile_dirs(profile_name)
    captures_dir = dirs["captures"]

    latest_path = os.path.join(captures_dir, "latest.png")
    cv2.imwrite(latest_path, frame)


def _detect_from_gray(profile_name, frame_gray):
    frame_e = cv2.Canny(frame_gray, 80, 160)
    references_dir = get_profile_dirs(profile_name)["references"]

    for ref in os.listdir(references_dir):
        ref_path = os.path.join(references_dir, ref)
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

        GRID = 8
        x = (x // GRID) * GRID
        y = (y // GRID) * GRID

        return ref, (x, y, w, h)

    return None, None


def frame_comp_from_array(profile_name, frame, state):

    if not profile_name or frame is None:
        return False

    profile_valid = os.path.isdir(profile_path(profile_name))

    frame_gray = (
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if frame.ndim == 3 else frame
    )
    now = time.time()
    matched_ref, match_bbox = _detect_from_gray(profile_name, frame_gray)

    if matched_ref is not None:
        state.last_seen_time = now
        event_start = not state.event_active
        if event_start:
            state.event_active = True

        if state.active_dialogue != matched_ref:
            state.active_dialogue = matched_ref

        # Save exactly one debug artifact per detection event.
        if event_start:
            debug = cv2.cvtColor(frame_gray, cv2.COLOR_GRAY2BGR)
            x, y, w, h = match_bbox
            cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 255, 0), 2)

            debug_dir, _ = get_debug_dir(
                profile_name if profile_valid else None,
                allow_fallback=True
            )
            if debug_dir:
                _save_debug_image_if_allowed(debug_dir, debug, state)

        return True

    if state.active_dialogue and now - state.last_seen_time > EXIT_TIMEOUT:
        state.active_dialogue = None
        state.event_active = False
        state.last_debug_frame = None

    return False


def frame_comp(profile_name, state=None):
    """
    File-based detector entrypoint kept for manual/debug workflows.
    Runtime monitoring should use frame_comp_from_array.
    """
    if not profile_name:
        return False

    dirs = get_profile_dirs(profile_name)
    frame_path = os.path.join(dirs["captures"], "latest.png")

    if not os.path.exists(frame_path):
        return False

    frame = cv2.imread(frame_path)
    if frame is None:
        return False

    if state is None:
        state = _default_detector_state
    return frame_comp_from_array(
        profile_name,
        frame,
        state,
    )


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
