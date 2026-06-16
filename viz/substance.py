from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QProgressBar
from PySide6.QtGui import QPixmap

from Osmograph.ui.theme import COLORS

ICONS_DIR = Path(__file__).resolve().parent.parent / "substance_icons"

ICON_ALIASES = {
    "room air": "fresh air",
    "room_air": "fresh air",
}


class SubstanceDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon_paths = self._scan_icons()
        self._last_substance = ""
        self._locked = False
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)
        self._flash_active = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        header = QLabel("Prediction")
        header.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold;")
        layout.addWidget(header)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(6)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(48, 48)
        self._icon_label.setStyleSheet("background: transparent;")
        icon_row.addWidget(self._icon_label)

        self._substance_label = QLabel("---")
        self._substance_label.setStyleSheet(
            f"color: {COLORS['text_bright']}; font-size: 22px; font-weight: bold;"
        )
        self._substance_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        icon_row.addWidget(self._substance_label, 1)

        layout.addLayout(icon_row)

        conf_layout = QHBoxLayout()
        conf_label = QLabel("Confidence")
        conf_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 9px;")
        conf_layout.addWidget(conf_label)
        conf_layout.addStretch()

        self._conf_value = QLabel("0.00")
        self._conf_value.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 11px;")
        conf_layout.addWidget(self._conf_value)
        layout.addLayout(conf_layout)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #222;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff4444, stop:0.5 #ffaa00, stop:1 #00ff88);
                border-radius: 4px;
            }
        """)
        layout.addWidget(self._progress_bar)

        self._warning_label = QLabel("")
        self._warning_label.setStyleSheet(f"color: {COLORS['warning']}; font-size: 9px;")
        self._warning_label.setWordWrap(True)
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

        layout.addStretch()

        self.setToolTip("Predicted substance from OpenSmell analysis")

    def _scan_icons(self) -> dict[str, Path]:
        icons = {}
        if ICONS_DIR.exists():
            for f in ICONS_DIR.glob("*.svg"):
                key = f.stem.lower().replace("_", " ").replace("-", " ")
                icons[key] = f
        return icons

    def _set_icon(self, substance: str) -> None:
        norm = substance.strip().lower()
        norm = ICON_ALIASES.get(norm, norm)
        if norm in self._icon_paths:
            pix = QPixmap(str(self._icon_paths[norm]))
            self._icon_label.setPixmap(pix.scaled(
                48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
            self._icon_label.setVisible(True)
            return
        for key, path in self._icon_paths.items():
            if norm in key or key in norm:
                pix = QPixmap(str(path))
                self._icon_label.setPixmap(pix.scaled(
                    48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
                self._icon_label.setVisible(True)
                return
        self._icon_label.setVisible(False)

    def update_prediction(self, substance: str, confidence: float, warning: str = "") -> None:
        display_name = substance if substance else "Unknown"
        self._substance_label.setText(display_name)
        self._set_icon(display_name)
        conf_pct = min(int(confidence * 100), 100)
        self._conf_value.setText(f"{confidence:.4f}")
        self._progress_bar.setValue(conf_pct)

        if warning:
            self._warning_label.setText(warning)
            self._warning_label.setVisible(True)
        else:
            self._warning_label.setVisible(False)

    def set_locked(self, locked: bool, class_name: str = "") -> None:
        self._locked = locked
        if locked:
            border = "2px solid #00ff88"
            self.setStyleSheet(f"border: {border}; border-radius: 8px;")
            self.setToolTip(f"Locked on: {class_name}")
        else:
            self.setStyleSheet("")

    def set_flash(self, flash: bool) -> None:
        if flash:
            self._flash_active = True
            self.update()
            self._flash_timer.start(300)

    def _end_flash(self) -> None:
        self._flash_active = False
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._flash_active:
            from PySide6.QtGui import QPainter, QColor, QBrush
            p = QPainter(self)
            p.setBrush(QBrush(QColor(0, 255, 136, 40)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(self.rect(), 8, 8)
            p.end()

    def clear(self) -> None:
        self._substance_label.setText("---")
        self._icon_label.setVisible(False)
        self._conf_value.setText("0.00")
        self._progress_bar.setValue(0)
        self._warning_label.setVisible(False)
        self._last_substance = ""
        self._locked = False
        self.setStyleSheet("")
