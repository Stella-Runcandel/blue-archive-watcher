class Colors:
    """Color palette for the application UI."""

    BG_WHITE = "#ffffff"
    FG_BLACK = "#111111"
    BORDER_LIGHT = "#d6d6d6"
    BORDER_MEDIUM = "#cdcdcd"
    HOVER_BG = "#f7f7f7"
    PRESSED_BG = "#eeeeee"

    BG_DARK = "#332f2a"
    BG_MEDIUM_DARK = "#3a352f"
    BG_HOVER_DARK = "#7a889a"
    FG_LIGHT = "#c8c1b7"
    BORDER_DARK = "#595148"

    SELECT_BG = "#6f7f94"
    SELECT_FG = "#ece4d9"
    SELECT_BORDER = "#7f8fa3"


class Styles:
    """Reusable stylesheet templates."""

    @staticmethod
    def button(dark=False):
        if dark:
            return f"""
                QPushButton {{
                    background-color: {Colors.BG_MEDIUM_DARK};
                    color: {Colors.FG_LIGHT};
                    border: 1px solid {Colors.BORDER_DARK};
                    border-radius: 6px;
                    padding: 8px 12px;
                    text-align: left;
                    outline: none;
                }}
                QPushButton:hover {{
                    background-color: {Colors.BG_HOVER_DARK};
                    color: #ffffff;
                }}
                QPushButton:pressed {{
                    background-color: #5a6a7a;
                    border: 1px solid #4a5a6a;
                }}
                QPushButton:focus {{
                    outline: none;
                    border: 1px solid {Colors.BORDER_DARK};
                }}
                QPushButton:disabled {{
                    background-color: #2a2520;
                    color: #7a7067;
                }}
            """
        return f"""
            QPushButton {{
                background-color: {Colors.BG_WHITE};
                color: {Colors.FG_BLACK};
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: 6px;
                padding: 8px 12px;
                text-align: left;
                outline: none;
            }}
            QPushButton:hover {{
                background-color: {Colors.HOVER_BG};
                border-color: {Colors.BORDER_MEDIUM};
            }}
            QPushButton:pressed {{
                background-color: {Colors.PRESSED_BG};
            }}
            QPushButton:focus {{
                outline: none;
                border: 1px solid {Colors.BORDER_LIGHT};
            }}
        """

    @staticmethod
    def selected_button():
        return f"""
            QPushButton {{
                font-weight: bold;
                background-color: {Colors.SELECT_BG};
                color: {Colors.SELECT_FG};
                border: 2px solid {Colors.SELECT_BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                text-align: left;
                outline: none;
            }}
            QPushButton:hover {{
                background-color: #7f8fa4;
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: #5f6f84;
            }}
            QPushButton:focus {{
                outline: none;
                border: 2px solid {Colors.SELECT_BORDER};
            }}
        """

    @staticmethod
    def preview_label(object_name):
        return f"""
            QLabel#{object_name} {{
                border: 2px solid {Colors.BORDER_DARK};
                background-color: {Colors.BG_DARK};
                color: {Colors.FG_LIGHT};
                border-radius: 8px;
                padding: 8px;
                selection-background-color: transparent;
                selection-color: {Colors.FG_LIGHT};
            }}
            QLabel#{object_name}:hover {{
                border: 2px solid {Colors.BORDER_DARK};
            }}
        """

    @staticmethod
    def info_label(color=Colors.FG_BLACK):
        return f"""
            QLabel {{
                color: {color};
                background-color: transparent;
                padding: 4px;
                font-size: 13px;
                selection-background-color: transparent;
                selection-color: {color};
            }}
        """

    @staticmethod
    def scroll_area():
        return f"""
            QScrollArea#scroll_area {{
                background-color: {Colors.BG_WHITE};
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: 8px;
            }}
            QScrollArea#scroll_area > QWidget > QWidget {{
                background-color: transparent;
            }}
            QScrollArea#scroll_area QWidget#scroll_container {{
                background-color: transparent;
            }}
        """
