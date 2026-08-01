import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtGui import QPainter, QColor, QLinearGradient
import pyqtgraph as pg

from Osmograph.ui.theme import COLORS

SENSOR_NAMES = ["MQ-135", "MQ-3", "MQ-6", "MQ-7", "MQ-4", "MQ-8"]
FEATURE_LABELS = ["AMP", "RISE", "DECAY", "AUC", "END", "SAT", "SEL", "CH"]

FEATURE_FULL = [
    "Amplitude", "Rise Time", "Decay Time", "Area Under Curve",
    "Endpoint Δ", "Saturation", "Selectivity", "Channels",
]


def _sensor_radar_vector(amplitudes: list[float]) -> np.ndarray:
    arr = np.array(amplitudes[:6], dtype=np.float32)
    mx = float(arr.max()) if arr.max() > 0 else 1.0
    return arr / mx


class _FeatureBarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = [0.0] * 8
        self.setMinimumWidth(140)
        self.setMinimumHeight(130)

    def set_data(self, values: list[float]) -> None:
        self._values = values[:8] if values else [0.0] * 8
        while len(self._values) < 8:
            self._values.append(0.0)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        if w < 20 or h < 20:
            p.end()
            return

        p.fillRect(self.rect(), QColor(COLORS["bg_primary"]))

        n = 8
        margin_l = 52
        margin_r = 44
        margin_t = 4
        margin_b = 4
        gap = 2
        row_h = (h - margin_t - margin_b - (n - 1) * gap) / n
        if row_h < 8:
            row_h = 8

        bar_area = w - margin_l - margin_r
        max_val = max(self._values) if max(self._values) > 0 else 1.0

        bar_color = COLORS["accent"]
        c = QColor(bar_color)

        for i in range(8):
            val = max(0.0, self._values[i])
            bar_w = max(2, (val / max_val) * bar_area)
            y = margin_t + i * (row_h + gap)
            x0 = margin_l

            gradient = QLinearGradient(x0, y, x0 + bar_w, y)
            gradient.setColorAt(0.0, c)
            gradient.setColorAt(1.0, c.lighter(150))
            p.setBrush(gradient)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x0, y, bar_w, row_h), 2, 2)

            p.setPen(QColor(COLORS["text_secondary"]))
            p.drawText(QRectF(2, y, margin_l - 6, row_h),
                       Qt.AlignRight | Qt.AlignVCenter,
                       FEATURE_LABELS[i])

            p.setPen(QColor(COLORS["text_muted"]))
            p.drawText(QRectF(x0 + bar_w + 4, y, margin_r - 8, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"{val:.2f}")

        p.end()


class FingerprintPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._feat_data = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 0)

        title = QLabel("Fingerprint")
        title.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 10px; font-weight: 600;"
        )
        header.addWidget(title)
        header.addStretch()

        self._sensor_label = QLabel("")
        self._sensor_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 9px;"
        )
        header.addWidget(self._sensor_label)

        layout.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(4)

        self.plot = pg.PlotWidget(background=COLORS["bg_primary"])
        self.plot.setAspectLocked(True)
        self.plot.setMouseEnabled(False, False)
        self.plot.setMenuEnabled(False)
        self.plot.hideAxis("bottom")
        self.plot.hideAxis("left")
        self.plot.setMinimumHeight(120)
        self.plot.setMinimumWidth(200)
        content.addWidget(self.plot, 3)

        self.bars = _FeatureBarChart()
        content.addWidget(self.bars, 2)

        layout.addLayout(content)

        self._legend = QLabel("")
        self._legend.setAlignment(Qt.AlignCenter)
        self._legend.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 9px; padding: 1px;"
        )
        layout.addWidget(self._legend)

        self._draw_sensor_radar([0.0] * 6)

    def set_fingerprint(self, features: dict, label: str = "") -> None:
        vec = self._compute_feature_vec(features)
        self.bars.set_data(vec.tolist())
        self._legend.setText(
            f'<span style="color:{COLORS["accent"]};">\u25cf {label or "current"}</span>'
        )

    def set_from_amplitudes(self, amplitudes: list[float]) -> None:
        self._sensor_label.setText("")
        self._draw_sensor_radar(amplitudes)

    def add_fingerprint(self, features: dict, label: str = "", color: str = "") -> None:
        pass

    def clear_overlay(self) -> None:
        pass

    def _compute_feature_vec(self, features: dict) -> np.ndarray:
        ch_count = 6
        amps, rises, decays, aucs, ends, sats = [], [], [], [], [], []
        for ch in range(ch_count):
            amp = features.get(f"ch{ch}_da_relative_amplitude", 0)
            if amp > 0:
                amps.append(amp)
            rise = features.get(f"ch{ch}_da_rise_time", -1)
            if rise > 0:
                rises.append(rise)
            decay = features.get(f"ch{ch}_da_decay_time", -1)
            if decay > 0:
                decays.append(decay)
            auc = features.get(f"ch{ch}_da_auc", 0)
            if auc > 0:
                aucs.append(auc)
            end = features.get(f"ch{ch}_da_endpoint_delta", 0)
            ends.append(abs(end))
            sat = features.get(f"ch{ch}_advanced_saturation_index", 0)
            if sat > 0:
                sats.append(sat)

        vec = np.zeros(8, dtype=np.float32)
        vec[0] = float(np.mean(amps)) if amps else 0.0
        vec[1] = float(np.mean(rises)) if rises else 0.0
        vec[2] = float(np.mean(decays)) if decays else 0.0
        vec[3] = float(np.mean(aucs)) if aucs else 0.0
        vec[4] = float(np.mean(ends)) if ends else 0.0
        vec[5] = float(np.mean(sats)) if sats else 0.0

        ratios = []
        active = [
            ch for ch in range(ch_count)
            if features.get(f"ch{ch}_da_relative_amplitude", 0) > 0
        ]
        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                ai = features.get(f"ch{active[i]}_da_relative_amplitude", 0)
                aj = features.get(f"ch{active[j]}_da_relative_amplitude", 0)
                if aj > 0:
                    ratios.append(abs(ai / aj - 1.0))
        vec[6] = float(np.mean(ratios)) if ratios else 0.0
        vec[7] = float(len(active)) / max(ch_count, 1)

        mx = float(np.max(vec)) if np.max(vec) > 0 else 1.0
        return vec / mx

    def _draw_sensor_radar(self, amplitudes: list[float]) -> None:
        self.plot.clear()
        n = 6
        labels = [s[:3].upper() for s in SENSOR_NAMES]
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
        angles_closed = np.concatenate([angles, [angles[0]]])

        self.plot.setBackground(COLORS["bg_primary"])

        grid_pen = pg.mkPen(COLORS["border"], width=1, style=Qt.DashLine)
        for level in [0.25, 0.5, 0.75, 1.0]:
            pts = np.column_stack(
                [level * np.cos(angles_closed), level * np.sin(angles_closed)]
            )
            self.plot.plot(pts, pen=grid_pen)

        sensor_colors = ["#4fc3f7", "#81c784", "#ffb74d", "#e57373", "#ba68c8", "#f06292"]
        for i, (angle, label) in enumerate(zip(angles, labels)):
            x = 1.15 * np.cos(angle)
            y = 1.15 * np.sin(angle)
            c = sensor_colors[i % len(sensor_colors)]
            text = pg.TextItem(
                text=label, color=c, anchor=(0.5, 0.5),
            )
            text.setPos(x, y)
            self.plot.addItem(text)

        vec = _sensor_radar_vector(amplitudes)
        mx = float(np.max(vec)) if np.max(vec) > 0 else 1.0
        norm = vec / mx if mx > 0 else vec
        norm_closed = np.concatenate([norm, [norm[0]]])
        pts = np.column_stack(
            [norm_closed * np.cos(angles_closed),
             norm_closed * np.sin(angles_closed)]
        )

        c = pg.mkColor(COLORS["accent"])
        c.setAlpha(30)
        fill = pg.mkBrush(c)
        self.plot.plot(
            pts, pen=pg.mkPen(COLORS["accent"], width=2), fillLevel=0, brush=fill
        )

        for i in range(n):
            x = norm[i] * np.cos(angles[i])
            y = norm[i] * np.sin(angles[i])
            dot = pg.ScatterPlotItem(
                [x], [y],
                pen=pg.mkPen(None),
                brush=pg.mkBrush(sensor_colors[i % len(sensor_colors)]),
                size=6,
            )
            self.plot.addItem(dot)

        self.plot.setXRange(-1.4, 1.4)
        self.plot.setYRange(-1.4, 1.4)

    def update_theme(self) -> None:
        self.plot.setBackground(COLORS["bg_primary"])
        self.bars.update()
        self._draw_sensor_radar(self.bars._values if hasattr(self.bars, '_values') else [0.0]*6)
