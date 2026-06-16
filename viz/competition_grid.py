from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QBrush, QPen
import numpy as np

from Osmograph.ui.theme import COLORS

CLASS_COLORS = {
    "cinnamon": QColor(139, 90, 43),
    "garlic": QColor(255, 191, 0),
    "ginger": QColor(255, 215, 0),
    "lemon": QColor(50, 205, 50),
    "onion": QColor(180, 60, 120),
    "unknown": QColor(128, 128, 128),
    "room_air": QColor(100, 180, 255),
    "fresh_air": QColor(100, 180, 255),
}
DEFAULT_COLOR = QColor(100, 100, 100)
BAR_WIDTH = 50
BAR_SPACING = 8
BOTTOM_MARGIN = 60
TOP_MARGIN = 10
ANIM_SPEED = 0.3


class CompetitionGrid(QWidget):
    prediction_locked = Signal(str, float)
    prediction_unknown = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._classes: list[str] = []
        self._probabilities: list[float] = []
        self._display_probs: list[float] = []
        self._top_class = ""
        self._top_confidence = 0.0
        self._locked = False
        self._locked_class = ""
        self._lock_count = 0
        self._unknown_count = 0
        self._unknown = False
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start(33)

        self._label = QLabel("Competition Grid")
        self._label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 9px; font-weight: bold;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self.setMinimumHeight(200)

    def set_classes(self, classes: list[str]) -> None:
        self._classes = classes
        self._probabilities = [0.0] * len(classes)
        self._display_probs = [0.0] * len(classes)
        self._locked = False
        self._locked_class = ""
        self._lock_count = 0
        self._unknown_count = 0
        self._unknown = False
        self.update()

    def update_probabilities(self, probabilities: list[float], top_idx: int) -> None:
        if not self._classes:
            return
        self._probabilities = probabilities
        self._top_class = self._classes[top_idx] if top_idx < len(self._classes) else "unknown"
        self._top_confidence = probabilities[top_idx] if len(probabilities) > top_idx else 0.0

        if self._top_confidence > 0.7:
            self._lock_count += 1
            self._unknown_count = 0
            if self._lock_count >= 10 and not self._locked:
                self._locked = True
                self._locked_class = self._top_class
                self.prediction_locked.emit(self._top_class, self._top_confidence)
        else:
            self._lock_count = 0
            self._locked = False

        if self._top_confidence < 0.5:
            self._unknown_count += 1
            if self._unknown_count >= 20:
                nearest = self._classes[top_idx] if top_idx < len(self._classes) else ""
                if not self._unknown:
                    self._unknown = True
                    self.prediction_unknown.emit(nearest)
        else:
            self._unknown_count = 0
            self._unknown = False

        self.update()

    def reset(self) -> None:
        self._classes = []
        self._probabilities = []
        self._display_probs = []
        self._top_class = ""
        self._top_confidence = 0.0
        self._locked = False
        self._locked_class = ""
        self._lock_count = 0
        self._unknown_count = 0
        self._unknown = False
        self.update()

    def _animate(self) -> None:
        if not self._classes:
            return
        changed = False
        target_len = len(self._probabilities)
        while len(self._display_probs) < target_len:
            self._display_probs.append(0.0)
            changed = True
        while len(self._display_probs) > target_len:
            self._display_probs.pop()
            changed = True
        for i in range(min(len(self._display_probs), len(self._probabilities))):
            diff = self._probabilities[i] - self._display_probs[i]
            if abs(diff) > 0.005:
                self._display_probs[i] += diff * ANIM_SPEED
                changed = True
        if changed:
            self.update()

    def paintEvent(self, event) -> None:
        if not self._classes:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        n = len(self._classes)
        total_bar_width = n * BAR_WIDTH + (n - 1) * BAR_SPACING
        start_x = (w - total_bar_width) // 2

        font = QFont("sans-serif", 9)
        painter.setFont(font)
        fm = QFontMetrics(font)

        bar_h = h - TOP_MARGIN - BOTTOM_MARGIN

        for i in range(n):
            x = start_x + i * (BAR_WIDTH + BAR_SPACING)
            prob = self._display_probs[i] if i < len(self._display_probs) else 0.0
            class_name = self._classes[i] if i < len(self._classes) else "?"

            bar_height = int(prob * bar_h)
            y = TOP_MARGIN + bar_h - bar_height

            color = CLASS_COLORS.get(class_name.lower(), DEFAULT_COLOR)
            if self._locked and class_name == self._locked_class:
                glow = QColor(color.red(), color.green(), color.blue(), 80)
                painter.setBrush(QBrush(glow))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(x - 4, y - 4, BAR_WIDTH + 8, bar_height + 8, 6, 6)

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.NoPen))
            painter.drawRoundedRect(x, y, BAR_WIDTH, bar_height, 4, 4)

            pct_text = f"{int(prob * 100)}%"
            painter.setPen(QColor(255, 255, 255))
            pct_font = QFont("sans-serif", 8, QFont.Bold)
            painter.setFont(pct_font)
            pct_rect = painter.boundingRect(x, y - 14, BAR_WIDTH, 12, Qt.AlignCenter, pct_text)
            painter.drawText(pct_rect, Qt.AlignCenter, pct_text)

            painter.setFont(font)
            painter.save()
            painter.translate(x + BAR_WIDTH // 2, h - 10)
            painter.rotate(-90)
            text_rect = painter.boundingRect(0, 0, 50, BAR_WIDTH, Qt.AlignCenter, class_name)
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(text_rect, Qt.AlignCenter, class_name)
            painter.restore()

        if self._locked:
            painter.setPen(QPen(QColor(0, 255, 100, 120), 2))
            painter.drawRoundedRect(2, 2, w - 4, h - 4, 8, 8)

        painter.end()
