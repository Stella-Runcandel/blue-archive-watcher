"""FFmpeg-based camera enumeration helpers for PyQt-safe device discovery."""
from __future__ import annotations

import platform
import re
import subprocess
from typing import Iterable


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
            devices.append(match.group(1).strip())

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


def enumerate_video_devices(ffmpeg_path: str = "ffmpeg") -> list[str]:
    """Return FFmpeg-friendly camera names without opening camera streams."""
    system = platform.system()

    try:
        if system == "Windows":
            result = _run_ffmpeg([
                ffmpeg_path,
                "-hide_banner",
                "-list_devices",
                "true",
                "-f",
                "dshow",
                "-i",
                "dummy",
            ])
            return _dedupe(_parse_dshow_video_devices((result.stderr or "") + "\n" + (result.stdout or "")))

        if system == "Darwin":
            result = _run_ffmpeg([
                ffmpeg_path,
                "-hide_banner",
                "-f",
                "avfoundation",
                "-list_devices",
                "true",
                "-i",
                "",
            ])
            return _dedupe(_parse_avfoundation_video_devices((result.stderr or "") + "\n" + (result.stdout or "")))

        # Linux / other UNIX-like fallback via FFmpeg source probing.
        result = _run_ffmpeg([ffmpeg_path, "-hide_banner", "-sources", "v4l2"])
        return _dedupe(_parse_v4l2_sources((result.stderr or "") + "\n" + (result.stdout or "")))
    except Exception:
        return []
