import time
import cv2
import os

from PyQt6.QtCore import QThread, pyqtSignal

from core import detector as dect
from core import notifier as notif
from core.profiles import get_profile_dirs
from app.app_state import app_state


class MonitorService(QThread):
    status = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False

    def run(self):
        profile = app_state.active_profile
        if not profile:
            self.status.emit("No profile selected")
            return

        app_state.monitoring_active = True
        self.running = True
        self.status.emit("Monitoring...")

        dirs = get_profile_dirs(profile)
        capture_path = os.path.join(dirs["captures"], "latest.png")

        cap = cv2.VideoCapture(2, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

        try:
            if not cap.isOpened():
                self.status.emit("Camera failed")
                return

            while self.running:
                ret, frame = cap.read()
                if not ret:
                    continue

                cv2.imwrite(capture_path, frame)

                if dect.frame_comp(profile):
                    self.status.emit("Dialogue detected!")
                    notif.alert()

                time.sleep(0.05)
        finally:
            cap.release()
            self.running = False
            app_state.monitoring_active = False
            self.status.emit("Stopped")

    def stop(self):
        self.running = False
        app_state.monitoring_active = False
