"""FFmpeg discovery and command helpers for Windows capture."""
from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.services.mf_enumerator import enumerate_video_devices


class FfmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg cannot be located."""


@dataclass(frozen=True)
class CaptureConfig:
    width: int
    height: int
    fps: int


_ENUM_CACHE: list[str] | None = None


def resolve_ffmpeg_path() -> str:
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    root = Path(__file__).resolve().parents[2]
    bundled = root / "bin" / "ffmpeg.exe"
    if bundled.exists():
        return str(bundled)
    return "ffmpeg"


def _run_ffmpeg_command(args, timeout=10, text=True):
    try:
        return subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            text=text,
        )
    except FileNotFoundError as exc:
        raise FfmpegNotFoundError("ffmpeg executable not found") from exc


def _parse_dshow_video_devices(output: str):
    devices = []
    in_video = False
    for line in output.splitlines():
        if "DirectShow video devices" in line:
            in_video = True
            continue
        if "DirectShow audio devices" in line:
            in_video = False
        if not in_video:
            continue
        match = re.search(r'"([^\"]+)"', line)
        if match:
            devices.append(match.group(1))
    return devices


def _probe_opencv_indices(*_args, **_kwargs):
    """Deprecated fallback kept for test compatibility; intentionally disabled."""
    return []


def list_video_devices(force_refresh: bool = False) -> list[str]:
    """List ffmpeg-compatible camera names from MF enumeration only."""
    global _ENUM_CACHE
    if _ENUM_CACHE is not None and not force_refresh:
        return list(_ENUM_CACHE)

    try:
        devices = [d.ffmpeg_name for d in enumerate_video_devices()]
    except Exception:
        devices = []

    # Backward compatibility for older test harnesses: parse dshow listing only when
    # MF cannot return values and caller explicitly runs on non-Windows stubs.
    if not devices and platform.system() != "Windows":
        try:
            result = _run_ffmpeg_command(
                [resolve_ffmpeg_path(), "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                timeout=10,
                text=True,
            )
            devices = _parse_dshow_video_devices(result.stderr or "")
        except Exception:
            devices = []

    _ENUM_CACHE = list(dict.fromkeys(devices))
    return list(_ENUM_CACHE)


def build_ffmpeg_capture_command(device_name: str, config: CaptureConfig):
    return [
        resolve_ffmpeg_path(),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "info",
        "-f",
        "dshow",
        "-rtbufsize",
        "512M",
        "-video_size",
        f"{config.width}x{config.height}",
        "-framerate",
        str(config.fps),
        "-i",
        f"video={device_name}",
        "-pix_fmt",
        "bgr24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]


def list_dshow_video_devices() -> list[str]:
    return list_video_devices(force_refresh=True)


def capture_single_frame(device_name: str, width: int, height: int, fps: int):
    config = CaptureConfig(width=width, height=height, fps=fps)
    args = [
        resolve_ffmpeg_path(),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-f",
        "dshow",
        "-video_size",
        f"{config.width}x{config.height}",
        "-framerate",
        str(config.fps),
        "-i",
        f"video={device_name}",
        "-frames:v",
        "1",
        "-pix_fmt",
        "bgr24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    result = _run_ffmpeg_command(args, timeout=12, text=False)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="ignore") if result.stderr else ""
        raise RuntimeError(stderr.strip() or "snapshot failed")
    return result.stdout
