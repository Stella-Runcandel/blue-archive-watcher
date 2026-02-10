"""Camera device models and conversion helpers for Windows capture stack."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CameraDevice:
    """Stable camera descriptor shared between UI, config, and capture layers.

    Attributes:
        id: Media Foundation symbolic link (stable device identifier).
        display_name: Human-friendly camera name shown in UI.
        ffmpeg_name: DirectShow-compatible friendly name used by FFmpeg.
    """

    id: str
    display_name: str
    ffmpeg_name: str


def mf_to_ffmpeg_name(display_name: str) -> str:
    """Convert an MF display name to a DirectShow FFmpeg input token.

    DirectShow accepts the friendly name quoted in `-i video="..."`. Keeping this
    utility central prevents accidental index-based names from entering config.
    """

    return (display_name or "").strip()
