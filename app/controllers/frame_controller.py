from app.app_state import app_state
from core.profiles import delete_frame_and_references


class FrameController:
    def select_frame(self, frame_name):
        """Mutates: selected_frame. Does NOT mutate: monitoring_active. Returns: (bool, str)."""
        if app_state.monitoring_active:
            return False, "Stop monitoring before selecting a frame."
        app_state.selected_frame = frame_name
        return True, "Frame selected."

    def delete_frame(self, frame_name):
        """Mutates: selected_frame, selected_reference. Does NOT mutate: monitoring_active. Returns: (bool, str)."""
        if app_state.monitoring_active:
            return False, "Stop monitoring before deleting a frame."
        if not app_state.active_profile:
            return False, "No profile selected."
        success, message, deleted_refs = delete_frame_and_references(
            app_state.active_profile,
            frame_name
        )
        if not success:
            return False, message
        if app_state.selected_frame == frame_name:
            app_state.selected_frame = None
        if app_state.selected_reference in deleted_refs:
            app_state.selected_reference = None
        return True, message
