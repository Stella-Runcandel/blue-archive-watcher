"""Visual detection engine for FrameTrace.

Uses OpenCV edge-based template matching to detect user-defined references
in camera frames. Detection flow: grayscale -> Canny edges -> matchTemplate
with TM_CCOEFF_NORMED. Debug images are written on detection events, with
global bounded storage enforcement.
"""
import cv2
import logging
import os
import time
from dataclasses import dataclass

from app.services.capture_constants import CANONICAL_HEIGHT, CANONICAL_WIDTH
from core.profiles import (
    DEBUG_EXTENSIONS,
    get_profile_dirs,
    get_debug_dir,
    profile_path,
    get_detection_threshold,
)
from core import storage

EXIT_TIMEOUT = 0.6  # seconds dialogue must disappear to reset
DEBUG_STORAGE_LIMIT_BYTES = 1_073_741_824  # 1 GB
DEBUG_STORAGE_LIMIT_COUNT = 2000


# =========================
# Detector state
# =========================

@dataclass
class DetectorState:
    active_dialogue: str | None = None
    event_active: bool = False
    last_seen_time: float = 0.0
    last_debug_frame: object = None
    debug_counter: int = 0
    debug_limit_warning_emitted: bool = False
    total_debug_storage_bytes: int = 0


@dataclass(frozen=True)
class DetectionResult:
    matched: bool
    confidence: float
    reference: str | None
    timestamp: float
    event_start: bool = False
    debug_frame: object = None


# =========================
# Debug storage accounting
# =========================

def _compute_initial_debug_storage_bytes():
    debug_dir = get_debug_dir()
    total = 0
    try:
        names = os.listdir(debug_dir)
    except Exception:
        return 0
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


def initialize_debug_storage_tracking(state: DetectorState):
    """Initialize debug storage accounting at startup."""
    try:
        state.total_debug_storage_bytes = _compute_initial_debug_storage_bytes()
    except Exception:
        logging.warning(
            "Failed to initialize debug storage accounting; disabling debug writes.",
            exc_info=True,
        )
        state.total_debug_storage_bytes = DEBUG_STORAGE_LIMIT_BYTES


def _emit_debug_limit_warning_once(state: DetectorState):
    """Emit a warning once when debug storage bounds are exceeded."""
    if state.debug_limit_warning_emitted:
        return
    logging.warning(
        "Debug storage limit reached (1 GB). "
        "Debug images are paused. Monitoring continues normally."
    )
    state.debug_limit_warning_emitted = True


def _save_debug_image_if_allowed(debug_dir, debug_image, state: DetectorState, profile_name: str, reference_name: str):
    """Persist debug image and enforce global bounds."""
    try:
        state.debug_counter += 1
        debug_path = os.path.join(
            debug_dir,
            f"match_{time.time_ns()}_{state.debug_counter:04d}.png"
        )

        if not cv2.imwrite(debug_path, debug_image):
            logging.warning("Failed to write debug image; continuing monitoring.")
            return

        try:
            size_bytes = os.path.getsize(debug_path)
        except Exception:
            size_bytes = 0
        storage.add_debug_entry(profile_name, reference_name, debug_path, size_bytes)
        for path in storage.prune_debug_entries(DEBUG_STORAGE_LIMIT_BYTES, DEBUG_STORAGE_LIMIT_COUNT):
            try:
                os.remove(path)
            except Exception:
                logging.warning("Failed to prune debug image %s", path, exc_info=True)
        state.total_debug_storage_bytes = _compute_initial_debug_storage_bytes()

        state.last_debug_frame = debug_image

    except Exception:
        logging.warning(
            "Failed to write debug image; continuing monitoring.",
            exc_info=True,
        )


# =========================
# Detector lifecycle
# =========================

def new_detector_state():
    """Create a new detector state instance."""
    state = DetectorState()
    initialize_debug_storage_tracking(state)
    return state


_default_detector_state = new_detector_state()


# =========================
# Reference selection
# =========================

def reference_selector(profile_name):
    """Open an ROI dialog to crop a reference from the first base frame. Returns (success, message)."""
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
    if orig_w <= 0 or orig_h <= 0:
        return False, "Base frame has invalid dimensions"
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
    existing = [f for f in os.listdir(ref_dir) if f.lower().endswith(".png")]
    ref_path = os.path.join(ref_dir, f"ref_{len(existing) + 1}.png")

    cv2.imwrite(ref_path, crop)
    storage.add_reference(profile_name, os.path.basename(ref_path), ref_path, base_frames[0])
    cv2.destroyAllWindows()
    return True, f"Reference saved as {os.path.basename(ref_path)}"


# =========================
# Detection core
# =========================

