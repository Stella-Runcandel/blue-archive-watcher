from app.app_state import app_state
from core.profiles import delete_reference_files


class ReferenceController:
    def select_reference(self, ref_name):
        """Mutates: selected_reference. Does NOT mutate: monitoring_active. Returns: (bool, str)."""
        if app_state.monitoring_active:
            return False, "Stop monitoring before selecting a reference."
        app_state.selected_reference = ref_name
        return True, "Reference selected."

    def delete_reference(self, ref_name):
        """Mutates: selected_reference. Does NOT mutate: monitoring_active. Returns: (bool, str)."""
        if app_state.monitoring_active:
            return False, "Stop monitoring before deleting a reference."
        if not app_state.active_profile:
            return False, "No profile selected."
        success, message = delete_reference_files(
            app_state.active_profile,
            ref_name
        )
        if not success:
            return False, message
        if app_state.selected_reference == ref_name:
            app_state.selected_reference = None
        return True, message
