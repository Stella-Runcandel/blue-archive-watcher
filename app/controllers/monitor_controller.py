import logging

from app.app_state import app_state


class MonitorController:
    def __init__(self, monitor_service):
        self.monitor = monitor_service

    def start(self):
        if not app_state.active_profile:
            return "No profile selected"

        if self.monitor.isRunning():
            return "Already monitoring"

        self.monitor.start()
        return "Monitoring start requested"

    def stop(self):
        if not self.monitor.isRunning():
            return "Not monitoring"

        self.monitor.stop()
        if not self.monitor.wait(5000):
            logging.warning("Monitor thread did not exit within 5 seconds")
        app_state.monitoring_active = False
        return "Monitoring stop requested"
