"""Run this after implementing fixes to verify no unwanted highlighting."""

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from app.ui.app_shell import AppShell


def test_widget_focus_policies(widget, path=""):
    """Recursively check all widgets for proper focus policies."""
    issues = []
    widget_name = f"{path}/{widget.__class__.__name__}"

    if isinstance(widget, QLabel):
        if widget.focusPolicy() != Qt.FocusPolicy.NoFocus:
            issues.append(f"{widget_name} - Label has focus enabled")
        if widget.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction:
            issues.append(f"{widget_name} - Label text is selectable")

    for child in widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        issues.extend(test_widget_focus_policies(child, widget_name))

    return issues


if __name__ == "__main__":
    app = QApplication(sys.argv)
    shell = AppShell()

    print("Checking for UI highlighting issues...")
    issues = test_widget_focus_policies(shell)

    if issues:
        print(f"\n❌ Found {len(issues)} issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n✅ No highlighting issues found!")

    sys.exit(0)
