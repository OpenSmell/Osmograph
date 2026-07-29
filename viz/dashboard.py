import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSplitter, QFrame, QSizePolicy,
)
import numpy as np

from Osmograph.viz.traces import LiveTracesWidget
from Osmograph.viz.fingerprint import RadarFingerprintWidget
from Osmograph.viz.signal_quality import SignalQualityIndicator, SignalLevel
from Osmograph.viz.substance import SubstanceDisplay
from Osmograph.viz.competition_grid import CompetitionGrid
from Osmograph.viz.device_health import DeviceHealthWidget
from Osmograph.ui.theme import COLORS


class DashboardWidget(QWidget):
    def __init__(self, sensor_count: int = 6, parent=None):
        super().__init__(parent)
        self._sensor_count = sensor_count
        self._classifier = None
        self._last_qualities = ["off"] * 6

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        top_bar = QHBoxLayout()
        title = QLabel("Live Dashboard")
        title.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 15px; font-weight: bold;"
        )
        top_bar.addWidget(title)

        self._sample_count_label = QLabel("Samples: 0")
        self._sample_count_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px;"
        )
        top_bar.addWidget(self._sample_count_label)

        top_bar.addStretch()

        self._fp_btn = QPushButton("FP")
        self._fp_btn.setFixedSize(28, 22)
        self._fp_btn.setToolTip("Toggle fingerprint overlay")
        self._fp_btn.setStyleSheet(
            f"font-size: 8px; font-weight: bold; padding: 0; "
            f"background: {COLORS['bg_tertiary']}; color: {COLORS['text_secondary']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 3px;"
        )
        self._fp_btn.clicked.connect(self._toggle_fingerprint)
        top_bar.addWidget(self._fp_btn)

        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setFixedWidth(60)
        self._reset_btn.clicked.connect(self.reset)
        self._reset_btn.setToolTip("Clear all traces and predictions")
        top_bar.addWidget(self._reset_btn)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setFixedWidth(60)
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._pause_btn.setToolTip("Freeze/unfreeze the trace display")
        top_bar.addWidget(self._pause_btn)

        layout.addLayout(top_bar)

        content = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._left_split = QSplitter(Qt.Vertical)
        self._left_split.setHandleWidth(1)

        self.traces = LiveTracesWidget()
        self.traces.set_sensor_count(sensor_count)
        self._left_split.addWidget(self.traces)

        self.fingerprint = RadarFingerprintWidget()
        self._left_split.addWidget(self.fingerprint)
        self._fp_visible = True

        self._left_split.setSizes([350, 140])
        left_layout.addWidget(self._left_split)

        content.addWidget(left_panel)

        right_panel = QWidget()
        right_panel.setMinimumWidth(180)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self.signal_quality = SignalQualityIndicator()
        right_layout.addWidget(self.signal_quality)

        self.device_health = DeviceHealthWidget()
        right_layout.addWidget(self.device_health)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {COLORS['border']};")
        right_layout.addWidget(line)

        self.substance = SubstanceDisplay()
        self.substance.setMinimumHeight(80)
        right_layout.addWidget(self.substance)

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet(f"color: {COLORS['border']};")
        right_layout.addWidget(line2)

        self.competition = CompetitionGrid()
        self.competition.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        right_layout.addWidget(self.competition, 1)

        content.addWidget(right_panel)

        content.setSizes([750, 220])
        layout.addWidget(content)

        self._hint_label = QLabel(
            "Welcome to Osmograph\n"
            "Connect your ESP32 via USB \u2192 Detect Board \u2192 Connect\n"
            "Or click Demo for simulated data \u2192 Recordings tab to import CSV"
        )
        self._hint_label.setAlignment(Qt.AlignCenter)
        self._hint_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; background: {COLORS['bg_secondary']}; "
            f"border: 1px dashed {COLORS['border']}; border-radius: 8px; "
            f"padding: 16px; font-size: 12px; line-height: 1.6;"
        )
        layout.addWidget(self._hint_label)

        self._counter_timer = QTimer(self)
        self._counter_timer.timeout.connect(self._update_stats)

    def start_timers(self):
        self._counter_timer.start(500)
        self.traces.start_timers()
        self.signal_quality.start_timers()

    def set_classifier(self, classifier) -> None:
        self._classifier = classifier
        if classifier and classifier.is_loaded and classifier.classes:
            self.competition.set_classes(classifier.classes)

    def add_sample(self, sample: np.ndarray) -> None:
        self.traces.add_sample(sample)
        self._hint_label.setVisible(False)
        if self._classifier and self._classifier.is_loaded:
            result = self._classifier.add_sample(sample)
            if result is not None:
                now = time.monotonic()
                if now - getattr(self, "_last_prediction_time", 0) < 0.4:
                    return
                self._last_prediction_time = now
                label, confidence = result
                self._update_competition_grid()
                if not self._classifier.is_unknown:
                    self.update_prediction(label, confidence)
                    self.substance.set_flash(
                        label != self.substance._last_substance
                    )
                    self.substance._last_substance = label
                else:
                    nearest = label if label != "unknown" else ""
                    display = (
                        f"Unknown \u2014 nearest: {nearest}" if nearest else "Unknown"
                    )
                    self.update_prediction(
                        display, confidence,
                        "Low confidence \u2014 out of distribution"
                    )
                    self.substance._last_substance = "unknown"

                if self._classifier.is_locked:
                    self.substance.set_locked(
                        True, self._classifier.locked_class
                    )
                else:
                    self.substance.set_locked(False)

    def _update_competition_grid(self) -> None:
        if not self._classifier or not self._classifier.is_loaded:
            return
        probs = self._classifier.current_probabilities
        classes = self._classifier.classes
        if probs and classes and len(probs) == len(classes):
            top_idx = int(np.argmax(probs))
            self.competition.update_probabilities(probs, top_idx)

    def update_prediction(
        self, substance: str, confidence: float, warning: str = ""
    ) -> None:
        self.substance.update_prediction(substance, confidence, warning)

    def update_fingerprint(self, features: dict, label: str = "") -> None:
        self.fingerprint.set_fingerprint(features, label)

    def add_fingerprint_overlay(
        self, features: dict, label: str = "", color: str = ""
    ) -> None:
        self.fingerprint.add_fingerprint(features, label, color)

    def clear_fingerprint_overlay(self) -> None:
        self.fingerprint.clear_overlay()

    def update_theme(self) -> None:
        self.traces.update_theme()
        self.fingerprint.update_theme()
        self.signal_quality.update_theme()
        self.device_health.update_theme()
        self.substance.update_theme()
        self.competition.update_theme()
        self._hint_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; background: {COLORS['bg_secondary']}; "
            f"border: 1px dashed {COLORS['border']}; border-radius: 8px; "
            f"padding: 16px; font-size: 12px; line-height: 1.6;"
        )
        self._fp_btn.setStyleSheet(
            f"font-size: 8px; font-weight: bold; padding: 0; "
            f"background: {COLORS['bg_tertiary']}; color: {COLORS['text_secondary']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 3px;"
        )

    def set_sensor_count(self, count: int) -> None:
        self._sensor_count = count
        self.traces.set_sensor_count(count)

    def update_quality_metrics(self, metrics: list[dict]):
        qualities = []
        for i, m in enumerate(metrics):
            s = m.get("stability", 0)
            if s > 80:
                qualities.append("good")
            elif s > 50:
                qualities.append("warning")
            else:
                qualities.append("error")
        self._last_qualities = qualities
        self.traces.set_sensor_quality(qualities)

    def set_connected(self, connected: bool):
        self._hint_label.setVisible(not connected)

    def _toggle_fingerprint(self) -> None:
        self._fp_visible = not self._fp_visible
        self.fingerprint.setVisible(self._fp_visible)
        sizes = self._left_split.sizes()
        if self._fp_visible:
            self._left_split.setSizes([max(1, sizes[0] - 140), 140])
        else:
            self._left_split.setSizes([sum(sizes), 0])

    def _toggle_pause(self) -> None:
        self.traces.toggle_pause()
        self._pause_btn.setText(
            "Resume" if self.traces.is_paused else "Pause"
        )

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
                    stability = max(
                        0, min(100, 100 * (1 - min(var / 500, 1)))
                    )
                    noise = float(np.std(col))
                    if len(col) > 5:
                        drift = float(np.polyfit(np.arange(len(col)), col, 1)[0])
                    else:
                        drift = 0.0
                    per_sensor.append(
                        {"variance": var, "stability": stability,
                         "noise": noise, "drift": drift}
                    )
                self.update_quality_metrics(per_sensor)
                self.signal_quality.update_from_metrics(per_sensor)
                self.device_health.update_health(per_sensor)

    def reset(self) -> None:
        self.traces.reset()
        self.substance.clear()
        self.signal_quality.reset_warmup()
        self.competition.reset()
        self._sample_count_label.setText("Samples: 0")
