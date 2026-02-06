import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from app.ui.app_shell import AppShell


LIGHT_THEME_STYLESHEET = """
QWidget {
    background-color: #f4f5f7;
    color: #1f2937;
}

QLabel {
    color: #111827;
}

QPushButton {
    background-color: #ffffff;
    color: #111827;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 6px 10px;
}

QPushButton:hover {
    background-color: #f9fafb;
    border-color: #9ca3af;
}

QPushButton:pressed {
    background-color: #e5e7eb;
}

QLineEdit,
QTextEdit,
QPlainTextEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {
    background-color: #ffffff;
    color: #111827;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: #c7d2fe;
    selection-color: #111827;
}

QScrollArea,
QFrame,
QListWidget,
QTreeWidget,
QTableWidget {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 8px;
}

QToolTip {
    background-color: #ffffff;
    color: #111827;
    border: 1px solid #d1d5db;
}
"""


def main():
    QCoreApplication.setOrganizationName("Frame Trace")
    QCoreApplication.setApplicationName("Frame Trace")
    app = QApplication(sys.argv)
    app.setApplicationName("Frame Trace")

    icon_path = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
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
