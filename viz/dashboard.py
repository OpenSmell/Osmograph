from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSplitter, QFrame, QSizePolicy,
)
import numpy as np

from Osmograph.viz.traces import LiveTracesWidget
from Osmograph.viz.chemprint import ChemprintBarWidget
from Osmograph.viz.signal_quality import SignalQualityIndicator
from Osmograph.viz.substance import SubstanceDisplay
from Osmograph.ui.theme import COLORS


class DashboardWidget(QWidget):
    def __init__(self, sensor_count: int = 6, parent=None):
        super().__init__(parent)
        self._sensor_count = sensor_count

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        top_bar = QHBoxLayout()
        title = QLabel("Live Dashboard")
        title.setStyleSheet(f"color: {COLORS['text_bright']}; font-size: 16px; font-weight: bold;")
        top_bar.addWidget(title)

        self._sample_count_label = QLabel("Samples: 0")
        self._sample_count_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        top_bar.addWidget(self._sample_count_label)

        self._data_quality = QLabel("")
        self._data_quality.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        top_bar.addWidget(self._data_quality)

        top_bar.addStretch()
        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setFixedWidth(80)
        self._reset_btn.clicked.connect(self.reset)
        self._reset_btn.setToolTip("Clear all traces, predictions, and quality metrics")
        top_bar.addWidget(self._reset_btn)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setFixedWidth(80)
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._pause_btn.setToolTip("Freeze/unfreeze the live trace display")
        top_bar.addWidget(self._pause_btn)

        layout.addLayout(top_bar)

        content = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.traces = LiveTracesWidget()
        self.traces.set_sensor_count(sensor_count)
        left_layout.addWidget(self.traces)

        self.chemprint = ChemprintBarWidget()
        left_layout.addWidget(self.chemprint)

        content.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self.signal_quality = SignalQualityIndicator()
        right_layout.addWidget(self.signal_quality)

        self.substance = SubstanceDisplay()
        right_layout.addWidget(self.substance)

        data_info = QLabel("Per-Sensor Quality")
        data_info.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; padding-top: 8px;")
        right_layout.addWidget(data_info)

        self._sensor_quality_labels = []
        sensor_names = ["MQ-135", "MQ-3", "MQ-6", "MQ-7", "MQ-4", "MQ-8"]
        for i, name in enumerate(sensor_names):
            lbl = QLabel(f"{name}: --")
            lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 9px;")
            right_layout.addWidget(lbl)
            self._sensor_quality_labels.append(lbl)

        right_layout.addStretch()
        content.addWidget(right_panel)

        content.setSizes([750, 200])
        layout.addWidget(content)

        self._hint_label = QLabel(
            "Connect your ESP32 via USB, then click Detect Board \u2192 Connect\n"
            "Once connected, enter a label and click Record to capture a sample"
        )
        self._hint_label.setAlignment(Qt.AlignCenter)
        self._hint_label.setStyleSheet(
            f"color: {COLORS['text_dim']}; background: {COLORS['bg_med']}; "
            f"border: 1px dashed {COLORS['border']}; border-radius: 6px; "
            f"padding: 8px; font-size: 12px;"
        )
        layout.addWidget(self._hint_label)

        self._counter_timer = QTimer(self)
        self._counter_timer.timeout.connect(self._update_stats)

    def start_timers(self):
        self._counter_timer.start(500)
        self.traces.start_timers()
        self.signal_quality.start_timers()

    def add_sample(self, sample: np.ndarray) -> None:
        self.traces.add_sample(sample)
        self._hint_label.setVisible(False)

    def update_prediction(self, substance: str, confidence: float, warning: str = "") -> None:
        self.substance.update_prediction(substance, confidence, warning)
        if substance and substance != "---":
            self._substance_label.setText(f"Substance: {substance}")

    def update_chemprint(self, chemprint: np.ndarray) -> None:
        self.chemprint.update_chemprint(chemprint)

    def set_sensor_count(self, count: int) -> None:
        self._sensor_count = count
        self.traces.set_sensor_count(count)

    def update_quality_metrics(self, metrics: list[dict]):
        sensor_names = ["MQ-135", "MQ-3", "MQ-6", "MQ-7", "MQ-4", "MQ-8"]
        for i, m in enumerate(metrics):
            if i >= len(self._sensor_quality_labels):
                break
            s = m.get("stability", 0)
            v = m.get("variance", 0)
            color = COLORS["accent_green"] if s > 80 else COLORS["accent_yellow"] if s > 50 else COLORS["accent_red"]
            self._sensor_quality_labels[i].setText(
                f"{sensor_names[i]}: {s:.0f}% stable (var={v:.1f})"
            )
            self._sensor_quality_labels[i].setStyleSheet(f"color: {color}; font-size: 9px;")

    def set_connected(self, connected: bool):
        if connected:
            self._hint_label.setVisible(False)
        else:
            self._hint_label.setVisible(True)

    def _toggle_pause(self) -> None:
        self.traces.toggle_pause()
        self._pause_btn.setText("Resume" if self.traces.is_paused else "Pause")

    def _update_stats(self) -> None:
        n = self.traces.sample_count
        self._sample_count_label.setText(f"Samples: {n}")

        if n > 20:
            data = self.traces.current_data
            if len(data) > 1:
                recent = data[-100:]
                per_sensor = []
                for si in range(min(6, recent.shape[1])):
                    col = recent[:, si]
                    var = float(col.var())
                    mean = float(col.mean())
                    stability = max(0, min(100, 100 * (1 - min(var / 500, 1))))
                    per_sensor.append({"variance": var, "stability": stability, "mean": mean})
                self.update_quality_metrics(per_sensor)
                self.signal_quality.update_from_metrics(per_sensor)
                avg_var = np.mean([m["variance"] for m in per_sensor])
                self._data_quality.setText(f"Avg variance: {avg_var:.1f}")

    def reset(self) -> None:
        self.traces.reset()
        self.substance.clear()
        self.signal_quality.reset_warmup()
        self.chemprint.clear()
        self._sample_count_label.setText("Samples: 0")
        self._data_quality.setText("")
        for lbl in self._sensor_quality_labels:
            lbl.setText(f"{lbl.text().split(':')[0]}: --")
            lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 9px;")
