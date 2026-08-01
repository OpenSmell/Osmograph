import copy
from PySide6.QtCore import QObject, Signal

THEME_MODES = ["HUD (Dark)", "Clean (Light)"]


DARK_COLORS = {
    "bg_primary": "#0a0a0a",
    "bg_secondary": "#141414",
    "bg_tertiary": "#1e1e1e",
    "bg_card": "#181818",
    "text_primary": "#f5f5f5",
    "text_secondary": "#c8c8c8",
    "text_muted": "#909090",
    "border": "#2a2a2a",
    "border_focus": "#4a9eff",
    "accent": "#4a9eff",
    "accent_hover": "#6ab4ff",
    "accent_text": "#ffffff",
    "success": "#34d399",
    "warning": "#fbbf24",
    "error": "#ef4444",
    "focus": "#3b82f6",
    "canvas_bg": "#0d0d0d",
    "bg_dark": "#0a0a0a",
    "bg_med": "#141414",
    "bg_light": "#1e1e1e",
    "surface": "#181818",
    "text_bright": "#f5f5f5",
    "text_dim": "#c8c8c8",
    "text_muted_old": "#909090",
    "accent_cyan": "#4a9eff",
    "accent_magenta": "#6ab4ff",
    "accent_green": "#34d399",
    "accent_orange": "#fbbf24",
    "accent_red": "#ef4444",
    "accent_yellow": "#fbbf24",
    "button_bg": "#1e1e1e",
    "button_hover": "#2a2a2a",
    "button_text": "#f5f5f5",
}

LIGHT_COLORS = {
    "bg_primary": "#ffffff",
    "bg_secondary": "#f5f5f5",
    "bg_tertiary": "#eaeaea",
    "bg_card": "#ffffff",
    "text_primary": "#000000",
    "text_secondary": "#1a1a1a",
    "text_muted": "#555555",
    "border": "#c0c0c0",
    "border_focus": "#2563eb",
    "accent": "#2563eb",
    "accent_hover": "#3b82f6",
    "accent_text": "#ffffff",
    "success": "#059669",
    "warning": "#d97706",
    "error": "#dc2626",
    "focus": "#3b82f6",
    "canvas_bg": "#ffffff",
    "bg_dark": "#ffffff",
    "bg_med": "#f5f5f5",
    "bg_light": "#eaeaea",
    "surface": "#ffffff",
    "text_bright": "#000000",
    "text_dim": "#1a1a1a",
    "text_muted_old": "#555555",
    "accent_cyan": "#2563eb",
    "accent_magenta": "#3b82f6",
    "accent_green": "#059669",
    "accent_orange": "#d97706",
    "accent_red": "#dc2626",
    "accent_yellow": "#d97706",
    "button_bg": "#eaeaea",
    "button_hover": "#d0d0d0",
    "button_text": "#000000",
}

COLORS = copy.deepcopy(DARK_COLORS)


class ThemeManager(QObject):
    theme_changed = Signal()

    def __init__(self):
        super().__init__()
        self._mode = "dark"

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        if mode == "light":
            COLORS.update(LIGHT_COLORS)
        else:
            COLORS.update(DARK_COLORS)
        self.theme_changed.emit()

    def toggle(self) -> str:
        new = "light" if self._mode == "dark" else "dark"
        self.set_mode(new)
        return new

    def is_dark(self) -> bool:
        return self._mode == "dark"


_manager = ThemeManager()


def get_manager() -> ThemeManager:
    return _manager


