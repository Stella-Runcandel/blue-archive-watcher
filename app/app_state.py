"""In-memory app state with persisted profile selection."""

from core import storage


class AppState:
    """Global UI and monitoring state: active profile, selected frame/reference, monitoring flag."""

    def __init__(self):
        self.active_profile = storage.get_app_state("active_profile")
        self.selected_frame = None
        self.selected_reference = None

        self.monitoring_active = False
        self.live_preview_on = False

        self.nav_stack = ["dashboard"]

app_state = AppState()
