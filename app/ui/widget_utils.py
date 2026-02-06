from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

from app.ui.theme import Styles


def disable_widget_interaction(widget: QWidget):
    """Disable interactive/focus states for display-only widgets."""
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if isinstance(widget, QLabel):
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)


def disable_button_focus_rect(button: QPushButton):
    """Disable focus rectangle on button while keeping it clickable."""
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def make_preview_label(
    text: str = "",
    min_height: int = 220,
    object_name: str = "preview_label",
) -> QLabel:
    """Create a configured preview label with non-interactive behavior."""
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setMinimumHeight(min_height)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    label.setStyleSheet(Styles.preview_label(object_name))
    return label
