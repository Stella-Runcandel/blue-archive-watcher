"""Compatibility wrapper for legacy imports.

Media Foundation enumeration has been removed in favor of FFmpeg-based, non-COM
enumeration. Import and call :func:`app.services.camera_enumerator.enumerate_video_devices`
directly in new code.
"""
from __future__ import annotations

from app.services.camera_enumerator import enumerate_video_devices

__all__ = ["enumerate_video_devices"]
