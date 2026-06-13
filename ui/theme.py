COLORS = {
    "bg_dark": "#0a0a0a",
    "bg_med": "#1a1a2e",
    "bg_light": "#16213e",
    "surface": "#222244",
    "text_bright": "#e0e0ff",
    "text_dim": "#8888aa",
    "text_muted": "#555577",
    "accent_cyan": "#00ffff",
    "accent_magenta": "#ff00ff",
    "accent_green": "#adff2f",
    "accent_orange": "#ff8c00",
    "accent_red": "#ff4444",
    "accent_yellow": "#ffd700",
    "warning": "#ffaa00",
    "success": "#00ff88",
    "error": "#ff4444",
    "border": "#333355",
    "button_bg": "#2a2a4a",
    "button_hover": "#3a3a6a",
    "button_text": "#ccccff",
}

DARK_STYLESHEET = """
QMainWindow, QDialog, QWidget {
    background-color: #0a0a0a;
    color: #e0e0ff;
}

QMenuBar {
    background-color: #1a1a2e;
    color: #ccccff;
    border-bottom: 1px solid #333355;
}
QMenuBar::item:selected {
    background-color: #3a3a6a;
}
QMenu {
    background-color: #1a1a2e;
    color: #ccccff;
    border: 1px solid #333355;
}
QMenu::item:selected {
    background-color: #3a3a6a;
}

QPushButton {
    background-color: #2a2a4a;
    color: #ccccff;
    border: 1px solid #333355;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #3a3a6a;
    border-color: #5555aa;
}
QPushButton:pressed {
    background-color: #1a1a3a;
}
QPushButton:disabled {
    background-color: #1a1a2e;
    color: #555577;
}

QComboBox {
    background-color: #1a1a2e;
    color: #ccccff;
    border: 1px solid #333355;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}
QComboBox:hover {
    border-color: #5555aa;
}
QComboBox::drop-down {
    border: none;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #8888aa;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #1a1a2e;
    color: #ccccff;
    border: 1px solid #333355;
    selection-background-color: #3a3a6a;
}

QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #1a1a2e;
    color: #ccccff;
    border: 1px solid #333355;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border-color: #5555aa;
}

QLabel {
    color: #e0e0ff;
    background: transparent;
}
QLabel[heading="true"] {
    font-size: 16px;
    font-weight: bold;
    color: #00ffff;
}

QGroupBox {
    border: 1px solid #333355;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    color: #ccccff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}

QTabWidget::pane {
    border: 1px solid #333355;
    background-color: #0a0a0a;
}
QTabBar::tab {
    background-color: #1a1a2e;
    color: #8888aa;
    border: 1px solid #333355;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 16px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #2a2a4a;
    color: #00ffff;
    border-bottom: 2px solid #00ffff;
}
QTabBar::tab:hover {
    background-color: #3a3a6a;
}

QScrollBar:vertical {
    background-color: #1a1a2e;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #333355;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #5555aa;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QProgressBar {
    background-color: #1a1a2e;
    border: 1px solid #333355;
    border-radius: 4px;
    text-align: center;
    color: #e0e0ff;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #ff00ff, stop:1 #00ffff);
    border-radius: 3px;
}

QListWidget, QTreeWidget {
    background-color: #1a1a2e;
    color: #e0e0ff;
    border: 1px solid #333355;
    border-radius: 4px;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #3a3a6a;
}
QListWidget::item:hover, QTreeWidget::item:hover {
    background-color: #2a2a4a;
}

QSplitter::handle {
    background-color: #333355;
}
QSplitter::handle:horizontal {
    width: 2px;
}
QSplitter::handle:vertical {
    height: 2px;
}
"""
