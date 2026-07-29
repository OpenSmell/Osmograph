import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt

from Osmograph.ui.theme import COLORS

SENSOR_NAMES = ["MQ-135", "MQ-3", "MQ-6", "MQ-7", "MQ-4", "MQ-8"]


class SensorAmplitudeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(1)

        header = QLabel("Sensor Response")
        header.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 10px; font-weight: 600; padding: 1px 4px;"
        )
        layout.addWidget(header)

        self._bars = []
        for name in SENSOR_NAMES:
            row = QHBoxLayout()
            row.setSpacing(4)
            row.setContentsMargins(0, 0, 0, 0)

            label = QLabel(name)
            label.setFixedWidth(50)
            label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px;")
            row.addWidget(label)

            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            bar.setStyleSheet(
                f"QProgressBar {{ background-color: {COLORS['bg_tertiary']}; border: none; border-radius: 3px; }} "
                f"QProgressBar::chunk {{ background-color: {COLORS['accent']}; border-radius: 3px; }}"
            )
            row.addWidget(bar)

            val_label = QLabel("0.00")
            val_label.setFixedWidth(34)
            val_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 8px;")
            row.addWidget(val_label)

            layout.addLayout(row)
            self._bars.append((bar, val_label))

        self.setMinimumHeight(100)

    def update_amplitudes(self, amplitudes: np.ndarray):
        for i, (bar, label) in enumerate(self._bars):
            if i < len(amplitudes):
                val = float(amplitudes[i])
                bar.setValue(min(1000, int(val * 1000)))
                label.setText(f"{val:.2f}")

    def clear(self):
        for bar, label in self._bars:
            bar.setValue(0)
            label.setText("0.00")

    def update_theme(self):
        self._update_bar_styles()

    def _update_bar_styles(self):
        for bar, _ in self._bars:
            bar.setStyleSheet(
                f"QProgressBar {{ background-color: {COLORS['bg_tertiary']}; border: none; border-radius: 3px; }} "
                f"QProgressBar::chunk {{ background-color: {COLORS['accent']}; border-radius: 3px; }}"
            )
