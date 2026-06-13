import numpy as np
from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

import pyqtgraph as pg

from Osmograph.ui.theme import COLORS

SENSOR_NAMES = ["MQ-135", "MQ-3", "MQ-6", "MQ-7", "MQ-4", "MQ-8"]
SENSOR_COLORS = ["#00ffff", "#ff00ff", "#adff2f", "#ff6347", "#ffd700", "#00ced1"]
WINDOW_SIZE = 500


class LiveTracesWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = np.zeros((WINDOW_SIZE, 6), dtype=np.float32)
        self._index = 0
        self._curves: list[pg.PlotDataItem] = []
        self._paused = False
        self._sample_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.plot_widget = pg.PlotWidget(background=COLORS["bg_dark"])
        self.plot_widget.setLabel("left", "Sensor Value", color=COLORS["text_dim"])
        self.plot_widget.setLabel("bottom", "Sample", color=COLORS["text_dim"])
        self.plot_widget.showGrid(x=True, y=True, alpha=0.1)
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.plot_widget.setLimits(xMin=0, xMax=WINDOW_SIZE)
        self.plot_widget.getAxis("left").setTextPen(COLORS["text_dim"])
        self.plot_widget.getAxis("bottom").setTextPen(COLORS["text_dim"])

        legend = self.plot_widget.addLegend(offset=(10, 10))
        legend.setBrush(pg.mkColor(COLORS["bg_med"]))

        for i in range(6):
            pen = pg.mkPen(color=SENSOR_COLORS[i], width=1.5, antialias=True)
            curve = self.plot_widget.plot(
                np.arange(WINDOW_SIZE),
                self._data[:, i],
                pen=pen,
                name=SENSOR_NAMES[i],
            )
            self._curves.append(curve)

        self._info_label = QLabel("Warming up...")
        self._info_label.setStyleSheet(f"color: {COLORS['text_dim']}; padding: 4px;")
        layout.addWidget(self._info_label)
        layout.addWidget(self.plot_widget)

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._refresh_plot)

    def start_timers(self):
        self._update_timer.start(50)

        self._sample_count = 0

    def add_sample(self, sample: np.ndarray) -> None:
        if self._paused:
            return
        if self._info_label.isVisible():
            self._info_label.setVisible(False)
        if self._index >= WINDOW_SIZE:
            self._data[:-1] = self._data[1:]
            self._data[-1] = sample[:6]
        else:
            self._data[self._index] = sample[:6]
            self._index += 1
        self._sample_count += 1

    def _refresh_plot(self) -> None:
        visible = self._data[:max(self._index, 1)]
        for i, curve in enumerate(self._curves):
            if self._index < WINDOW_SIZE:
                curve.setData(np.arange(self._index), visible[:, i])
            else:
                curve.setData(np.arange(WINDOW_SIZE), self._data[:, i])

        if self._index > 10:
            self.plot_widget.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)

    def set_sensor_count(self, count: int) -> None:
        for i in range(6):
            self._curves[i].setVisible(i < count)

    def toggle_pause(self) -> None:
        self._paused = not self._paused

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def current_data(self) -> np.ndarray:
        return self._data[:max(self._index, 1)].copy()

    def reset(self) -> None:
        self._data.fill(0)
        self._index = 0
        self._sample_count = 0
        self._info_label.setText("Warming up...")
        self._info_label.setVisible(True)

    def set_info(self, text: str) -> None:
        self._info_label.setText(text)
