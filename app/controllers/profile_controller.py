from app.app_state import app_state
from core.profiles import (
    create_profile,
    delete_profile,
    list_profiles,
    set_profile_icon,
)


class ProfileController:    
    def list_profiles(self):
        """
        Mutates: none.
        Does NOT mutate: app_state.
        Returns: (bool, list[str], str)
        """
        profiles = list_profiles()
        return True, profiles, "Profiles loaded"


    def select_profile(self, name):
        """Mutates: active_profile, selected_frame, selected_reference. Does NOT mutate: monitoring_active. Returns: (bool, str)."""
        if app_state.monitoring_active:
            return False, "Stop monitoring before changing profiles."
        app_state.active_profile = name
        app_state.selected_frame = None
        app_state.selected_reference = None
        return True, "Profile selected."

    def create_profile(self, name):
        """Mutates: active_profile, selected_frame, selected_reference. Does NOT mutate: monitoring_active. Returns: (bool, str)."""
        success, message = create_profile(name)
        if not success:
            return False, message
        app_state.active_profile = name
        app_state.selected_frame = None
        app_state.selected_reference = None
        return True, message

    def delete_profile(self, name):
        """Mutates: none. Does NOT mutate: app_state. Returns: (bool, str)."""
        if app_state.monitoring_active:
            return False, "Stop monitoring before deleting a profile."
        if app_state.active_profile == name:
            return False, "You cannot delete the active profile."
        success, message = delete_profile(name)
        return success, message

    def set_profile_icon(self, name, source_path):
        """Mutates: profile metadata. Does NOT mutate: app_state. Returns: (bool, str)."""
        if app_state.monitoring_active:
            return False, "Stop monitoring before changing profile icons."
        return set_profile_icon(name, source_path)
