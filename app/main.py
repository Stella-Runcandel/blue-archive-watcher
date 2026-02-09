"""Application entrypoint for Frame Trace."""
import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from app.ui.app_shell import AppShell
from core.logging_setup import setup_logging


LIGHT_THEME_STYLESHEET = """
QWidget {
    background-color: #ffffff;
    color: #111111;
}

QLabel {
    background-color: transparent;
    color: #111111;
    selection-background-color: transparent;
    selection-color: #111111;
}

QLabel:focus {
    outline: none;
}

QPushButton {
    background-color: #ffffff;
    color: #111111;
    border: 1px solid #d6d6d6;
    border-radius: 8px;
    padding: 6px 10px;
    outline: none;
}

QPushButton:hover {
    background-color: #f7f7f7;
    border-color: #cdcdcd;
}

QPushButton:pressed {
    background-color: #eeeeee;
    border-color: #c6c6c6;
}

QPushButton:focus {
    outline: none;
    border: 1px solid #d6d6d6;
}

QLabel[objectName="preview_label"],
QLabel[objectName="profile_preview"] {
    background-color: transparent;
    selection-background-color: transparent;
}

QLineEdit,
QTextEdit,
QPlainTextEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox,
QDateEdit,
QDateTimeEdit,
QTimeEdit {
    background-color: #ffffff;
    color: #111111;
    border: 1px solid #d6d6d6;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: #e6e6e6;
    selection-color: #111111;
}

QScrollArea {
    background-color: #ffffff;
    border: 1px solid #d6d6d6;
    border-radius: 8px;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}
"""


def main():
    setup_logging()
    QCoreApplication.setOrganizationName("Frame Trace")
    QCoreApplication.setApplicationName("Frame Trace")
    app = QApplication(sys.argv)
    app.setApplicationName("Frame Trace")

    icon_path = Path(__file__).resolve().parent.parent / "Assets" / "app_icon.png"
    app_icon = QIcon(str(icon_path))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    app.setStyleSheet(LIGHT_THEME_STYLESHEET)

    shell = AppShell()
    if not app_icon.isNull():
        shell.setWindowIcon(app_icon)
    shell.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
