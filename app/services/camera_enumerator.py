"""FFmpeg-based camera enumeration helpers for PyQt-safe device discovery."""
from __future__ import annotations

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


def _camera_debug_enabled() -> bool:
    return os.environ.get("CAMERA_DEBUG", "").strip() in {"1", "true", "TRUE", "yes", "on"}


def _append_camera_debug_log(section: str, payload: str) -> None:
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


def _parse_dshow_video_devices(output: str) -> list[str]:
    devices: list[str] = []
    in_video_section = False

    for line in output.splitlines():
        if "DirectShow video devices" in line:
            in_video_section = True
            continue
        if "DirectShow audio devices" in line:
            in_video_section = False
        if not in_video_section:
            continue

        if "Alternative name" in line:
            continue

        match = re.search(r'"([^\"]+)"', line)
        if match:
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


def _names_to_camera_devices(names: Iterable[str], backend: str) -> list[CameraDevice]:
    devices: list[CameraDevice] = []
    for name in names:
        if backend == "dshow":
            token = f"video={name}"
        elif backend == "avfoundation":
            token = name
        else:
            token = name
        devices.append(CameraDevice(display_name=name, ffmpeg_token=token))
    return devices


def enumerate_video_devices(ffmpeg_path: str = "ffmpeg") -> list[CameraDevice]:
    """Return FFmpeg-friendly camera descriptors without opening camera streams."""
    system = platform.system()
    backend = "dshow" if system == "Windows" else "avfoundation" if system == "Darwin" else "v4l2"
    try:
        if system == "Windows":
            cmd = [
                ffmpeg_path,
                "-hide_banner",
                "-list_devices",
                "true",
                "-f",
                "dshow",
                "-i",
                "dummy",
            ]
            LOG.info("[CAM_ENUM] platform=%s ffmpeg_path=%s backend=%s", system, ffmpeg_path, backend)
            LOG.info("[CAM_ENUM] ffmpeg cmd: %s", cmd)
            result = _run_ffmpeg(cmd)
            raw_output = (result.stderr or "") + "\n" + (result.stdout or "")
            LOG.info("[CAM_ENUM] ffmpeg exit=%s", result.returncode)
            LOG.info("[CAM_ENUM] raw stderr:\n%s", result.stderr or "")
            LOG.info("[CAM_ENUM] raw stdout:\n%s", result.stdout or "")
            _append_camera_debug_log("CAM_ENUM_CMD", " ".join(cmd))
            _append_camera_debug_log("CAM_ENUM_STDERR", result.stderr or "")
            _append_camera_debug_log("CAM_ENUM_STDOUT", result.stdout or "")
            parsed = _parse_dshow_video_devices(raw_output)
            LOG.info("[CAM_ENUM] parsed devices (pre-dedupe): %s", parsed)
            validated = _reject_invalid_windows_names(parsed)
            deduped = _dedupe(validated)
            LOG.info("[CAM_ENUM] parsed devices (post-dedupe): %s", deduped)
            devices = _names_to_camera_devices(deduped, backend="dshow")
            LOG.info("[CAM_ENUM] camera descriptors: %s", devices)
            return devices

        if system == "Darwin":
            cmd = [
                ffmpeg_path,
                "-hide_banner",
                "-f",
                "avfoundation",
                "-list_devices",
                "true",
                "-i",
                "",
            ]
            LOG.info("[CAM_ENUM] platform=%s ffmpeg_path=%s backend=%s", system, ffmpeg_path, backend)
            LOG.info("[CAM_ENUM] ffmpeg cmd: %s", cmd)
            result = _run_ffmpeg(cmd)
            raw_output = (result.stderr or "") + "\n" + (result.stdout or "")
            LOG.info("[CAM_ENUM] raw stderr:\n%s", result.stderr or "")
            LOG.info("[CAM_ENUM] raw stdout:\n%s", result.stdout or "")
            parsed = _parse_avfoundation_video_devices(raw_output)
            LOG.info("[CAM_ENUM] parsed devices (pre-dedupe): %s", parsed)
            deduped = _dedupe(parsed)
            LOG.info("[CAM_ENUM] parsed devices (post-dedupe): %s", deduped)
            return _names_to_camera_devices(deduped, backend="avfoundation")

        cmd = [ffmpeg_path, "-hide_banner", "-sources", "v4l2"]
        LOG.info("[CAM_ENUM] platform=%s ffmpeg_path=%s backend=%s", system, ffmpeg_path, backend)
        LOG.info("[CAM_ENUM] ffmpeg cmd: %s", cmd)
        result = _run_ffmpeg(cmd)
        raw_output = (result.stderr or "") + "\n" + (result.stdout or "")
        LOG.info("[CAM_ENUM] raw stderr:\n%s", result.stderr or "")
        LOG.info("[CAM_ENUM] raw stdout:\n%s", result.stdout or "")
        parsed = _parse_v4l2_sources(raw_output)
        LOG.info("[CAM_ENUM] parsed devices (pre-dedupe): %s", parsed)
        deduped = _dedupe(parsed)
        LOG.info("[CAM_ENUM] parsed devices (post-dedupe): %s", deduped)
        return _names_to_camera_devices(deduped, backend="v4l2")
    except Exception:
        LOG.error("[CAM_ENUM] enumeration failed", exc_info=True)
        return []
