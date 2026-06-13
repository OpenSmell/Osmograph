from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QProgressBar
from PySide6.QtGui import QFont

from Osmograph.ui.theme import COLORS


class SubstanceDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        header = QLabel("Prediction")
        header.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold;")
        layout.addWidget(header)

        self._substance_label = QLabel("---")
        self._substance_label.setStyleSheet(
            f"color: {COLORS['text_bright']}; font-size: 22px; font-weight: bold;"
        )
        self._substance_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(self._substance_label)

        conf_layout = QHBoxLayout()
        conf_label = QLabel("Confidence")
        conf_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 9px;")
        conf_layout.addWidget(conf_label)
        conf_layout.addStretch()

        self._conf_value = QLabel("0.00")
        self._conf_value.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 11px;")
        conf_layout.addWidget(self._conf_value)
        layout.addLayout(conf_layout)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #222;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff4444, stop:0.5 #ffaa00, stop:1 #00ff88);
                border-radius: 4px;
            }
        """)
        layout.addWidget(self._progress_bar)

        self._warning_label = QLabel("")
        self._warning_label.setStyleSheet(f"color: {COLORS['warning']}; font-size: 9px;")
        self._warning_label.setWordWrap(True)
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

        layout.addStretch()

        self.setToolTip("Predicted substance from OpenSmell analysis")

    def update_prediction(self, substance: str, confidence: float, warning: str = "") -> None:
        self._substance_label.setText(substance if substance else "Unknown")
        conf_pct = min(int(confidence * 100), 100)
        self._conf_value.setText(f"{confidence:.4f}")
        self._progress_bar.setValue(conf_pct)

        if warning:
            self._warning_label.setText(warning)
            self._warning_label.setVisible(True)
        else:
            self._warning_label.setVisible(False)

    def clear(self) -> None:
        self._substance_label.setText("---")
        self._conf_value.setText("0.00")
        self._progress_bar.setValue(0)
        self._warning_label.setVisible(False)
