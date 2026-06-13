from enum import Enum
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PySide6.QtGui import QPainter, QColor, QBrush, QPen


class SignalLevel(Enum):
    WARMING_UP = "Warming Up"
    UNSTABLE = "Unstable"
    STABLE = "Stable"
    READY = "Ready"
    RECORDING = "Recording"

    @property
    def color(self) -> str:
        return {
            SignalLevel.WARMING_UP: "#ff4444",
            SignalLevel.UNSTABLE: "#ffaa00",
            SignalLevel.STABLE: "#88ff00",
            SignalLevel.READY: "#00ff88",
            SignalLevel.RECORDING: "#ff00ff",
        }[self]

    @property
    def color_hex(self) -> QColor:
        return QColor(self.color)


class _TrafficLight(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = SignalLevel.WARMING_UP
        self.setFixedSize(24, 24)

    def set_level(self, level: SignalLevel) -> None:
        self._level = level
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = self._level.color_hex
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(150), 2))
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.drawEllipse(rect)
        painter.end()


class SignalQualityIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = SignalLevel.WARMING_UP
        self._warmup_seconds = 0
        self._warmup_target = 300
        self._noise_level = 1.0
        self._stable_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        header = QLabel("Signal Quality")
        header.setStyleSheet("color: #aaaaaa; font-size: 10px; font-weight: bold;")
        layout.addWidget(header)

        indicator_layout = QHBoxLayout()

        self._light = _TrafficLight()
        indicator_layout.addWidget(self._light)

        self._status_label = QLabel(self._level.value)
        self._status_label.setStyleSheet(f"color: {self._level.color}; font-size: 14px; font-weight: bold;")
        indicator_layout.addWidget(self._status_label)
        indicator_layout.addStretch()
        layout.addLayout(indicator_layout)

        self._detail_label = QLabel("")
        self._detail_label.setStyleSheet("color: #666666; font-size: 9px;")
        layout.addWidget(self._detail_label)

        self._skip_btn = QPushButton("Skip Warm-up")
        self._skip_btn.setFixedHeight(20)
        self._skip_btn.setStyleSheet(
            "font-size: 9px; padding: 0 8px; background: #555; color: #ccc; border-radius: 3px;"
        )
        self._skip_btn.clicked.connect(self._skip_warmup)
        layout.addWidget(self._skip_btn)

        self.setToolTip("Shows sensor warm-up status and signal stability")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start_timers(self):
        self._timer.start(1000)

    def _tick(self) -> None:
        if self._level == SignalLevel.WARMING_UP:
            self._warmup_seconds += 1
            elapsed = self._warmup_seconds
            mins, secs = divmod(elapsed, 60)
            self._detail_label.setText(f"Stabilising... {mins}:{secs:02d}")
        elif self._level == SignalLevel.READY or self._level == SignalLevel.STABLE:
            self._detail_label.setText("Signal stable")

    def set_level(self, level: SignalLevel) -> None:
        self._level = level
        self._light.set_level(level)
        self._status_label.setText(level.value)
        self._status_label.setStyleSheet(f"color: {level.color}; font-size: 14px; font-weight: bold;")
        self._skip_btn.setVisible(level == SignalLevel.WARMING_UP)

    def set_noise(self, noise: float) -> None:
        self._noise_level = noise
        if self._level == SignalLevel.READY or self._level == SignalLevel.STABLE:
            if noise > 15.0:
                self.set_level(SignalLevel.UNSTABLE)
            elif noise > 5.0:
                self.set_level(SignalLevel.STABLE)
            else:
                self.set_level(SignalLevel.READY)

    def update_from_metrics(self, metrics: list[dict]) -> None:
        if self._level == SignalLevel.WARMING_UP and len(metrics) >= 3:
            all_stable = all(m.get("stability", 0) > 80 for m in metrics)
            if all_stable:
                self._stable_count += 1
                if self._stable_count >= 3:
                    self.set_level(SignalLevel.READY)
                    self._detail_label.setText("Signal stable")
            else:
                self._stable_count = 0

    def set_recording(self, recording: bool) -> None:
        if recording:
            self.set_level(SignalLevel.RECORDING)

    @property
    def level(self) -> SignalLevel:
        return self._level

    def _skip_warmup(self) -> None:
        self._warmup_seconds = self._warmup_target
        self._detail_label.setText("Warm-up skipped")
        self.set_level(SignalLevel.READY)

    def reset_warmup(self) -> None:
        self._warmup_seconds = 0
        self._stable_count = 0
        self.set_level(SignalLevel.WARMING_UP)
