from enum import Enum
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtGui import QPainter, QColor, QBrush, QPen

from Osmograph.ui.theme import COLORS as C


class SignalLevel(Enum):
    WARMING_UP = "Warm up"
    UNSTABLE = "Unstable"
    STABLE = "Stable"
    READY = "Ready"
    RECORDING = "Recording"

    @property
    def color(self) -> str:
        return {
            SignalLevel.WARMING_UP: C["error"],
            SignalLevel.UNSTABLE: C["warning"],
            SignalLevel.STABLE: C["success"],
            SignalLevel.READY: C["accent"],
            SignalLevel.RECORDING: C["accent_hover"],
        }[self]

    @property
    def color_hex(self) -> QColor:
        return QColor(self.color)


class _QualityDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(C["error"])
        self.setFixedSize(10, 10)

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(self._color))
        p.setPen(QPen(self._color.darker(130), 1))
        p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        p.end()


class SignalQualityIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = SignalLevel.WARMING_UP
        self._warmup_seconds = 0
        self._warmup_target = 300
        self._noise_level = 1.0
        self._stable_count = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        self._dot = _QualityDot()
        self._dot.set_color(self._level.color)
        layout.addWidget(self._dot)

        self._status_label = QLabel(self._level.value)
        self._status_label.setStyleSheet(
            f"color: {self._level.color}; font-size: 11px; font-weight: 600;"
        )
        layout.addWidget(self._status_label)

        self._detail_label = QLabel("")
        self._detail_label.setStyleSheet(f"color: {C['text_muted']}; font-size: 9px;")
        layout.addWidget(self._detail_label)

        layout.addStretch()

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
            self._detail_label.setText(f"{mins}:{secs:02d}")
        elif self._level in (SignalLevel.READY, SignalLevel.STABLE):
            self._detail_label.setText("Stable")

    def set_level(self, level: SignalLevel) -> None:
        self._level = level
        self._dot.set_color(level.color)
        self._status_label.setText(level.value)
        self._status_label.setStyleSheet(
            f"color: {level.color}; font-size: 11px; font-weight: 600;"
        )

    def set_noise(self, noise: float) -> None:
        self._noise_level = noise
        if self._level in (SignalLevel.READY, SignalLevel.STABLE):
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
                    self._detail_label.setText("Stable")
            else:
                self._stable_count = 0

    def set_recording(self, recording: bool) -> None:
        if recording:
            self.set_level(SignalLevel.RECORDING)
        elif self._level == SignalLevel.RECORDING:
            self.set_level(SignalLevel.READY)

    @property
    def level(self) -> SignalLevel:
        return self._level

    def reset_warmup(self) -> None:
        self._warmup_seconds = 0
        self._stable_count = 0
        self.set_level(SignalLevel.WARMING_UP)

    def update_theme(self) -> None:
        self._detail_label.setStyleSheet(f"color: {C['text_muted']}; font-size: 9px;")
        self._dot.set_color(self._level.color)
