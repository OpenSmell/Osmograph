import sys
import time
import pickle
import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTabWidget, QGroupBox,
    QSpinBox, QDoubleSpinBox, QLineEdit, QFileDialog,
    QStatusBar, QMenuBar, QMenu, QFrame,
    QProgressBar, QSizePolicy, QInputDialog,
)
from PySide6.QtGui import QAction, QIcon

from Osmograph import __version__, __app_name__
from Osmograph.settings import get_settings, migrate_settings
from Osmograph.board import BoardDetector, FirmwareRepository, FlashingService
from Osmograph.sensor import SensorProfiles, PinMapper, PresetManager
from Osmograph.data import SerialReader, WifiReader, BleReader, DataValidator, CSVRecorder, SessionManager, SessionRecord
from Osmograph.viz import DashboardWidget
from Osmograph.viz.signal_quality import SignalLevel
from Osmograph.viz.realtime_classifier import RealtimeClassifier
from Osmograph.viz.train_tab import TrainTab
from Osmograph.substance_library import SubstanceLibrary
from Osmograph.burnin import BurnInTracker
from Osmograph.wizard import AdapterWizard
from Osmograph.plugins import PluginLoader
from Osmograph.ui.theme import COLORS, generate_stylesheet, get_manager as get_theme_manager
from Osmograph.ui.theme import THEME_MODES
from Osmograph.ui.dialogs import (
    InfoDialog, ConfirmDialog, ProgressDialog,
    PresetSelectionDialog, PinMappingDialog, AboutDialog,
)

logger = logging.getLogger(__name__)


class OsmographMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.resize(1100, 680)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(generate_stylesheet())

        self._theme_manager = get_theme_manager()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

        logo_path = Path(__file__).resolve().parent.parent / "opensmell_logo.png"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))

        self._settings = get_settings()
        migrate_settings()

        self._serial_reader = SerialReader(self)
        self._wifi_reader = WifiReader(self)
        self._wifi_reader.data_received.connect(self._on_data_received)
        self._wifi_reader.connection_changed.connect(self._on_connection_changed)
        self._wifi_reader.error_occurred.connect(self._on_error)

        self._ble_reader = BleReader(self)
        self._ble_reader.data_received.connect(self._on_data_received)
        self._ble_reader.connection_changed.connect(self._on_connection_changed)
        self._ble_reader.error_occurred.connect(self._on_error)
        self._ble_reader.devices_discovered.connect(self._on_ble_devices_discovered)

        self._burnin.tick.connect(self._on_burnin_tick)
        self._burnin.completed.connect(self._on_burnin_complete)

        self._tabs.currentChanged.connect(self._on_tab_changed)
        if hasattr(self, '_rec_tabs'):
            self._rec_tabs.currentChanged.connect(self._on_rec_sub_tab_changed)

    def _restore_geometry(self):
        geom = self._settings.value("ui/geometry")
        if geom:
            self.restoreGeometry(geom)
        state = self._settings.value("ui/window_state")
        if state:
            self.restoreState(state)

    def _initial_discover(self):
        self._refresh_ports()
        preset = PresetManager.get(self._active_preset)
        if preset:
            self._classifier.n_sensors = preset.sensor_count
        boards = BoardDetector.detect()
        if boards:
            known = [b for b in boards if b.is_known]
            if known:
                self._board_label.setText(f"{known[0].label} on {known[0].port}")
                self._board_label.setStyleSheet(f"color: {COLORS['accent_green']}; padding: 0 8px;")

        plugin_dir = Path.home() / ".config" / "Osmograph" / "plugins"
        self._plugin_loader = PluginLoader(plugin_dir)
        self._discover_plugins()
        self._scan_classifiers()
        self._refresh_session_list()

        if self._session_manager.get_record_count() == 0:
            self._status.showMessage(
                "Welcome! Connect your ESP32, then click Detect Board → Connect to start.", 10000
            )

        last_port = self._settings.value("serial/port", "")
        if last_port and last_port in [self._port_combo.itemText(i) for i in range(self._port_combo.count())]:
            self._port_combo.setCurrentText(last_port)
            if self._connection_mode == "Serial":
                QTimer.singleShot(500, self._connect_device)

    def _scan_classifiers(self):
        classifiers_dir = Path(__file__).resolve().parent / "classifiers"
        self._classifier_combo.blockSignals(True)
        self._classifier_combo.clear()
        self._classifier_combo.addItem("None", None)
        if classifiers_dir.exists():
            for pkl_path in sorted(classifiers_dir.glob("*.pkl")):
                display = self._read_classifier_display_name(pkl_path)
                self._classifier_combo.addItem(display, str(pkl_path))
        self._classifier_combo.blockSignals(False)
        last = self._settings.value("classifier/selected", "")
        if last:
            idx = self._classifier_combo.findData(last)
            if idx >= 0:
                self._classifier_combo.setCurrentIndex(idx)

    def _read_classifier_display_name(self, pkl_path: Path) -> str:
        try:
            with open(pkl_path, "rb") as f:
                model = pickle.load(f)
            name = model.get("classifier_name", "")
            classes = model.get("classes", [])
            if name:
                suffix = f" ({len(classes)} classes)" if classes else ""
                return name + suffix
        except Exception:
            pass
        return pkl_path.stem.replace("_", " ").title()

    def _on_classifier_change(self, idx: int):
        pkl_path = self._classifier_combo.itemData(idx)
        if pkl_path:
            self._classifier.load(pkl_path)
            self._settings.setValue("classifier/selected", pkl_path)
            if hasattr(self, '_window_size_spin'):
                self._window_size_spin.setValue(self._classifier.window_size)
            self._update_clf_info()
            self.dashboard.set_classifier(self._classifier)
            self._status.showMessage(
                f"Loaded: {self._classifier.classifier_name} "
                f"({len(self._classifier.classes)} classes)", 5000
            )
        else:
            self._classifier.unload()
            self._settings.setValue("classifier/selected", "")
            self._update_clf_info()
            self.dashboard.set_classifier(self._classifier)
            self._status.showMessage("Classifier unloaded", 3000)

    def _update_clf_info(self):
        if hasattr(self, '_clf_info_label'):
            clf = self._classifier
            if clf.is_loaded:
                text = (f"Active: {clf.classifier_name} | "
                        f"{len(clf.classes)} classes: {', '.join(clf.classes)} | "
                        f"Window: {clf.window_size} | "
                        f"Threshold: {clf.confidence_threshold:.2f}")
            else:
                text = "Active: None"
            self._clf_info_label.setText(text)

    def _on_window_size_change(self, value: int):
        self._classifier.window_size = value
        self._status.showMessage(f"Window size: {value} samples (~{value//2}s at 2 Hz)", 3000)
        self._update_clf_info()

    def _on_conf_threshold_change(self, value: float):
        self._classifier.confidence_threshold = value
        self._status.showMessage(f"Confidence threshold: {value:.2f}", 3000)
        self._update_clf_info()

    def _open_training_wizard(self):
        self._train_tab.set_sensor_count(self._classifier.n_sensors)
        self._train_tab.set_recordings(self._session_manager.get_records())
        self._tabs.setCurrentWidget(self._recordings_tab)
        self._rec_tabs.setCurrentWidget(self._train_tab)

    def _open_adapter_wizard(self):
        self._tabs.setCurrentWidget(self._recordings_tab)
        self._rec_tabs.setCurrentWidget(self._adapter_tab)

    def _on_train_complete(self, model_path: str):
        self._scan_classifiers()
        idx = self._classifier_combo.findData(model_path)
        if idx >= 0:
            self._classifier_combo.setCurrentIndex(idx)
            self.dashboard.set_classifier(self._classifier)
            self._status.showMessage(
                f"Classifier trained and loaded: {self._classifier.classifier_name}", 5000
            )
        else:
            self._status.showMessage("Training complete! Select your classifier from the dropdown.", 5000)

    def _refresh_ports(self):
        from Osmograph.board.detector import BoardDetector
        ports = BoardDetector.list_ports()
        current = self._port_combo.currentText()
        self._port_combo.clear()
        self._port_combo.addItems(ports)
        if current in ports:
            self._port_combo.setCurrentText(current)
        elif ports:
            self._port_combo.setCurrentText(ports[0])

    def _detect_board(self):
        boards = BoardDetector.detect()
        if not boards:
            InfoDialog("No Board", "No board detected. Connect your ESP32 via USB.").exec()
            self._board_label.setText("No board")
            self._board_label.setStyleSheet(f"color: {COLORS['accent_red']}; padding: 0 8px;")
            return

        known = [b for b in boards if b.is_known]
        if known:
            board = known[0]
            self._board_label.setText(f"{board.label} on {board.port}")
            self._board_label.setStyleSheet(f"color: {COLORS['accent_green']}; padding: 0 8px;")
            self._port_combo.setCurrentText(board.port)

            preset_names = PresetManager.get_preset_names()
            dialog = PresetSelectionDialog(preset_names, self)
            if dialog.exec() and dialog.selected_preset:
                self._active_preset = dialog.selected_preset
                self._preset_combo.setCurrentText(dialog.selected_preset)
                self._flash_firmware(board.port, dialog.selected_preset)

            BoardDetector.auto_fix_permissions(board.port)

            connect = ConfirmDialog("Connect Serial", f"Connect to {board.port}?", "Connect")
            if connect.exec():
                self._connect_serial_to_port(board.port)
        else:
            self._board_label.setText(f"{len(boards)} unknown device(s)")
            self._board_label.setStyleSheet(f"color: {COLORS['accent_orange']}; padding: 0 8px;")

    def _flash_firmware(self, port: str, preset_name: str):
        fw_image = FirmwareRepository.get(preset_name)
        if not fw_image:
            InfoDialog("Firmware Not Found", f"No firmware for preset: {preset_name}").exec()
            return

        if not Path(fw_image.path).exists():
            InfoDialog(
                "Firmware Missing",
                f"Firmware binary not found at:\n  {fw_image.path}\n\n"
                "Run 'make firmware' from the Osmograph project root to build it."
            ).exec()
            return

        dialog = ProgressDialog("Flashing Firmware", f"Flashing {preset_name} to {port}...")
        dialog.show()

        def on_progress(pct: int):
            dialog.set_progress(pct)

        success, msg = self._flasher.flash(port, fw_image.path, progress_callback=on_progress)
        dialog.close()

        if success:
            InfoDialog("Flash Complete", msg).exec()
            self._status.showMessage(f"Flashed {preset_name} to {port}", 5000)
            QTimer.singleShot(2000, lambda: self._connect_serial_to_port(port))
        else:
            InfoDialog("Flash Failed", msg).exec()

    def _flash_firmware_dialog(self):
        port = self._port_combo.currentText()
        if not port:
            InfoDialog("No Port", "Select a serial port first.").exec()
            return

        preset_names = PresetManager.get_preset_names()
        dialog = PresetSelectionDialog(preset_names, self)
        if dialog.exec() and dialog.selected_preset:
            self._flash_firmware(port, dialog.selected_preset)

    def _on_preset_change(self, preset_name: str):
        self._active_preset = preset_name
        preset = PresetManager.get(preset_name)
        if preset:
            self.dashboard.set_sensor_count(preset.sensor_count)
            self._classifier.n_sensors = preset.sensor_count
            self._train_tab.set_sensor_count(preset.sensor_count)
            self._validator.reset()

    def _on_mode_change(self, mode: str):
        self._connection_mode = mode
        if mode == "WiFi":
            self._detect_btn.setText("Discover WiFi")
            self._detect_btn.setToolTip("Scan network for ESP32 boards via mDNS")
            self._port_combo.setToolTip("Enter the ESP32's IP address (e.g. 192.168.1.42)")
            self._port_combo.setPlaceholderText("IP address...")
            self._port_combo.clear()
            self._port_combo.setEditable(True)
        elif mode == "Bluetooth":
            self._detect_btn.setText("Scan BLE")
            self._detect_btn.setToolTip("Scan for nearby Osmograph-BLE devices")
            self._port_combo.setToolTip("Enter the BLE device MAC address")
            self._port_combo.setPlaceholderText("MAC address...")
            self._port_combo.clear()
            self._port_combo.setEditable(True)
        else:
            self._detect_btn.setText("Detect Board")
            self._detect_btn.setToolTip("Scan USB ports for connected ESP32 boards")
            self._port_combo.setToolTip("Select the serial port your board is connected to")
            self._port_combo.clearEditText()
            self._refresh_ports()

    def _detect_or_discover(self):
        if self._connection_mode == "WiFi":
            self._discover_wifi()
        elif self._connection_mode == "Bluetooth":
            self._scan_ble()
        else:
            self._detect_board()

    def _discover_wifi(self):
        try:
            from Osmograph.data.wifi_reader import discover_via_mdns
            self._status.showMessage("Scanning network for ESP32 boards...", 3000)
            devices = discover_via_mdns(timeout=3)
            if devices:
                self._port_combo.clear()
                for d in devices:
                    label = f"{d['host']}:{d['port']}" if d.get("name") else d['host']
                    self._port_combo.addItem(label)
                    self._port_combo.setItemData(self._port_combo.count() - 1, d['host'], Qt.UserRole)
                self._port_combo.setCurrentText(devices[0]['host'])
                self._board_label.setText(f"Found {len(devices)} device(s) on network")
                self._board_label.setStyleSheet(f"color: {COLORS['accent_green']}; padding: 0 8px;")
                self._status.showMessage(f"Found {len(devices)} ESP32 board(s) on network", 5000)
            else:
                self._board_label.setText("No WiFi devices found")
                self._board_label.setStyleSheet(f"color: {COLORS['accent_red']}; padding: 0 8px;")
                InfoDialog("No Devices", "No ESP32 boards found on the network.\nMake sure your board is connected to WiFi and broadcasting via mDNS as _osmograph._tcp.").exec()
        except ImportError:
            InfoDialog("zeroconf Not Installed",
                "Install zeroconf to use WiFi discovery:\n\n"
                "  pip install zeroconf\n\n"
                "Alternatively, enter the IP address manually.").exec()

    def _connect_device(self):
        addr = self._port_combo.currentText().strip()
        if not addr:
            InfoDialog("No Address", "No serial port or IP address selected.").exec()
            return
        if self._connection_mode == "WiFi":
            self._connect_wifi_to(addr)
        elif self._connection_mode == "Bluetooth":
            self._connect_ble_to(addr)
        else:
            self._connect_serial_to_port(addr)

    def _connect_serial_to_port(self, port: str):
        baud = int(self._baud_spin.currentText())
        self._serial_reader.configure(port, baud)
        self._serial_reader.set_validator(self._validator.validate)
        ok, msg = self._serial_reader.connect()
        if ok:
            self._serial_reader.start_streaming()
            self._status.showMessage(f"Connected to {port} @ {baud}", 3000)
        else:
            InfoDialog("Connection Failed", msg).exec()

    def _connect_wifi_to(self, host: str):
        port = 8080
        if ":" in host:
            host, port_str = host.split(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                pass
        self._wifi_reader.configure(host, port)
        ok, msg = self._wifi_reader.connect()
        if ok:
            self._wifi_reader.start_streaming()
            self._status.showMessage(f"Connected to {host}:{port} via WiFi", 3000)
        else:
            InfoDialog("Connection Failed", msg).exec()

    def _scan_ble(self):
        try:
            import bleak
        except ImportError:
            InfoDialog("bleak Not Installed",
                "Install bleak for BLE support:\n\n"
                "  pip install bleak\n\n"
                "Alternatively, enter the MAC address manually.").exec()
            return
        self._status.showMessage("Scanning for BLE devices...", 5000)
        self._ble_reader.start_scan(timeout=5)

    def _connect_ble_to(self, address: str):
        if "(" in address and ")" in address:
            address = address.split("(")[-1].rstrip(")")
        self._ble_reader.stop_streaming()
        self._ble_reader.wait(2000)
        self._ble_reader.configure(address)
        self._ble_reader._running = True
        self._ble_reader.start()
        self._status.showMessage(f"Connecting to BLE: {address}", 3000)

    def _disconnect_device(self):
        self._serial_reader.stop_streaming()
        self._serial_reader.disconnect()
        self._wifi_reader.stop_streaming()
        self._wifi_reader.disconnect()
        self._ble_reader.stop_streaming()

    def _toggle_demo(self, checked: bool) -> None:
        if checked:
            self._demo_btn.setText("Stop Demo")
            self._demo_btn.setStyleSheet(
                f"background-color: {COLORS['warning']}; color: #000; font-weight: bold;"
            )
            self._demo_timer.start(200)
            self._connected = True
            self.dashboard.set_connected(True)
            self.dashboard.start_timers()
            self._status.showMessage("Demo mode active — generating synthetic sensor data", 3000)
        else:
            self._demo_timer.stop()
            self._demo_btn.setText("Demo")
            self._demo_btn.setStyleSheet("")
            self._connected = False
            self.dashboard.set_connected(False)
            self._status.showMessage("Demo mode stopped", 3000)

    def _generate_demo_sample(self) -> None:
        t = time.time()
        preset = PresetManager.get(self._active_preset)
        n = preset.sensor_count if preset else 6
        noise = np.random.normal(0, 0.02, n).astype(np.float32)
        signals = np.array([
            0.5 + 0.3 * np.sin(t * 0.3 + i * 1.2) + 0.1 * np.sin(t * 0.7 + i * 0.8)
            for i in range(n)
        ], dtype=np.float32)
        sample = signals + noise
        self._on_data_received(sample)

    def _toggle_connection(self):
        if self._connected:
            self._disconnect_device()
        else:
            self._connect_device()

    def _on_connection_changed(self, connected: bool, msg: str):
        self._connected = connected
        if connected:
            self._serial_label.setText("Connected")
            self._serial_label.setStyleSheet(f"color: {COLORS['accent_green']}; padding: 0 8px;")
            self._connect_btn.setText("Disconnect")
            self._connect_btn.setStyleSheet(
                f"background-color: {COLORS['accent_red']}; color: {COLORS['accent_text']}; font-weight: bold;"
            )
            self.dashboard.set_connected(True)
            self._settings.setValue("serial/port", self._port_combo.currentText())
        else:
            self._serial_label.setText("Disconnected")
            self._serial_label.setStyleSheet(f"color: {COLORS['text_dim']}; padding: 0 8px;")
            self._connect_btn.setText("Connect")
            self._connect_btn.setStyleSheet("")
            self.dashboard.set_connected(False)

    def _on_error(self, msg: str):
        self._status.showMessage(f"Connection error: {msg}", 5000)

    def _on_ble_devices_discovered(self, devices: list):
        if not devices:
            self._board_label.setText("No BLE devices found")
            self._board_label.setStyleSheet(f"color: {COLORS['accent_red']}; padding: 0 8px;")
            return
        self._port_combo.clear()
        for d in devices:
            label = f"{d['name']} ({d['address']})"
            self._port_combo.addItem(label)
            self._port_combo.setItemData(self._port_combo.count() - 1, d['address'], Qt.UserRole)
        self._port_combo.setCurrentIndex(0)
        self._board_label.setText(f"Found {len(devices)} BLE device(s)")
        self._board_label.setStyleSheet(f"color: {COLORS['accent_green']}; padding: 0 8px;")
        self._status.showMessage(f"Found {len(devices)} Osmograph-BLE device(s)", 5000)

    def _on_bootloader(self):
        pass

    def _on_tab_changed(self, index: int):
        widget = self._tabs.widget(index)
        if widget is self._recordings_tab:
            self._on_rec_sub_tab_changed(self._rec_tabs.currentIndex())

    def _on_rec_sub_tab_changed(self, index: int):
        sub = self._rec_tabs.currentWidget()
        if sub is self._train_tab:
            self._train_tab.set_recordings(self._session_manager.get_records())
        elif sub is self._adapter_tab:
            self._refresh_session_list()

    def _on_data_received(self, sample: np.ndarray):
        self.dashboard.add_sample(sample)
        if self._recorder.is_recording:
            self._recorder.write_sample(sample)

    def _start_recording_dialog(self):
        label = self._label_input.text().strip()
        if not label:
            InfoDialog("No Label", "Enter a substance label before recording.").exec()
            self._label_input.setFocus()
            return

        duration = self._duration_spin.value()

        def on_complete(filepath, elapsed):
            self._recording_bar.setVisible(False)
            self._recording_timer.stop()
            self._record_btn.setEnabled(True)
            self._record_btn.setText("Record")
            self.dashboard.signal_quality.set_recording(False)

            record = SessionRecord(
                substance=label,
                csv_path=str(filepath),
                timestamp=time.time(),
                duration_sec=elapsed,
                sensor_count=PresetManager.get(self._active_preset).sensor_count if PresetManager.get(self._active_preset) else 6,
                preset_name=self._active_preset,
                label=label,
            )
            self._session_manager.add_record(record)
            self._refresh_session_list()
            self._status.showMessage(f"Recording saved: {filepath.name}", 5000)

            self._adapter_wizard.add_recording(label, str(filepath))
            self._update_adapter_status()

            self._process_with_opensmell(str(filepath))

        filepath = self._recorder.start(label=label, duration_sec=duration, on_complete=on_complete)
        self._recording_label.setText(f"Recording: {label}")
        self._recording_start = time.time()
        self._recording_duration = duration
        self._recording_countdown.setText(f"{duration}s remaining")
        self._recording_bar.setVisible(True)
        self._recording_timer.start(500)
        self._record_btn.setEnabled(False)
        self._record_btn.setText("Recording...")
        self.dashboard.signal_quality.set_recording(True)

    def _update_recording_countdown(self) -> None:
        if not self._recorder.is_recording:
            self._recording_timer.stop()
            self._recording_bar.setVisible(False)
            return
        elapsed = time.time() - self._recording_start
        remaining = max(0, self._recording_duration - elapsed)
        self._recording_countdown.setText(f"{remaining:.0f}s remaining")

    def _cancel_recording(self) -> None:
        self._recorder.cancel()
        self._recording_timer.stop()
        self._recording_bar.setVisible(False)
        self._record_btn.setEnabled(True)
        self._record_btn.setText("Record")
        self.dashboard.signal_quality.set_recording(False)

    def _refresh_session_list(self):
        from PySide6.QtWidgets import QListWidgetItem

        self._session_list.clear()
        filter_text = self._substance_filter.currentText()
        records = self._session_manager.get_records()
        if filter_text != "All substances":
            records = [r for r in records if r.substance == filter_text]

        substances = self._session_manager.get_recorded_substances()
        self._substance_filter.clear()
        self._substance_filter.addItem("All substances")
        self._substance_filter.addItems(substances)

        for r in records:
            item = QListWidgetItem(
                f"[{r.datetime_str}] {r.substance} ({r.duration_sec:.0f}s) -> {Path(r.csv_path).name}"
            )
            item.setData(Qt.UserRole, r.file_id)
            self._session_list.addItem(item)

        self._auto_process_pending(records)

    def _auto_process_pending(self, records: list) -> None:
        unprocessed = [r for r in records if not r.opensmell_result and Path(r.csv_path).exists()]
        if unprocessed:
            newest = unprocessed[-1]
            try:
                first_line = Path(newest.csv_path).read_text().strip().split("\n")[0]
                if "MQ135" in first_line or "MQ3" in first_line:
                    logger.info(f"Skipping old-format CSV (pre-v2 columns): {newest.csv_path}")
                    newest.opensmell_result = {"substance": "Unknown", "confidence": 0.0, "warning": "Old CSV format, re-record"}
                    self._session_manager.add_record(newest)
                    return
            except Exception:
                pass
            result = self._process_with_opensmell(newest.csv_path)
            if result:
                newest.opensmell_result = result
                self._session_manager.add_record(newest)

    def _import_csv_session(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import CSV Recording", "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            substance, ok = QInputDialog.getText(
                self, "Import CSV", "Substance name:",
                QLineEdit.Normal, ""
            )
            if not ok or not substance.strip():
                substance = "unknown"

            import csv
            from datetime import datetime

            with open(path) as f:
                reader = csv.reader(f)
                header = next(reader, [])
                rows = list(reader)
                row_count = len(rows)

            timestamps = None
            if "timestamp" in [c.lower() for c in header]:
                ts_col = next(i for i, c in enumerate(header) if c.lower() == "timestamp")
                timestamps = [float(r[ts_col]) for r in rows if len(r) > ts_col and r[ts_col].strip()]
            duration = (timestamps[-1] - timestamps[0]) if timestamps and len(timestamps) > 1 else row_count / 2.0

            rec = SessionRecord(
                substance=substance.strip(),
                csv_path=path,
                timestamp=time.time(),
                duration_sec=duration,
                sensor_count=6,
                preset_name=self._active_preset or "Default",
                label=substance.strip(),
            )
            self._session_manager.add_record(rec)
            self._refresh_session_list()
            self._status.showMessage(f"Imported: {Path(path).name} ({substance.strip()})", 5000)
        except Exception as e:
            InfoDialog("Import Failed", str(e)).exec()

    def _process_selected_session(self):
        item = self._session_list.currentItem()
        if not item:
            return
        file_id = item.data(Qt.UserRole)
        records = self._session_manager.get_records()
        target = next((r for r in records if r.file_id == file_id), None)
        if target is None:
            return

        result = self._process_with_opensmell(target.csv_path)
        if result:
            target.opensmell_result = result
            self._session_manager.add_record(target)
        else:
            InfoDialog("OpenSmell Not Found", "Could not import opensmell.\nInstall with: pip install opensmell").exec()

    def _process_with_opensmell(self, csv_path: str) -> Optional[dict]:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "opensmell"))
            import opensmell
            result = opensmell.process(csv_path)

            chemprint = getattr(result, "chemoprint", None)
            if chemprint is not None:
                self.dashboard.update_chemprint(chemprint)

            features = getattr(result, "features", None)
            feat_names = getattr(result, "feature_names", None)
            if features is not None and feat_names is not None:
                feat_dict = dict(zip(feat_names, features))
                label = (result.substance or "") if hasattr(result, "substance") else ""
                self.dashboard.update_fingerprint(feat_dict, label)

            substance = (result.substance or "Unknown") if hasattr(result, "substance") else "Unknown"
            confidence = (result.confidence or 0.0) if hasattr(result, "confidence") else 0.0
            warning = getattr(result, "warning", "")

            self.dashboard.update_prediction(substance, confidence, warning or "")
            self._status.showMessage(
                f"OpenSmell: {substance} (conf={confidence:.3f})", 5000
            )
            return {
                "substance": substance,
                "confidence": confidence,
                "warning": warning,
            }
        except ImportError:
            return None
        except Exception as e:
            logger.warning(f"OpenSmell process failed: {e}")
            return None

    def _delete_selected_session(self):
        item = self._session_list.currentItem()
        if not item:
            return
        file_id = item.data(Qt.UserRole)
        confirm = ConfirmDialog("Delete Session", "Delete this recording permanently?", "Delete")
        if confirm.exec():
            self._session_manager.remove_record(file_id)
            self._refresh_session_list()

    def _export_fingerprint(self) -> None:
        item = self._session_list.currentItem()
        if not item:
            InfoDialog("No Selection", "Select a session recording first.").exec()
            return
        file_id = item.data(Qt.UserRole)
        records = self._session_manager.get_records()
        target = next((r for r in records if r.file_id == file_id), None)
        if not target or not Path(target.csv_path).exists():
            InfoDialog("File Not Found", "The recording file could not be found.").exec()
            return

        try:
            import opensmell
            from opensmell import features as _f
            import json, csv
            from datetime import datetime

            raw = opensmell.load_recording(target.csv_path)
            feat_dict = _f.extract_all_framework_features(raw)
            metadata = {
                "app": __app_name__,
                "version": __version__,
                "timestamp": datetime.fromtimestamp(target.timestamp).isoformat(),
                "substance": target.substance,
                "duration_sec": target.duration_sec,
                "preset": target.preset_name,
                "sensor_count": target.sensor_count,
                "n_features": len(feat_dict),
            }

            path, _ = QFileDialog.getSaveFileName(
                self, "Export Fingerprint",
                f"fingerprint_{target.substance}_{target.file_id}",
                "JSON (*.json);;CSV (*.csv)",
            )
            if not path:
                return

            if path.endswith(".csv"):
                with open(path, "w", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(["feature", "value"])
                    for k in sorted(feat_dict.keys()):
                        w.writerow([k, feat_dict[k]])
            else:
                export = {"metadata": metadata, "features": {}}
                for k in sorted(feat_dict.keys()):
                    v = feat_dict[k]
                    export["features"][k] = float(v) if isinstance(v, (np.floating, float)) else int(v) if isinstance(v, (np.integer, int)) else v
                with open(path, "w") as f:
                    json.dump(export, f, indent=2)

            self._status.showMessage(f"Fingerprint exported: {path}", 5000)
        except Exception as e:
            InfoDialog("Export Failed", str(e)).exec()

    def _export_sessions(self):
        path = QFileDialog.getExistingDirectory(self, "Export Sessions To")
        if not path:
            return
        import shutil
        count = 0
        for r in self._session_manager.get_records():
            src = Path(r.csv_path)
            if src.exists():
                shutil.copy2(str(src), str(Path(path) / src.name))
                count += 1
        InfoDialog("Export Complete", f"Exported {count} files to {path}").exec()

    def _load_adapter_from_sessions(self):
        records = self._session_manager.get_records_for_adapter_training()
        if not records:
            InfoDialog("No Recordings", "No session recordings found. Record some substances first.").exec()
            return

        self._adapter_wizard.clear_recordings()
        self._adapter_records.clear()

        for r in records:
            if Path(r.csv_path).exists():
                self._adapter_wizard.add_recording(r.substance, r.csv_path)
                from PySide6.QtWidgets import QListWidgetItem
                item = QListWidgetItem(f"{r.substance} -> {Path(r.csv_path).name}")
                self._adapter_records.addItem(item)

        self._update_adapter_status()

    def _clear_adapter_records(self):
        self._adapter_wizard.clear_recordings()
        self._adapter_records.clear()
        self._update_adapter_status()

    def _update_adapter_status(self):
        count = self._adapter_wizard.recording_count
        substances = self._adapter_wizard.unique_substance_count
        ready = self._adapter_wizard.is_ready
        self._adapter_status.setText(
            f"Recordings: {count}/3 minimum | Substances: {substances}/2 minimum"
        )
        self._train_btn.setEnabled(ready)

    def _train_adapter(self):
        dialog = ProgressDialog("Training Adapter", "Training on recorded substances...")
        dialog.show()

        def on_progress(pct: int):
            dialog.set_progress(pct)

        def on_complete(result: dict):
            dialog.close()
            if result.get("success"):
                sim = result.get("cosine_similarity", 0.0)
                self._adapter_similarity.setText(
                    f"Cosine similarity: {sim:.4f} | Readiness: {'GOOD' if sim > 0.8 else 'FAIR' if sim > 0.6 else 'LOW'}"
                )
                InfoDialog("Training Complete",
                    f"Adapter trained on {result['recording_count']} recordings.\n"
                    f"Substances: {', '.join(result['substances_trained'])}\n"
                    f"Cosine similarity: {sim:.4f}\n"
                    f"Model saved to: {result['model_path']}"
                ).exec()
            else:
                InfoDialog("Training Failed", result.get("error", "Unknown error")).exec()

        self._adapter_wizard.set_progress_callback(on_progress)
        self._adapter_wizard.set_complete_callback(on_complete)
        self._adapter_wizard.train()

    def _on_burnin_tick(self, elapsed: int):
        if self._burnin.is_paused:
            self._burnin_status.setText("Burn-in: PAUSED")
            return
        remaining = self._burnin.remaining_seconds
        h, rem = divmod(remaining, 3600)
        m, s = divmod(rem, 60)
        text = f"{h:02d}:{m:02d}:{s:02d} remaining"
        self._burnin_status.setText(f"Burn-in: {text}")
        self._burnin_progress.setValue(int(self._burnin.progress * 100))

        if self._burnin.is_complete:
            self.dashboard.signal_quality.set_level(SignalLevel.READY)

    def _on_burnin_complete(self):
        self._status.showMessage("Burn-in complete! Sensors are ready.", 10000)
        self._burnin_status.setText("Burn-in: COMPLETE")
        self._burnin_status.setStyleSheet(f"color: {COLORS['accent_green']}; font-size: 24px; font-weight: bold;")
        self._burnin_start_btn.setText("Completed")

    def _toggle_burnin(self):
        if self._burnin.is_running and not self._burnin.is_paused:
            self._burnin.pause()
            self._burnin_start_btn.setText("Resume")
            self._status.showMessage("Burn-in paused", 3000)
        elif self._burnin.is_paused:
            self._burnin.resume()
            self._burnin_start_btn.setText("Stop Burn-In")
            self._status.showMessage("Burn-in resumed", 3000)
        else:
            self._start_burnin()

    def _start_burnin(self):
        hours = self._burnin_hours_spin.value()
        self._burnin.set_burnin_hours(hours)
        self._burnin.reset(hours)
        self._burnin.start()
        self._burnin_start_btn.setText("Stop Burn-In")
        self._status.showMessage(f"Burn-in started: {hours}h", 5000)

    def _reset_burnin(self):
        confirm = ConfirmDialog("Reset Burn-In", "Reset the burn-in timer to 0?", "Reset")
        if confirm.exec():
            hours = self._burnin_hours_spin.value()
            self._burnin.reset(hours)
            self._burnin_start_btn.setText("Start Burn-In")

    def _on_burnin_hours_change(self, hours: float):
        pass

    def _browse_save_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if path:
            self._save_dir_input.setText(path)
            self._settings.setValue("data/save_dir", path)
            self._recorder = CSVRecorder(path)
            self._session_manager.set_data_dir(path)
            self._session_manager._load_index()

    def _open_pin_mapper(self):
        preset = PresetManager.get(self._active_preset)
        sensors = preset.sensors if preset else SensorProfiles.list_models()
        dialog = PinMappingDialog(sensors, self)
        if dialog.exec() and dialog.assignments:
            from Osmograph.board.compiler import FirmwareCompiler
            pins = [dialog.assignments.get(s, 34) for s in sensors]
            output_dir = Path.home() / ".cache" / "Osmograph" / "firmware" / f"custom_{self._active_preset.replace(' ', '_')}"
            path = FirmwareCompiler.export_sketch(
                output_dir=output_dir,
                pins=pins,
            )
            InfoDialog("Firmware Compiled",
                f"PlatformIO project created at:\n{path}\n\n"
                f"Open this folder in VS Code with the PlatformIO extension, "
                f"build and upload to your ESP32.\n\n"
                f"The firmware works over USB Serial AND WiFi simultaneously.\n"
                f"WiFi network: OSMOGRAPH-XXXX (no password)").exec()

    def _discover_plugins(self):
        self._plugin_loader.discover()
        self._reload_plugins()

    def _reload_plugins(self):
        from PySide6.QtWidgets import QTableWidgetItem

        plugins = self._plugin_loader.reload_all()
        self._plugin_table.setRowCount(len(plugins))
        for i, info in enumerate(plugins):
            self._plugin_table.setItem(i, 0, QTableWidgetItem(info.name))
            self._plugin_table.setItem(i, 1, QTableWidgetItem(info.version))
            self._plugin_table.setItem(i, 2, QTableWidgetItem(info.description))
            status = "Loaded" if info.loaded else f"Error: {info.error}"
            self._plugin_table.setItem(i, 3, QTableWidgetItem(status))

    def _open_plugins_folder(self):
        plugin_dir = Path.home() / ".config" / "Osmograph" / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        import subprocess
        try:
            subprocess.run(["xdg-open", str(plugin_dir)], check=False)
        except FileNotFoundError:
            try:
                subprocess.run(["open", str(plugin_dir)], check=False)
            except FileNotFoundError:
                subprocess.run(["explorer", str(plugin_dir)], check=False)

    def _toggle_theme(self) -> None:
        new_mode = self._theme_manager.toggle()
        label = "HUD (Dark)" if new_mode == "dark" else "Clean (Light)"
        self._status.showMessage(f"Theme: {label}", 3000)

        for action in self.menuBar().actions():
            if action.text() == "&View":
                for a in action.menu().actions():
                    if "Switch to" in a.text():
                        mode_label = "Light" if self._theme_manager.is_dark() else "Dark"
                        a.setText(f"Switch to {mode_label} Theme")

    def _on_theme_changed(self) -> None:
        self.setStyleSheet(generate_stylesheet())
        self._toolbar.setStyleSheet(f"background-color: {COLORS['bg_secondary']}; border-radius: 4px;")
        self._status.setStyleSheet(f"background-color: {COLORS['bg_secondary']}; color: {COLORS['text_dim']};")
        self._board_label.setStyleSheet(f"color: {COLORS['accent_orange']}; padding: 0 8px;")
        self._serial_label.setStyleSheet(f"color: {COLORS['text_dim']}; padding: 0 8px;")
        self._recording_bar.setStyleSheet(f"background-color: {COLORS['bg_secondary']}; border-radius: 6px;")
        self.dashboard.update_theme()

    def _open_docs(self) -> None:
        docs_path = Path(__file__).resolve().parent.parent.parent / "docs" / "index.html"
        if docs_path.exists():
            import subprocess
            try:
                subprocess.run(["xdg-open", str(docs_path)], check=False)
            except FileNotFoundError:
                try:
                    subprocess.run(["open", str(docs_path)], check=False)
                except FileNotFoundError:
                    subprocess.run(["explorer", str(docs_path)], check=False)
        else:
            InfoDialog("Docs Not Found", f"Documentation not found at:\n{docs_path}").exec()

    def _show_about(self):
        from Osmograph.ui.theme import COLORS as C
        logo_path = Path(__file__).resolve().parent.parent / "opensmell_logo.png"
        AboutDialog(
            f"About {__app_name__}",
            logo_path if logo_path.exists() else None,
        ).exec()

    def closeEvent(self, event):
        self._serial_reader.stop_streaming()
        self._serial_reader.cleanup()
        self._wifi_reader.stop_streaming()
        self._wifi_reader.cleanup()
        self._ble_reader.stop_streaming()
        self._ble_reader.cleanup()
        self._recorder.cancel()
        self._burnin.stop()

        self._settings.setValue("ui/geometry", self.saveGeometry())
        self._settings.setValue("ui/window_state", self.saveState())
        self._settings.sync()

        event.accept()


def main():
    cache_dir = Path.home() / ".cache" / "Osmograph"
    cache_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(cache_dir / "osmograph.log", mode="a"),
        ],
    )

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("OpenSmell")
    app.setStyle("Fusion")

    window = OsmographMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
