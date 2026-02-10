"""FFmpeg-first camera enumeration with layered Windows fallbacks."""
from __future__ import annotations

import json
import logging
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraDevice:
    display_name: str
    ffmpeg_token: str
    backend: str
    is_virtual: bool


_VIRTUAL_HINTS = (
    "virtual",
    "obs",
    "broadcast",
    "ndi",
    "splitcam",
    "manycam",
    "vcam",
)


def _camera_debug_enabled() -> bool:
    return os.environ.get("CAMERA_DEBUG", "").strip() in {"1", "true", "TRUE", "yes", "on"}


def append_camera_debug_log(section: str, payload: str) -> None:
    if not _camera_debug_enabled():
        return
    logs_dir = Path("Data") / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "camera_debug.log"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{section}]\n{payload}\n\n")


def _run_ffmpeg(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        text=True,
    )


def _parse_dshow_video_devices(stderr_text: str) -> list[str]:
    """Parse authoritative dshow lines of format: "name" (video)."""
    devices: list[str] = []
    for line in stderr_text.splitlines():
        lowered = line.lower()
        if "alternative name" in lowered:
            continue
        match = re.search(r'"([^"]+)"\s*\(video\)', line, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(1).strip()
        if candidate:
            devices.append(candidate)
    return devices


def _parse_avfoundation_video_devices(output: str) -> list[str]:
    devices: list[str] = []
    in_video_section = False

    for line in output.splitlines():
        if "AVFoundation video devices" in line:
            in_video_section = True
            continue
        if "AVFoundation audio devices" in line:
            in_video_section = False
        if not in_video_section:
            continue

        match = re.search(r"\[[0-9]+\]\s+(.+)$", line.strip())
        if match:
            devices.append(match.group(1).strip())

    return devices


def _parse_v4l2_sources(output: str) -> list[str]:
    devices: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith("*"):
            continue

        match = re.search(r"\*\s+\S+\s+\[(.+)\]", stripped)
        if match:
            devices.append(match.group(1).strip())

    return devices


def _reject_invalid_windows_names(items: Iterable[str]) -> list[str]:
    valid: list[str] = []
    for item in items:
        name = item.strip()
        if not name:
            continue
        if re.fullmatch(r"camera\s*\d+", name, re.IGNORECASE):
            LOG.warning("[CAM_ENUM] rejecting fabricated/placeholder dshow name: %r", name)
            continue
        valid.append(name)
    return valid


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        name = item.strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _is_virtual_camera(name: str) -> bool:
    lowered = name.casefold()
    return any(hint in lowered for hint in _VIRTUAL_HINTS)


def _names_to_camera_devices(names: Iterable[str], backend: str) -> list[CameraDevice]:
    devices: list[CameraDevice] = []
    for name in names:
        token = f"video={name}" if backend == "dshow" else name
        devices.append(
            CameraDevice(
                display_name=name,
                ffmpeg_token=token,
                backend=backend,
                is_virtual=_is_virtual_camera(name),
            )
        )
    return devices


def _enumerate_dshow(ffmpeg_path: str) -> list[str]:
    commands = [
        [ffmpeg_path, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
        [ffmpeg_path, "-loglevel", "verbose", "-f", "dshow", "-list_devices", "true", "-i", "dummy"],
    ]
    collected: list[str] = []
    for index, cmd in enumerate(commands, start=1):
        try:
            result = _run_ffmpeg(cmd)
        except Exception:
            LOG.exception("[CAM_ENUM] dshow ffmpeg invocation failed")
            append_camera_debug_log("CAM_ENUM_DSHOW_ERROR", f"cmd={cmd}")
            continue
        append_camera_debug_log(f"CAM_ENUM_DSHOW_CMD_{index}", " ".join(cmd))
        append_camera_debug_log(f"CAM_ENUM_DSHOW_STDERR_{index}", result.stderr or "")
        append_camera_debug_log(f"CAM_ENUM_DSHOW_STDOUT_{index}", result.stdout or "")
        LOG.info("[CAM_ENUM] dshow cmd #%s exit=%s cmd=%s", index, result.returncode, cmd)
        parsed = _parse_dshow_video_devices(result.stderr or "")
        append_camera_debug_log(f"CAM_ENUM_PARSED_DSHOW_{index}", json.dumps(parsed, ensure_ascii=False, indent=2))
        if parsed:
            collected.extend(parsed)
            break
    return collected


def _probe_opencv_indices(max_index: int = 12) -> list[str]:
    try:
        import cv2
    except Exception:
        return []

    found: list[str] = []
    for index in range(max_index):
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        try:
            if cap is not None and cap.isOpened():
                found.append(f"OpenCV Camera {index}")
        finally:
            if cap is not None:
                cap.release()
    append_camera_debug_log("CAM_ENUM_OPENCV", json.dumps(found, indent=2))
    return found


def enumerate_video_devices(ffmpeg_path: str = "ffmpeg") -> list[CameraDevice]:
    """Enumerate camera devices without opening camera streams.

    Windows order: dshow -> dshow verbose -> OpenCV.
    """
    system = platform.system()
    try:
        if system == "Windows":
            dshow_names = _enumerate_dshow(ffmpeg_path)
            parsed = _dedupe(_reject_invalid_windows_names(dshow_names))
            if parsed:
                devices = _names_to_camera_devices(parsed, backend="dshow")
                append_camera_debug_log("CAM_ENUM_FINAL", json.dumps([d.__dict__ for d in devices], ensure_ascii=False, indent=2))
                return devices

            opencv_names = _probe_opencv_indices()
            if opencv_names:
                devices = _names_to_camera_devices(_dedupe(opencv_names), backend="opencv")
                append_camera_debug_log("CAM_ENUM_FINAL", json.dumps([d.__dict__ for d in devices], ensure_ascii=False, indent=2))
                return devices

            append_camera_debug_log("CAM_ENUM_FINAL", json.dumps([], ensure_ascii=False, indent=2))
            return []

        if system == "Darwin":
            cmd = [ffmpeg_path, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""]
            result = _run_ffmpeg(cmd)
            parsed = _dedupe(_parse_avfoundation_video_devices((result.stderr or "") + "\n" + (result.stdout or "")))
            return _names_to_camera_devices(parsed, backend="avfoundation")

        cmd = [ffmpeg_path, "-hide_banner", "-sources", "v4l2"]
        result = _run_ffmpeg(cmd)
        parsed = _dedupe(_parse_v4l2_sources((result.stderr or "") + "\n" + (result.stdout or "")))
        return _names_to_camera_devices(parsed, backend="v4l2")
    except Exception:
        LOG.error("[CAM_ENUM] enumeration failed", exc_info=True)
        return []
