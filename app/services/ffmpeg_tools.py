"""FFmpeg discovery and command helpers for camera capture."""
from __future__ import annotations

import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.services.camera_enumerator import CameraDevice, enumerate_video_devices

LOG = logging.getLogger(__name__)


class FfmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg cannot be located."""


@dataclass(frozen=True)
class CaptureConfig:
    width: int
    height: int
    fps: int


_ENUM_CACHE: list[CameraDevice] | None = None


def _normalize_camera_device(device: CameraDevice | str) -> CameraDevice:
    if isinstance(device, CameraDevice):
        return device
    name = str(device)
    token = f"video={name}"
    return CameraDevice(display_name=name, ffmpeg_token=token)


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


def _probe_opencv_indices(*_args, **_kwargs):
    """Deprecated fallback kept for test compatibility; intentionally disabled."""
    return []


def list_camera_devices(force_refresh: bool = False) -> list[CameraDevice]:
    global _ENUM_CACHE
    if _ENUM_CACHE is not None and not force_refresh:
        return [_normalize_camera_device(d) for d in _ENUM_CACHE]

    ffmpeg_path = resolve_ffmpeg_path()
    devices = enumerate_video_devices(ffmpeg_path=ffmpeg_path)

    if not devices and platform.system() != "Windows" and ffmpeg_path != "ffmpeg":
        devices = enumerate_video_devices(ffmpeg_path="ffmpeg")

    deduped: list[CameraDevice] = []
    seen: set[str] = set()
    for raw_device in devices:
        device = _normalize_camera_device(raw_device)
        key = device.display_name.casefold()
        if key in seen:
            continue
        deduped.append(device)
        seen.add(key)

    _ENUM_CACHE = deduped
    LOG.info("[CAM_ENUM] cached camera devices: %s", _ENUM_CACHE)
    return list(_ENUM_CACHE)


def list_video_devices(force_refresh: bool = False) -> list[str]:
    """List display names for backwards compatibility with existing UI callers."""
    return [d.display_name for d in list_camera_devices(force_refresh=force_refresh)]


def resolve_camera_device_token(selected_display_name: str, force_refresh: bool = False) -> str | None:
    if not selected_display_name:
        LOG.warning("[CAM_CAPTURE] selected display name is empty")
        return None

    devices = list_camera_devices(force_refresh=force_refresh)
    names = [d.display_name for d in devices]
    LOG.info("[CAM_CAPTURE] resolve selected device display_name=%r available=%s", selected_display_name, names)

    for device in devices:
        if device.display_name.casefold() == selected_display_name.casefold():
            LOG.info("[CAM_CAPTURE] resolved token for %r -> %r", selected_display_name, device.ffmpeg_token)
            return device.ffmpeg_token

    LOG.warning("[CAM_CAPTURE] selected device %r is not present in enumerated devices", selected_display_name)
    return None


def build_ffmpeg_capture_command(input_token: str, config: CaptureConfig):
    cmd = [
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
        input_token,
        "-pix_fmt",
        "bgr24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    LOG.info("[CAM_CAPTURE] ffmpeg command: %s", cmd)
    return cmd


def list_dshow_video_devices() -> list[str]:
    return list_video_devices(force_refresh=True)


def capture_single_frame(device_name: str, width: int, height: int, fps: int):
    token = resolve_camera_device_token(device_name, force_refresh=True)
    if not token:
        raise RuntimeError(f"camera '{device_name}' not found in enumerated ffmpeg devices")

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
        token,
        "-frames:v",
        "1",
        "-pix_fmt",
        "bgr24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    LOG.info("[CAM_CAPTURE] snapshot command: %s", args)
    result = _run_ffmpeg_command(args, timeout=12, text=False)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="ignore") if result.stderr else ""
        raise RuntimeError(stderr.strip() or "snapshot failed")
    return result.stdout
