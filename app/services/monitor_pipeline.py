"""Backward-compatible exports for capture pipeline primitives."""

from app.services.ffmpeg_capture_supervisor import FfmpegCaptureSupervisor as FfmpegCapture
from app.services.frame_bus import FrameQueue

__all__ = ["FrameQueue", "FfmpegCapture"]