def _find_best_match(profile_name, frame_gray, selected_reference: str | None = None):
    """Return best matching reference and confidence score for a frame."""
    frame_e = cv2.Canny(frame_gray, 80, 160)
    references_dir = get_profile_dirs(profile_name)["references"]

    refs_to_check = (
        [selected_reference]
        if selected_reference
        else [f for f in os.listdir(references_dir) if f.lower().endswith(".png")]
    )
    best_ref = None
    best_bbox = None
    best_score = 0.0
    for ref in refs_to_check:
        if not ref.lower().endswith(".png"):
            continue
        ref_path = os.path.join(references_dir, ref)
        template = cv2.imread(ref_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            continue

        template_e = cv2.Canny(template, 80, 160)
        tw, th = template_e.shape[1], template_e.shape[0]
        fw, fh = frame_e.shape[1], frame_e.shape[0]
        if tw > fw or th > fh:
            continue
        result = cv2.matchTemplate(frame_e, template_e, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_score:
            x, y = max_loc
            h, w = template_e.shape[:2]
            GRID = 8
            x = (x // GRID) * GRID
            y = (y // GRID) * GRID
            best_ref = ref
            best_bbox = (x, y, w, h)
            best_score = max_val

    if best_ref and best_score >= get_detection_threshold(profile_name):
        return best_ref, best_bbox, best_score

    return None, None, best_score


def evaluate_frame(profile_name, frame, state: DetectorState, selected_reference: str | None = None):
    """Evaluate a frame deterministically and return match metadata."""
    if not profile_name or frame is None:
        return DetectionResult(False, 0.0, None, time.time())

    profile_valid = os.path.isdir(profile_path(profile_name))

    frame_gray = (
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if frame.ndim == 3 else frame
    )

    now = time.time()
    expected_h, expected_w = CANONICAL_HEIGHT, CANONICAL_WIDTH
    if frame_gray.shape[:2] != (expected_h, expected_w):
        frame_gray = cv2.resize(frame_gray, (expected_w, expected_h), interpolation=cv2.INTER_AREA)

    # ROI HOOK — crop here after canonical resize if ROI is configured
    roi = None
    try:
        roi_x = storage.get_app_state(f"{profile_name}:roi_x")
        roi_y = storage.get_app_state(f"{profile_name}:roi_y")
        roi_w = storage.get_app_state(f"{profile_name}:roi_w")
        roi_h = storage.get_app_state(f"{profile_name}:roi_h")
        if None not in (roi_x, roi_y, roi_w, roi_h):
            roi_x = int(roi_x)
            roi_y = int(roi_y)
            roi_w = int(roi_w)
            roi_h = int(roi_h)
            if roi_w >= 10 and roi_h >= 10:
                x0 = max(0, min(roi_x, CANONICAL_WIDTH - 1))
                y0 = max(0, min(roi_y, CANONICAL_HEIGHT - 1))
                x1 = max(x0 + 1, min(roi_x + roi_w, CANONICAL_WIDTH))
                y1 = max(y0 + 1, min(roi_y + roi_h, CANONICAL_HEIGHT))
                clamped_w = x1 - x0
                clamped_h = y1 - y0
                if clamped_w >= 10 and clamped_h >= 10:
                    roi = (x0, y0, clamped_w, clamped_h)
    except Exception:
        roi = None

    processed_frame = frame_gray
    if roi is not None:
        roi_x, roi_y, roi_w, roi_h = roi
        processed_frame = frame_gray[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

    matched_ref, match_bbox, confidence = _find_best_match(
        profile_name,
        processed_frame,
        selected_reference,
    )
    if match_bbox is not None and roi is not None:
        roi_x, roi_y, _, _ = roi
        x, y, w, h = match_bbox
        match_bbox = (x + roi_x, y + roi_y, w, h)

    if matched_ref is not None:
        state.last_seen_time = now
        event_start = not state.event_active

        if event_start:
            state.event_active = True

        if state.active_dialogue != matched_ref:
            state.active_dialogue = matched_ref

        if event_start:
            debug = cv2.cvtColor(frame_gray, cv2.COLOR_GRAY2BGR)
            if roi is not None:
                roi_x, roi_y, roi_w, roi_h = roi
                cv2.rectangle(debug, (roi_x, roi_y), (roi_x + roi_w, roi_y + roi_h), (96, 96, 96), 1)
            x, y, w, h = match_bbox
            cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 255, 0), 2)

            debug_dir = get_debug_dir()
            if debug_dir:
                _save_debug_image_if_allowed(
                    debug_dir,
                    debug,
                    state,
                    profile_name if profile_valid else None,
                    matched_ref,
                )

        debug_flash = None
        if event_start:
            debug_flash = debug.copy()
        return DetectionResult(True, float(confidence), matched_ref, now, event_start=event_start, debug_frame=debug_flash)

    if state.active_dialogue and now - state.last_seen_time > EXIT_TIMEOUT:
        state.active_dialogue = None
        state.event_active = False
        state.last_debug_frame = None

    return DetectionResult(False, float(confidence), None, now)


def frame_comp_from_array(profile_name, frame, state: DetectorState, selected_reference: str | None = None):
    """Run detection on an in-memory frame. When selected_reference is set, only that reference
    is matched; otherwise all references are checked. Returns True if a match is found."""
    result = evaluate_frame(profile_name, frame, state, selected_reference=selected_reference)
    return result.matched


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

    return frame_comp_from_array(profile_name, frame, state)