def generate_stylesheet() -> str:
    c = COLORS
    is_dark = _manager.is_dark()

    btn_bg = c["bg_tertiary"]
    btn_hover = c["border"]
    btn_text = c["text_primary"]
    input_bg = c["bg_secondary"]

    return f"""
    QMainWindow, QDialog, QWidget {{
        background-color: {c['bg_primary']};
        color: {c['text_primary']};
        font-family: 'SF Pro Display', 'Segoe UI', -apple-system, sans-serif;
    }}
    QMenuBar {{
        background-color: {c['bg_secondary']};
        color: {c['text_secondary']};
        border-bottom: 1px solid {c['border']};
        font-size: 12px;
        padding: 2px 0;
    }}
    QMenuBar::item:selected {{
        background-color: {c['bg_tertiary']};
        color: {c['accent']};
    }}
    QMenuBar::item:pressed {{
        background-color: {c['bg_tertiary']};
    }}
    QMenu {{
        background-color: {c['bg_secondary']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        padding: 4px 0;
    }}
    QMenu::item {{
        padding: 6px 24px;
        font-size: 12px;
    }}
    QMenu::item:selected {{
        background-color: {c['bg_tertiary']};
        color: {c['accent']};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {c['border']};
        margin: 4px 8px;
    }}
    QPushButton {{
        background-color: {btn_bg};
        color: {btn_text};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 6px 18px;
        font-size: 12px;
        font-weight: 500;
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: {btn_hover};
        border-color: {c['accent']};
    }}
    QPushButton:pressed {{
        background-color: {c['bg_primary']};
    }}
    QPushButton:disabled {{
        background-color: {c['bg_secondary']};
        color: {c['text_muted']};
        border-color: {c['border']};
    }}
    QComboBox {{
        background-color: {input_bg};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 4px 10px;
        min-height: 24px;
        font-size: 12px;
    }}
    QComboBox:hover {{
        border-color: {c['accent']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid {c['text_secondary']};
        margin-right: 6px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c['bg_secondary']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        selection-background-color: {c['bg_tertiary']};
        selection-color: {c['accent']};
        outline: none;
    }}
    QSpinBox, QDoubleSpinBox, QLineEdit {{
        background-color: {input_bg};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 4px 10px;
        min-height: 24px;
        font-size: 12px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
        border-color: {c['accent']};
    }}
    QLabel {{
        color: {c['text_primary']};
        background: transparent;
    }}
    QGroupBox {{
        border: 1px solid {c['border']};
        border-radius: 8px;
        margin-top: 14px;
        padding-top: 18px;
        font-weight: 600;
        font-size: 12px;
        color: {c['text_secondary']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
    }}
    QTabWidget::pane {{
        border: none;
        border-top: 1px solid {c['border']};
        background-color: {c['bg_primary']};
    }}
    QTabBar::tab {{
        background-color: {c['bg_secondary']};
        color: {c['text_muted']};
        border: none;
        border-bottom: 2px solid transparent;
        padding: 8px 20px;
        margin-right: 1px;
        font-size: 12px;
        font-weight: 500;
    }}
    QTabBar::tab:selected {{
        background-color: {c['bg_primary']};
        color: {c['accent']};
        border-bottom: 2px solid {c['accent']};
    }}
    QTabBar::tab:hover {{
        color: {c['text_secondary']};
    }}
    QScrollBar:vertical {{
        background-color: {c['bg_primary']};
        width: 8px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {c['border']};
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {c['text_muted']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QProgressBar {{
        background-color: {c['bg_tertiary']};
        border: none;
        border-radius: 4px;
        text-align: center;
        color: {c['text_secondary']};
        font-size: 10px;
        min-height: 8px;
    }}
    QProgressBar::chunk {{
        background-color: {c['accent']};
        border-radius: 4px;
    }}
    QListWidget, QTreeWidget {{
        background-color: {input_bg};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        outline: none;
    }}
    QListWidget::item:selected, QTreeWidget::item:selected {{
        background-color: {c['bg_tertiary']};
        color: {c['accent']};
    }}
    QListWidget::item:hover, QTreeWidget::item:hover {{
        background-color: {c['bg_tertiary']};
    }}
    QSplitter::handle {{
        background-color: {c['border']};
    }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QSplitter::handle:vertical {{ height: 1px; }}
    QCheckBox {{
        color: {c['text_primary']};
        font-size: 12px;
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {c['border']};
        border-radius: 3px;
        background-color: {input_bg};
    }}
    QCheckBox::indicator:checked {{
        background-color: {c['accent']};
        border-color: {c['accent']};
    }}
    QHeaderView::section {{
        background-color: {c['bg_secondary']};
        color: {c['text_secondary']};
        border: none;
        border-bottom: 1px solid {c['border']};
        padding: 6px 12px;
        font-size: 11px;
        font-weight: 600;
    }}
    QStatusBar {{
        background-color: {c['bg_secondary']};
        color: {c['text_secondary']};
        border-top: 1px solid {c['border']};
        font-size: 11px;
    }}
    QToolTip {{
        background-color: {c['bg_secondary']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 11px;
    }}
    QTableWidget {{
        background-color: {input_bg};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        gridline-color: {c['border']};
    }}
    QTableWidget::item:selected {{
        background-color: {c['bg_tertiary']};
        color: {c['accent']};
    }}
    """