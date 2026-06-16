from typing import Optional, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QMessageBox, QProgressBar, QDialogButtonBox,
    QListWidget, QListWidgetItem, QWidget, QApplication,
)

from Osmograph.ui.theme import COLORS, DARK_STYLESHEET


class InfoDialog(QDialog):
    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setStyleSheet(DARK_STYLESHEET)

        layout = QVBoxLayout(self)
        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {COLORS['text_bright']}; font-size: 13px; padding: 16px;")
        layout.addWidget(msg)

        btn = QPushButton("OK")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignCenter)


class ConfirmDialog(QDialog):
    def __init__(self, title: str, message: str, confirm_text: str = "Confirm", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setStyleSheet(DARK_STYLESHEET)

        layout = QVBoxLayout(self)
        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {COLORS['text_bright']}; font-size: 13px; padding: 16px;")
        layout.addWidget(msg)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton(confirm_text)
        confirm_btn.setStyleSheet(
            f"background-color: {COLORS['accent_red']}; color: black; font-weight: bold;"
        )
        confirm_btn.clicked.connect(self.accept)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)


class ProgressDialog(QDialog):
    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(450)
        self.setStyleSheet(DARK_STYLESHEET)
        self.setModal(True)

        layout = QVBoxLayout(self)

        self._msg_label = QLabel(message)
        self._msg_label.setStyleSheet(f"color: {COLORS['text_bright']}; padding: 8px;")
        layout.addWidget(self._msg_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(20)
        layout.addWidget(self._progress)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        layout.addWidget(self._status_label)

    def set_progress(self, value: int, status: str = "") -> None:
        self._progress.setValue(value)
        if status:
            self._status_label.setText(status)
        QApplication.processEvents()

    def set_message(self, message: str) -> None:
        self._msg_label.setText(message)


class PresetSelectionDialog(QDialog):
    def __init__(self, presets: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Sensor Configuration")
        self.setMinimumWidth(450)
        self.setStyleSheet(DARK_STYLESHEET)

        self.selected_preset = presets[0] if presets else ""

        layout = QVBoxLayout(self)

        header = QLabel("Which sensor configuration is connected?")
        header.setStyleSheet(f"color: {COLORS['text_bright']}; font-size: 14px; font-weight: bold; padding: 8px;")
        layout.addWidget(header)

        self._combo = QComboBox()
        self._combo.addItems(presets)
        self._combo.currentTextChanged.connect(self._on_selection)
        layout.addWidget(self._combo)

        self._desc_label = QLabel("")
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet(f"color: {COLORS['text_dim']}; padding: 4px;")
        layout.addWidget(self._desc_label)

        btn_layout = QHBoxLayout()
        self._skip_btn = QPushButton("Skip (use existing firmware)")
        self._skip_btn.clicked.connect(self._on_skip)
        btn_layout.addWidget(self._skip_btn)

        self._flash_btn = QPushButton("Flash Firmware")
        self._flash_btn.setStyleSheet(
            f"background-color: {COLORS['accent_cyan']}; color: black; font-weight: bold;"
        )
        self._flash_btn.clicked.connect(self._on_flash)
        btn_layout.addWidget(self._flash_btn)
        layout.addLayout(btn_layout)

        self._on_selection(self.selected_preset)

    def _on_selection(self, text: str) -> None:
        self.selected_preset = text

    def _on_skip(self):
        self.selected_preset = ""
        self.accept()

    def _on_flash(self):
        self.accept()


class PinMappingDialog(QDialog):
    def __init__(self, sensors: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pin Mapper")
        self.setMinimumSize(500, 450)
        self.setStyleSheet(DARK_STYLESHEET)

        from Osmograph.sensor.pin_mapper import PinMapper
        from Osmograph.sensor.profiles import SensorProfiles

        self._sensors = sensors
        self._assignments: dict[str, int] = {}

        layout = QVBoxLayout(self)

        header = QLabel("Assign each sensor to a GPIO pin")
        header.setStyleSheet(f"color: {COLORS['text_bright']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        self._list = QListWidget()
        available_pins = PinMapper.get_available_adc_pins()

        for sensor in sensors:
            profile = SensorProfiles.get(sensor)
            default_pin = profile.default_pin if profile else available_pins[0]
            item = QListWidgetItem(f"{sensor} → GPIO {default_pin}")
            item.setData(Qt.UserRole, sensor)
            item.setData(Qt.UserRole + 1, default_pin)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self._list.addItem(item)
            self._assignments[sensor] = default_pin

        layout.addWidget(self._list)

        btn_layout = QHBoxLayout()
        self._auto_btn = QPushButton("Auto-assign")
        self._auto_btn.clicked.connect(self._auto_assign)
        btn_layout.addWidget(self._auto_btn)

        btn_layout.addStretch()

        ok_btn = QPushButton("Apply")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _auto_assign(self) -> None:
        from Osmograph.sensor.pin_mapper import PinMapper
        pm = PinMapper.autodetect_pins(self._sensors)
        self._assignments = pm.to_firmware_config()
        self._list.clear()
        for sensor, pin in self._assignments.items():
            item = QListWidgetItem(f"{sensor} → GPIO {pin}")
            item.setData(Qt.UserRole, sensor)
            item.setData(Qt.UserRole + 1, pin)
            self._list.addItem(item)

    @property
    def assignments(self) -> dict[str, int]:
        return self._assignments
