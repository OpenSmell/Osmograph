from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout, QFrame

from Osmograph.ui.theme import COLORS


class DeviceHealthWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._visible = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(2)

        header = QLabel("Sensor Health")
        header.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 9px; font-weight: bold;"
        )
        layout.addWidget(header)

        row = QHBoxLayout()
        row.setSpacing(12)

        self._rows = []
        for i in range(6):
            col = QVBoxLayout()
            col.setSpacing(1)

            label = QLabel(f"CH{i+1}")
            label.setAlignment(Qt.AlignCenter)
            label.setFixedWidth(48)
            label.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 8px;"
            )
            col.addWidget(label)

            dot = QLabel("\u25cf")
            dot.setAlignment(Qt.AlignCenter)
            dot.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
            col.addWidget(dot)

            val = QLabel("--")
            val.setAlignment(Qt.AlignCenter)
            val.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 8px;"
            )
            col.addWidget(val)

            self._rows.append({"label": label, "dot": dot, "val": val})
            row.addLayout(col)

        layout.addLayout(row)
        self.setVisible(False)

    def update_health(self, metrics: list[dict]) -> None:
        if not metrics:
            self.setVisible(False)
            return
        self.setVisible(True)
        self._visible = True

        for i, m in enumerate(metrics):
            if i >= 6:
                break
            noise = m.get("noise", 0)
            drift = abs(m.get("drift", 0))
            stability = m.get("stability", 0)

            if stability > 80 and noise < 0.5:
                color = COLORS["success"]
                status = "OK"
            elif stability > 50 and noise < 2.0:
                color = COLORS["warning"]
                status = "~"
            else:
                color = COLORS["error"]
                status = "!"

            self._rows[i]["dot"].setStyleSheet(f"color: {color}; font-size: 10px;")
            self._rows[i]["val"].setText(status)

    def update_theme(self) -> None:
        pass
