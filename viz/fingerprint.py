import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
import pyqtgraph as pg

from Osmograph.ui.theme import COLORS

FINGERPRINT_AXES = [
    "Amplitude",
    "Rise Time",
    "Decay Time",
    "AUC",
    "Endpoint",
    "Saturation",
    "Selectivity",
    "Channels",
]

AXIS_SHORT = ["AMP", "RISE", "DECAY", "AUC", "END", "SAT", "SEL", "CH"]


def _compute_radar_vector(features: dict) -> np.ndarray:
    vec = np.zeros(8, dtype=np.float32)

    ch_count = 6
    amps = []
    rises = []
    decays = []
    aucs = []
    ends = []
    sats = []

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

    vec[0] = float(np.mean(amps)) if amps else 0.0
    vec[1] = float(np.mean(rises)) if rises else 0.0
    vec[2] = float(np.mean(decays)) if decays else 0.0
    vec[3] = float(np.mean(aucs)) if aucs else 0.0
    vec[4] = float(np.mean(ends)) if ends else 0.0
    vec[5] = float(np.mean(sats)) if sats else 0.0

    ratios = []
    active = [ch for ch in range(ch_count)
              if features.get(f"ch{ch}_da_relative_amplitude", 0) > 0]
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            ai = features.get(f"ch{active[i]}_da_relative_amplitude", 0)
            aj = features.get(f"ch{active[j]}_da_relative_amplitude", 0)
            if aj > 0:
                ratios.append(abs(ai / aj - 1.0))
    vec[6] = float(np.mean(ratios)) if ratios else 0.0

    vec[7] = float(len(active)) / max(ch_count, 1)

    return vec


class RadarFingerprintWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._vectors = []
        self._labels = []
        self._colors = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Fingerprint")
        title.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-weight: 600; font-size: 12px; padding: 4px;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.plot = pg.PlotWidget(background=COLORS.get("canvas_bg", COLORS["bg_primary"]))
        self.plot.setAspectLocked(True)
        self.plot.setMouseEnabled(False, False)
        self.plot.setMenuEnabled(False)
        self.plot.hideAxis("bottom")
        self.plot.hideAxis("left")
        self.plot.setMinimumHeight(180)
        layout.addWidget(self.plot)

        self._legend = QLabel("")
        self._legend.setAlignment(Qt.AlignCenter)
        self._legend.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; padding: 2px;")
        layout.addWidget(self._legend)

        self._scatter = None
        self._n_axes = 8

    def set_fingerprint(self, features: dict, label: str = "", color: str = "#4a9eff") -> None:
        vec = _compute_radar_vector(features)
        self._vectors = [vec]
        self._labels = [label] if label else [""]
        self._colors = [color]
        self._redraw()

    def add_fingerprint(self, features: dict, label: str = "", color: str = "") -> None:
        if not color:
            palette = ["#4a9eff", "#34d399", "#fbbf24", "#ef4444", "#a78bfa", "#f472b6"]
            color = palette[len(self._vectors) % len(palette)]
        vec = _compute_radar_vector(features)
        self._vectors.append(vec)
        self._labels.append(label)
        self._colors.append(color)
        self._redraw()

    def clear_overlay(self) -> None:
        self._vectors = []
        self._labels = []
        self._colors = []
        self._redraw()

    def _redraw(self) -> None:
        self.plot.clear()

        n = self._n_axes
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
        angles = np.concatenate([angles, [angles[0]]])

        bg_brush = pg.mkBrush(COLORS.get("canvas_bg", COLORS["bg_primary"]))
        self.plot.setBackground(bg_brush)

        grid_pen = pg.mkPen(COLORS["border"], width=1, style=Qt.DashLine)
        for level in [0.25, 0.5, 0.75, 1.0]:
            pts = np.column_stack([level * np.cos(angles), level * np.sin(angles)])
            self.plot.plot(pts, pen=grid_pen)

        for i, (angle, label) in enumerate(zip(angles[:n], AXIS_SHORT)):
            x = 1.15 * np.cos(angle)
            y = 1.15 * np.sin(angle)
            text = pg.TextItem(
                text=label,
                color=COLORS["text_muted"],
                anchor=(0.5, 0.5),
            )
            text.setPos(x, y)
            self.plot.addItem(text)

        if not self._vectors:
            empty = pg.TextItem(
                text="No fingerprint",
                color=COLORS["text_muted"],
                anchor=(0.5, 0.5),
            )
            empty.setPos(0, 0)
            self.plot.addItem(empty)
            self._legend.setText("")
            return

        for vi, (vec, label, color) in enumerate(zip(self._vectors, self._labels, self._colors)):
            norm = vec.copy()
            mx = np.max(norm) if np.max(norm) > 0 else 1.0
            norm = norm / mx
            pts = np.column_stack([norm * np.cos(angles), norm * np.sin(angles)])

            fill = pg.mkBrush(pg.mkColor(color))
            fill.setAlpha(30)
            self.plot.plot(pts, pen=pg.mkPen(color, width=2), fillLevel=0, brush=fill)

            for i in range(n):
                x = norm[i] * np.cos(angles[i])
                y = norm[i] * np.sin(angles[i])
                dot = pg.ScatterPlotItem(
                    [x], [y],
                    pen=pg.mkPen(None),
                    brush=pg.mkBrush(color),
                    size=6,
                )
                self.plot.addItem(dot)

        legend_parts = []
        for vi, (label, color) in enumerate(zip(self._labels, self._colors)):
            name = label if label else f"#{vi + 1}"
            legend_parts.append(f'<span style="color:{color};">\u25cf {name}</span>')
        self._legend.setText(" | ".join(legend_parts))

        self.plot.setXRange(-1.4, 1.4)
        self.plot.setYRange(-1.4, 1.4)

    def update_theme(self) -> None:
        bg = COLORS.get("canvas_bg", COLORS["bg_primary"])
        self.plot.setBackground(bg)
        self._legend.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; padding: 2px;")
        self._redraw()
