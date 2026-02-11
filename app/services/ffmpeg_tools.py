"""FFmpeg discovery and command helpers for camera capture."""
from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.services.camera_enumerator import CameraDevice, append_camera_debug_log, enumerate_video_devices

LOG = logging.getLogger(__name__)


def ffmpeg_debug_enabled() -> bool:
    """Enable verbose ffmpeg logs only when explicitly requested."""
    return os.environ.get("FFMPEG_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


class FfmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg cannot be located."""


@dataclass(frozen=True)
class CaptureConfig:
    width: int
    height: int
    fps: int
    input_width: int | None = None
    input_height: int | None = None
    input_fps: int | None = None
    label: str = "requested"


@dataclass(frozen=True)
class CaptureInputCandidate:
    token: str
    reason: str
    is_virtual: bool


_ENUM_CACHE: list[CameraDevice] | None = None


def _normalize_camera_device(device: CameraDevice | str) -> CameraDevice:
    if isinstance(device, CameraDevice):
        return device
    name = str(device)
    token = f"video={name}"
    return CameraDevice(display_name=name, ffmpeg_token=token, backend="dshow", is_virtual=False)


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
    append_camera_debug_log("CAM_ENUM_CACHE", json.dumps([d.__dict__ for d in _ENUM_CACHE], ensure_ascii=False, indent=2))
    return list(_ENUM_CACHE)


def list_video_devices(force_refresh: bool = False) -> list[str]:
    """List display names for backwards compatibility with existing UI callers."""
    return [d.display_name for d in list_camera_devices(force_refresh=force_refresh)]


def _find_camera_device(selected_display_name: str, force_refresh: bool = False) -> CameraDevice | None:
    devices = list_camera_devices(force_refresh=force_refresh)
    for device in devices:
        if device.display_name.casefold() == selected_display_name.casefold():
            return device
    return None


def build_capture_input_candidates(selected_display_name: str, force_refresh: bool = False) -> list[CaptureInputCandidate]:
    device = _find_camera_device(selected_display_name, force_refresh=force_refresh)
    if not device:
        return []

    candidate = CaptureInputCandidate(device.ffmpeg_token, "exact-enumerated-token", is_virtual=device.is_virtual)
    append_camera_debug_log("CAM_CAPTURE_CANDIDATE", json.dumps(candidate.__dict__, ensure_ascii=False, indent=2))
    return [candidate]


def verify_windows_dshow_device_token(input_token: str, timeout: int = 8) -> tuple[bool, str]:
    if platform.system() != "Windows":
        return True, "non-windows"

    args = [resolve_ffmpeg_path(), "-hide_banner", "-f", "dshow", "-i", input_token, "-t", "0.2", "-f", "null", "-"]
    append_camera_debug_log("CAM_VERIFY_CMD", " ".join(args))
    try:
        result = _run_ffmpeg_command(args, timeout=timeout, text=True)
    except Exception as exc:
        return False, str(exc)

    stderr = result.stderr or ""
    append_camera_debug_log("CAM_VERIFY_STDERR", stderr)
    lowered = stderr.lower()
    fail_tokens = ("could not find video device", "error opening input", "i/o error")
    if any(token in lowered for token in fail_tokens):
        return False, stderr.strip() or "verification failed"
    return True, stderr.strip() or "ok"


def resolve_camera_device_token(selected_display_name: str, force_refresh: bool = False) -> str | None:
    if not selected_display_name:
        LOG.warning("[CAM_CAPTURE] selected display name is empty")
        return None

    device = _find_camera_device(selected_display_name, force_refresh=force_refresh)
    devices = list_camera_devices(force_refresh=False)
    names = [d.display_name for d in devices]
    LOG.info("[CAM_CAPTURE] resolve selected device display_name=%r available=%s", selected_display_name, names)

    if device:
        LOG.info("[CAM_CAPTURE] resolved token for %r -> %r", selected_display_name, device.ffmpeg_token)
        append_camera_debug_log(
            "CAM_CAPTURE_TOKEN_RESOLVE",
            json.dumps(
                {
                    "selected_display_name": selected_display_name,
                    "resolved_token": device.ffmpeg_token,
                    "backend": device.backend,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        return device.ffmpeg_token

    LOG.warning("[CAM_CAPTURE] selected device %r is not present in enumerated devices", selected_display_name)
    append_camera_debug_log("CAM_CAPTURE_TOKEN_RESOLVE", f"MISSING selected={selected_display_name!r} available={names!r}")
    return None


def build_ffmpeg_capture_command(
    input_token: str,
    config: CaptureConfig,
    *,
    allow_input_tuning: bool = True,
    pipeline: str = "monitoring",
):
    ffmpeg_loglevel = "verbose" if ffmpeg_debug_enabled() else "warning"
    cmd = [
        resolve_ffmpeg_path(),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        ffmpeg_loglevel,
        "-f",
        "dshow",
        "-rtbufsize",
        "64M",
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
    ]
    if pipeline == "preview":
        cmd.extend(["-thread_queue_size", "512"])
    if allow_input_tuning and config.input_width is not None and config.input_height is not None:
        cmd.extend(["-video_size", f"{config.input_width}x{config.input_height}"])
    if allow_input_tuning and config.input_fps is not None:
        cmd.extend(["-framerate", str(config.input_fps)])

    cmd.extend(["-i", input_token])
    cmd.extend(["-vf", f"scale={config.width}:{config.height}:flags=fast_bilinear"])
    cmd.extend([
        "-r",
        str(config.fps),
        "-pix_fmt",
        "bgr24",
        "-f",
        "rawvideo",
        "pipe:1",
    ])
    LOG.info("[CAM_CAPTURE] ffmpeg command: %s", cmd)
    append_camera_debug_log("CAM_CAPTURE_CMD", " ".join(cmd))
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
    append_camera_debug_log("CAM_CAPTURE_SNAPSHOT_CMD", " ".join(args))
    result = _run_ffmpeg_command(args, timeout=12, text=False)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="ignore") if result.stderr else ""
        append_camera_debug_log("CAM_CAPTURE_SNAPSHOT_STDERR", stderr)
        raise RuntimeError(stderr.strip() or "snapshot failed")
    return result.stdout


def capture_single_frame_by_token(input_token: str, *, width: int | None = None, height: int | None = None):
    """Capture exactly one raw BGR frame from a resolved dshow token."""
    args = [
        resolve_ffmpeg_path(),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-f",
        "dshow",
        "-i",
        input_token,
    ]
    if width and height:
        args.extend(["-s", f"{int(width)}x{int(height)}"])
    args.extend([
        "-frames:v",
        "1",
        "-pix_fmt",
        "bgr24",
        "-f",
        "rawvideo",
        "pipe:1",
    ])
    LOG.info("[CAM_CAPTURE] one-shot snapshot command: %s", args)
    append_camera_debug_log("CAM_CAPTURE_SNAPSHOT_ONESHOT_CMD", " ".join(args))
    result = _run_ffmpeg_command(args, timeout=10, text=False)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="ignore") if result.stderr else ""
        append_camera_debug_log("CAM_CAPTURE_SNAPSHOT_ONESHOT_STDERR", stderr)
        raise RuntimeError(stderr.strip() or "snapshot failed")
    return result.stdout
