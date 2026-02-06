import logging
import time
import cv2

from PyQt6.QtCore import QThread, pyqtSignal

from core import detector as dect
from core import notifier as notif
from core.profiles import (
    get_profile_camera_index,
    get_profile_dirs,
    has_profile_camera_index,
    set_profile_camera_index,
)
from app.app_state import app_state


class MonitorService(QThread):
    status = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.detector_state = dect.new_detector_state()

    def _list_available_camera_indices(self, max_devices=10):
        # Probing indices may briefly activate physical cameras as OpenCV opens each device.
        available = []
        for index in range(max_devices):
            cap = cv2.VideoCapture(index)
            try:
                if cap.isOpened():
                    available.append(index)
            finally:
                cap.release()
        return available

    def list_available_camera_indices(self, max_devices=10):
        return self._list_available_camera_indices(max_devices=max_devices)

    def run(self):
        profile = app_state.active_profile
        if not profile:
            self.status.emit("No profile selected")
            return

        app_state.monitoring_active = True
        self.running = True
        self.status.emit("Monitoring...")
        self.detector_state = dect.new_detector_state()

        get_profile_dirs(profile)
        camera_index = get_profile_camera_index(profile)
        if not has_profile_camera_index(profile):
            available = self._list_available_camera_indices()
            if available:
                camera_index = available[0]
                set_profile_camera_index(profile, camera_index)

        cap = None
        try:
            cap = cv2.VideoCapture(camera_index)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

            if not cap.isOpened():
                self.status.emit(f"Camera failed ({camera_index}). Select another camera index.")
                return
            logging.info("Using camera index %s", camera_index)

            while self.running:
                ret, frame = cap.read()
                if not ret:
                    continue

                try:
                    if dect.frame_comp_from_array(
                        profile,
                        frame,
                        self.detector_state,
                    ):
                        self.status.emit("Dialogue detected!")
                        try:
                            notif.alert()
                        except Exception:
                            logging.error("Alert backend failure", exc_info=True)
                except Exception:
                    logging.error("Detection crash", exc_info=True)
                    continue

                time.sleep(0.05)
        finally:
            if cap is not None:
                cap.release()
            self.running = False
            app_state.monitoring_active = False
            self.status.emit("Stopped")

    def stop(self):
        self.running = False
        app_state.monitoring_active = False
