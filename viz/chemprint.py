import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

import pyqtgraph as pg

from Osmograph.ui.theme import COLORS

DIM_GROUPS = [
    ("Base properties", 0, 12, "#00ffff"),
    ("Topological indices", 12, 15, "#ff00ff"),
    ("Functional groups", 15, 29, "#adff2f"),
]

DIM_LABELS = [f"d{i}" for i in range(29)]


class ChemprintBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._chemprint = np.zeros(29, dtype=np.float32)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Chemoprint (29-dim)")
        title.setStyleSheet(f"color: {COLORS['text_bright']}; font-weight: bold; font-size: 13px; padding: 4px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.plot_widget = pg.PlotWidget(background=COLORS["bg_dark"])
        self.plot_widget.setLabel("bottom", "Dimension", color=COLORS["text_dim"])
        self.plot_widget.setLabel("left", "Activation", color=COLORS["text_dim"])
        self.plot_widget.setMouseEnabled(False, False)
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.getAxis("left").setTextPen(COLORS["text_dim"])
        self.plot_widget.getAxis("bottom").setTextPen(COLORS["text_dim"])
        self.plot_widget.showGrid(x=False, y=True, alpha=0.1)
        self.plot_widget.setMaximumHeight(120)

        self._bar_graph = pg.BarGraphItem(
            x=np.arange(29),
            height=np.zeros(29),
            width=0.7,
        )
        self.plot_widget.addItem(self._bar_graph)
        self.plot_widget.setXRange(-0.5, 28.5)

        self._legend_label = QLabel("Base | Topo | FnGroups")
        self._legend_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 9px; padding: 2px;")
        self._legend_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._legend_label)
        layout.addWidget(self.plot_widget)

    def update_chemprint(self, chemprint: np.ndarray) -> None:
        self._chemprint = chemprint.copy() if chemprint is not None else np.zeros(29)

        brushes = []
        for i in range(29):
            color = "#666666"
            for _, start, end, c in DIM_GROUPS:
                if start <= i < end:
                    color = c
                    break
            brushes.append(pg.mkColor(color))

        self.plot_widget.clear()
        self._bar_graph = pg.BarGraphItem(
            x=np.arange(29),
            height=self._chemprint,
            width=0.7,
            brushes=brushes,
        )
        self.plot_widget.addItem(self._bar_graph)
        self.plot_widget.setXRange(-0.5, 28.5)
        self.plot_widget.enableAutoRange(axis=pg.ViewBox.YAxis)

        legend_html = " | ".join(
            f'<span style="color:{c};">{name}</span>'
            for name, _, _, c in DIM_GROUPS
        )
        self._legend_label.setText(legend_html)

    def clear(self) -> None:
        self._chemprint = np.zeros(29, dtype=np.float32)
        self.plot_widget.clear()
        self._bar_graph = pg.BarGraphItem(
            x=np.arange(29),
            height=np.zeros(29),
            width=0.7,
        )
        self.plot_widget.addItem(self._bar_graph)
        self.plot_widget.setXRange(-0.5, 28.5)

    @property
    def chemprint(self) -> np.ndarray:
        return self._chemprint
