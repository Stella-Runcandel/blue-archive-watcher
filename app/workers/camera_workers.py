"""Worker threads for FFmpeg device enumeration and snapshot capture."""
import logging

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from app.services.ffmpeg_tools import (
    FfmpegNotFoundError,
    capture_single_frame,
    list_dshow_video_devices,
)


class CameraProbeWorker(QThread):
    """Enumerate DirectShow devices off the UI thread."""
    cameraIndicesReady = pyqtSignal(list)

    def __init__(self, max_devices=10):
        super().__init__()
        self.max_devices = max_devices

    def run(self):
        """Emit device list when enumeration completes."""
        try:
            devices = list_dshow_video_devices()
        except FfmpegNotFoundError as exc:
            logging.error("FFmpeg not found for device enumeration: %s", exc)
            devices = []
        except Exception:
            logging.error("FFmpeg device enumeration failed", exc_info=True)
            devices = []
        self.cameraIndicesReady.emit(devices)


class CameraSnapshotWorker(QThread):
    """Capture a single preview frame via FFmpeg."""
    snapshotReady = pyqtSignal(QImage)
    snapshotFailed = pyqtSignal(str)

    def __init__(self, device_name, width, height, fps):
        super().__init__()
        self.device_name = device_name
        self.width = width
        self.height = height
        self.fps = fps

    def run(self):
        """Emit a QImage snapshot or an error message."""
        if not self.device_name:
            self.snapshotFailed.emit("No camera selected")
            return
        try:
            raw = capture_single_frame(
                self.device_name,
                self.width,
                self.height,
                self.fps,
            )
        except FfmpegNotFoundError as exc:
            self.snapshotFailed.emit(f"FFmpeg not found ({exc})")
            return
        except Exception as exc:
            logging.error("Snapshot capture failed", exc_info=True)
            self.snapshotFailed.emit(f"Snapshot failed ({exc})")
            return

        frame = np.frombuffer(raw, dtype=np.uint8)
        expected = self.width * self.height * 3
        if frame.size != expected:
            self.snapshotFailed.emit("Snapshot size mismatch")
            return

        frame = frame.reshape((self.height, self.width, 3))
        frame = frame[:, :, ::-1]
        image = QImage(
            frame.data,
            self.width,
            self.height,
            self.width * 3,
            QImage.Format.Format_RGB888,
        ).copy()

        self.snapshotReady.emit(image)
