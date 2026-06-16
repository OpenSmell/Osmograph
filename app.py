import os
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
    QSpinBox, QDoubleSpinBox, QLineEdit, QMessageBox, QFileDialog,
    QStatusBar, QMenuBar, QMenu, QSystemTrayIcon, QStyle, QFrame,
    QProgressBar,
)
from PySide6.QtGui import QAction, QIcon

from Osmograph import __version__, __app_name__
from Osmograph.settings import get_settings, migrate_settings
from Osmograph.board import BoardDetector, FirmwareRepository, FlashingService
from Osmograph.sensor import SensorProfiles, PinMapper, PresetManager
from Osmograph.data import SerialReader, WifiReader, DataValidator, CSVRecorder, SessionManager, SessionRecord
from Osmograph.viz import DashboardWidget
from Osmograph.viz.signal_quality import SignalLevel
from Osmograph.viz.realtime_classifier import RealtimeClassifier
from Osmograph.viz.train_tab import TrainTab
from Osmograph.substance_library import SubstanceLibrary
from Osmograph.burnin import BurnInTracker
from Osmograph.wizard import AdapterWizard
from Osmograph.plugins import PluginLoader
from Osmograph.ui.theme import DARK_STYLESHEET, COLORS
from Osmograph.ui.dialogs import (
    InfoDialog, ConfirmDialog, ProgressDialog,
    PresetSelectionDialog, PinMappingDialog,
)

logger = logging.getLogger(__name__)


class OsmographMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.resize(1100, 680)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(DARK_STYLESHEET)

        self._settings = get_settings()
        migrate_settings()

        self._serial_reader = SerialReader(self)
        self._wifi_reader = WifiReader(self)
        self._connection_mode = "Serial"
        self._validator = DataValidator()
        self._recorder = CSVRecorder(self._settings.value("data/save_dir", ""))
        self._session_manager = SessionManager(self._settings.value("data/save_dir", ""))
        self._burnin = BurnInTracker(self)
        self._adapter_wizard = AdapterWizard()
        self._plugin_loader = PluginLoader()
        self._classifier = RealtimeClassifier()
        self._flasher = FlashingService()
        self._firmware_dir = Path(__file__).resolve().parent / "firmware"
        self._active_preset = ""
        self._connected = False
        self._recording_start = 0.0
        self._recording_duration = 0.0
        self._recording_timer = QTimer(self)
        self._recording_timer.timeout.connect(self._update_recording_countdown)

        FirmwareRepository.initialize(self._firmware_dir)
        self._setup_ui()
        self._connect_signals()
        self._restore_geometry()

    def showEvent(self, event):
        super().showEvent(event)
        self.dashboard.start_timers()
        self._initial_discover()
        self._refresh_ports()

    def _setup_ui(self):
        self._setup_menu_bar()
        self._setup_status_bar()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._toolbar = self._build_toolbar()
        layout.addWidget(self._toolbar)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self.dashboard = DashboardWidget()
        self.dashboard.set_classifier(self._classifier)
        self._tabs.addTab(self.dashboard, "Dashboard")
        self._tabs.setTabToolTip(0, "Live sensor traces, chemoprint, predictions")

        self._session_tab = self._build_session_tab()
        self._tabs.addTab(self._session_tab, "Sessions")
        self._tabs.setTabToolTip(1, "Browse, process, and manage recordings")

        self._train_tab = TrainTab(n_sensors=self._classifier.n_sensors)
        self._train_tab.training_complete.connect(self._on_train_complete)
        self._tabs.addTab(self._train_tab, "Train")
        self._tabs.setTabToolTip(2, "Train a real-time substance classifier from your recordings")

        self._adapter_tab = self._build_adapter_tab()
        self._tabs.addTab(self._adapter_tab, "Adapter")
        self._tabs.setTabToolTip(3, "Train a lightweight adapter on your samples")

        self._plugin_tab = self._build_plugin_tab()
        self._tabs.addTab(self._plugin_tab, "Plugins")
        self._tabs.setTabToolTip(4, "Manage OpenSmell plugins and model heads")

        self._settings_tab = self._build_settings_tab()
        self._tabs.addTab(self._settings_tab, "Settings")
        self._tabs.setTabToolTip(5, "Serial connection and data directory settings")

        self._burnin_tab = self._build_burnin_tab()
        self._tabs.addTab(self._burnin_tab, "Burn-In")
        self._tabs.setTabToolTip(6, "Track sensor burn-in time (24h recommended for new MQ sensors)")

        layout.addWidget(self._tabs)

        self._recording_bar = QWidget()
        self._recording_bar.setStyleSheet(
            f"background-color: {COLORS['bg_med']}; border-radius: 4px;"
        )
        rec_layout = QHBoxLayout(self._recording_bar)
        rec_layout.setContentsMargins(8, 4, 8, 4)
        self._recording_label = QLabel("")
        self._recording_label.setStyleSheet(
            f"color: {COLORS['accent_red']}; font-weight: bold; font-size: 11px;"
        )
        rec_layout.addWidget(self._recording_label)
        self._recording_countdown = QLabel("")
        self._recording_countdown.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px;"
        )
        rec_layout.addWidget(self._recording_countdown)
        rec_layout.addStretch()
        self._cancel_rec_btn = QPushButton("Cancel")
        self._cancel_rec_btn.setStyleSheet(
            f"background-color: {COLORS['accent_red']}; color: white; "
            f"font-weight: bold; font-size: 10px; padding: 2px 12px; border-radius: 3px;"
        )
        self._cancel_rec_btn.clicked.connect(self._cancel_recording)
        rec_layout.addWidget(self._cancel_rec_btn)
        self._recording_bar.setVisible(False)
        layout.addWidget(self._recording_bar)

    def _setup_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        record_action = QAction("&Record Session...", self)
        record_action.setShortcut("Ctrl+R")
        record_action.triggered.connect(self._start_recording_dialog)
        file_menu.addAction(record_action)

        export_action = QAction("&Export Sessions...", self)
        export_action.triggered.connect(self._export_sessions)
        file_menu.addAction(export_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        board_menu = menubar.addMenu("&Board")
        detect_action = QAction("&Detect / Discover", self)
        detect_action.setShortcut("Ctrl+D")
        detect_action.triggered.connect(self._detect_or_discover)
        board_menu.addAction(detect_action)

        flash_action = QAction("&Flash Firmware...", self)
        flash_action.setShortcut("Ctrl+F")
        flash_action.triggered.connect(self._flash_firmware_dialog)
        board_menu.addAction(flash_action)

        board_menu.addSeparator()
        connect_action = QAction("&Connect", self)
        connect_action.setShortcut("Ctrl+C")
        connect_action.triggered.connect(self._connect_device)
        board_menu.addAction(connect_action)

        disconnect_action = QAction("&Disconnect", self)
        disconnect_action.triggered.connect(self._disconnect_device)
        board_menu.addAction(disconnect_action)

        tools_menu = menubar.addMenu("&Tools")
        wizard_action = QAction("&Adapter Wizard", self)
        wizard_action.setShortcut("Ctrl+W")
        wizard_action.triggered.connect(lambda: self._tabs.setCurrentWidget(self._adapter_tab))
        tools_menu.addAction(wizard_action)

        pin_action = QAction("&Pin Mapper...", self)
        pin_action.triggered.connect(self._open_pin_mapper)
        tools_menu.addAction(pin_action)

        burnin_action = QAction("&Reset Burn-In Timer", self)
        burnin_action.triggered.connect(self._reset_burnin)
        tools_menu.addAction(burnin_action)

        view_menu = menubar.addMenu("&View")
        toggle_fullscreen = QAction("Toggle &Fullscreen", self)
        toggle_fullscreen.setShortcut("F11")
        toggle_fullscreen.triggered.connect(lambda: self.showFullScreen() if not self.isFullScreen() else self.showNormal())
        view_menu.addAction(toggle_fullscreen)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About Osmograph", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_status_bar(self):
        self._status = QStatusBar()
        self._status.setStyleSheet(f"background-color: {COLORS['bg_med']}; color: {COLORS['text_dim']};")
        self.setStatusBar(self._status)

        self._board_label = QLabel("No board detected")
        self._board_label.setStyleSheet(f"color: {COLORS['accent_orange']}; padding: 0 8px;")
        self._status.addPermanentWidget(self._board_label)

        self._serial_label = QLabel("Disconnected")
        self._serial_label.setStyleSheet(f"color: {COLORS['text_dim']}; padding: 0 8px;")
        self._status.addPermanentWidget(self._serial_label)

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {COLORS['bg_med']}; border-radius: 4px;")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Serial", "WiFi"])
        self._mode_combo.setFixedWidth(80)
        self._mode_combo.currentTextChanged.connect(self._on_mode_change)
        layout.addWidget(self._mode_combo)

        self._detect_btn = QPushButton("Detect Board")
        self._detect_btn.setToolTip("Scan USB ports for connected ESP32 boards")
        self._detect_btn.clicked.connect(self._detect_or_discover)
        layout.addWidget(self._detect_btn)

        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.setMinimumWidth(150)
        self._port_combo.setToolTip("Select the serial port your board is connected to")
        layout.addWidget(self._port_combo)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setToolTip("Open the serial connection to the selected port")
        self._connect_btn.clicked.connect(self._toggle_connection)
        layout.addWidget(self._connect_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {COLORS['border']};")
        layout.addWidget(sep)

        self._preset_combo = QComboBox()
        self._preset_combo.addItems(PresetManager.get_preset_names())
        self._preset_combo.setMinimumWidth(150)
        self._preset_combo.currentTextChanged.connect(self._on_preset_change)
        self._preset_combo.setToolTip("Choose your sensor configuration")
        layout.addWidget(QLabel("Preset:"))
        layout.addWidget(self._preset_combo)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet(f"color: {COLORS['border']};")
        layout.addWidget(sep2)

        self._classifier_combo = QComboBox()
        self._classifier_combo.setMinimumWidth(140)
        self._classifier_combo.setToolTip("Select a real-time classifier (.pkl)")
        self._classifier_combo.currentIndexChanged.connect(self._on_classifier_change)
        layout.addWidget(QLabel("Classifier:"))
        layout.addWidget(self._classifier_combo)

        self._train_clf_btn = QPushButton("Train...")
        self._train_clf_btn.setToolTip("Train a new classifier from your recordings")
        self._train_clf_btn.clicked.connect(self._open_training_wizard)
        layout.addWidget(self._train_clf_btn)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.VLine)
        sep3.setStyleSheet(f"color: {COLORS['border']};")
        layout.addWidget(sep3)

        self._label_input = QLineEdit()
        self._label_input.setPlaceholderText("Label (e.g. garlic)...")
        self._label_input.setMinimumWidth(130)
        self._label_input.setToolTip("Name the substance you are recording")
        layout.addWidget(self._label_input)

        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(10, 3600)
        self._duration_spin.setValue(60)
        self._duration_spin.setSuffix("s")
        self._duration_spin.setToolTip("How long to record (in seconds)")
        layout.addWidget(QLabel("Duration:"))
        layout.addWidget(self._duration_spin)

        self._record_btn = QPushButton("Record")
        self._record_btn.setStyleSheet(
            f"background-color: {COLORS['accent_red']}; color: white; font-weight: bold;"
        )
        self._record_btn.setToolTip("Start a recording session. Enter a label first!")
        self._record_btn.clicked.connect(self._start_recording_dialog)
        layout.addWidget(self._record_btn)

        return toolbar

    def _build_session_tab(self) -> QWidget:
        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        w = QWidget()
        layout = QVBoxLayout(w)

        toolbar = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Reload the session list from disk")
        refresh_btn.clicked.connect(self._refresh_session_list)
        toolbar.addWidget(refresh_btn)

        self._substance_filter = QComboBox()
        self._substance_filter.addItem("All substances")
        self._substance_filter.setToolTip("Filter recordings by substance")
        toolbar.addWidget(QLabel("Filter:"))
        toolbar.addWidget(self._substance_filter)

        process_btn = QPushButton("Process with OpenSmell")
        process_btn.setToolTip("Run OpenSmell analysis on the selected recording")
        process_btn.clicked.connect(self._process_selected_session)
        toolbar.addWidget(process_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setToolTip("Delete the selected recording permanently")
        delete_btn.clicked.connect(self._delete_selected_session)
        toolbar.addWidget(delete_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._session_list = QListWidget()
        layout.addWidget(self._session_list)

        return w

    def _build_adapter_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        header = QLabel("Adapter Training Wizard")
        header.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "Record 3-5 different substances to train a lightweight adapter. "
            "Osmograph will learn to distinguish your specific samples."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {COLORS['text_dim']}; padding: 4px;")
        layout.addWidget(desc)

        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        self._adapter_records = QListWidget()
        layout.addWidget(self._adapter_records)

        info_layout = QHBoxLayout()
        self._adapter_status = QLabel("Recordings: 0/3 minimum | Substances: 0/2 minimum")
        self._adapter_status.setStyleSheet(f"color: {COLORS['text_dim']};")
        info_layout.addWidget(self._adapter_status)

        self._adapter_similarity = QLabel("")
        self._adapter_similarity.setStyleSheet(f"color: {COLORS['accent_green']}; font-weight: bold;")
        info_layout.addWidget(self._adapter_similarity)
        info_layout.addStretch()
        layout.addLayout(info_layout)

        btn_layout = QHBoxLayout()
        load_btn = QPushButton("Load from Sessions")
        load_btn.setToolTip("Import existing recordings into the adapter training set")
        load_btn.clicked.connect(self._load_adapter_from_sessions)
        btn_layout.addWidget(load_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Remove all recordings from the adapter training set")
        clear_btn.clicked.connect(self._clear_adapter_records)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()

        self._train_btn = QPushButton("Train Adapter")
        self._train_btn.setStyleSheet(
            f"background-color: {COLORS['accent_cyan']}; color: black; font-weight: bold;"
        )
        self._train_btn.clicked.connect(self._train_adapter)
        self._train_btn.setEnabled(False)
        btn_layout.addWidget(self._train_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        return w

    def _build_plugin_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        header = QLabel("Plugin Manager")
        header.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "Drop `.head` model files or `.py` plugin scripts into the plugins folder. "
            "Discovered plugins appear below."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(desc)

        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView

        self._plugin_table = QTableWidget(0, 4)
        self._plugin_table.setHorizontalHeaderLabels(["Name", "Version", "Description", "Status"])
        self._plugin_table.horizontalHeader().setStretchLastSection(True)
        self._plugin_table.setAlternatingRowColors(True)
        layout.addWidget(self._plugin_table)

        btn_layout = QHBoxLayout()
        discover_btn = QPushButton("Discover Plugins")
        discover_btn.clicked.connect(self._discover_plugins)
        btn_layout.addWidget(discover_btn)

        reload_btn = QPushButton("Reload All")
        reload_btn.clicked.connect(self._reload_plugins)
        btn_layout.addWidget(reload_btn)

        btn_layout.addStretch()

        open_folder_btn = QPushButton("Open Plugins Folder")
        open_folder_btn.clicked.connect(self._open_plugins_folder)
        btn_layout.addWidget(open_folder_btn)

        layout.addLayout(btn_layout)

        return w

    def _build_burnin_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        header = QLabel("Burn-In Timer")
        header.setStyleSheet(f"color: {COLORS['accent_orange']}; font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "New MQ sensors need a 24-hour burn-in to stabilise. "
            "The timer runs in the background and persists across app restarts."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {COLORS['text_dim']}; padding: 4px;")
        layout.addWidget(desc)

        status_layout = QHBoxLayout()
        self._burnin_status = QLabel("Burn-in: --:--:-- remaining")
        self._burnin_status.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 24px; font-weight: bold;")
        status_layout.addWidget(self._burnin_status)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        progress_layout = QHBoxLayout()
        self._burnin_progress = QProgressBar()
        self._burnin_progress.setRange(0, 100)
        self._burnin_progress.setValue(0)
        self._burnin_progress.setTextVisible(True)
        self._burnin_progress.setFixedHeight(24)
        progress_layout.addWidget(self._burnin_progress)
        layout.addLayout(progress_layout)

        controls = QHBoxLayout()
        self._burnin_hours_spin = QDoubleSpinBox()
        self._burnin_hours_spin.setRange(1, 168)
        self._burnin_hours_spin.setValue(24)
        self._burnin_hours_spin.setSuffix(" h")
        self._burnin_hours_spin.valueChanged.connect(self._on_burnin_hours_change)
        controls.addWidget(QLabel("Duration:"))
        controls.addWidget(self._burnin_hours_spin)

        start_btn = QPushButton("Start Burn-In")
        start_btn.clicked.connect(self._start_burnin)
        controls.addWidget(start_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset_burnin)
        controls.addWidget(reset_btn)

        controls.addStretch()
        layout.addLayout(controls)

        layout.addStretch()
        return w

    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        serial_group = QGroupBox("Serial Connection")
        sg_layout = QVBoxLayout(serial_group)

        baud_layout = QHBoxLayout()
        baud_layout.addWidget(QLabel("Baud rate:"))
        self._baud_spin = QComboBox()
        self._baud_spin.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "921600"])
        self._baud_spin.setCurrentText("115200")
        baud_layout.addWidget(self._baud_spin)
        refresh_btn = QPushButton("Refresh Ports")
        refresh_btn.clicked.connect(self._refresh_ports)
        baud_layout.addWidget(refresh_btn)
        baud_layout.addStretch()
        sg_layout.addLayout(baud_layout)

        help_label = QLabel("Select port from the toolbar and click Connect.")
        help_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; padding: 4px;")
        sg_layout.addWidget(help_label)

        layout.addWidget(serial_group)

        clf_group = QGroupBox("Classifier")
        cg_layout = QVBoxLayout(clf_group)

        ws_layout = QHBoxLayout()
        ws_layout.addWidget(QLabel("Window size (samples):"))
        self._window_size_spin = QSpinBox()
        self._window_size_spin.setRange(20, 500)
        self._window_size_spin.setValue(self._classifier.window_size)
        self._window_size_spin.valueChanged.connect(self._on_window_size_change)
        ws_layout.addWidget(self._window_size_spin)
        ws_label = QLabel("Lower = faster, higher = more stable")
        ws_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        ws_layout.addWidget(ws_label)
        ws_layout.addStretch()
        cg_layout.addLayout(ws_layout)

        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("Confidence threshold:"))
        self._conf_threshold_spin = QDoubleSpinBox()
        self._conf_threshold_spin.setRange(0.0, 1.0)
        self._conf_threshold_spin.setSingleStep(0.05)
        self._conf_threshold_spin.setValue(self._classifier.confidence_threshold)
        self._conf_threshold_spin.valueChanged.connect(self._on_conf_threshold_change)
        conf_layout.addWidget(self._conf_threshold_spin)
        conf_label = QLabel("Below this → 'unknown'")
        conf_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        conf_layout.addWidget(conf_label)
        conf_layout.addStretch()
        cg_layout.addLayout(conf_layout)

        clf_info = QLabel(f"Active: {self._classifier.classifier_name}")
        clf_info.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; padding: 2px;")
        self._clf_info_label = clf_info
        cg_layout.addWidget(clf_info)

        layout.addWidget(clf_group)

        data_group = QGroupBox("Data Storage")
        dg_layout = QVBoxLayout(data_group)

        save_layout = QHBoxLayout()
        save_layout.addWidget(QLabel("Save directory:"))
        self._save_dir_input = QLineEdit(self._settings.value("data/save_dir", ""))
        save_layout.addWidget(self._save_dir_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_save_dir)
        save_layout.addWidget(browse_btn)
        dg_layout.addLayout(save_layout)

        layout.addWidget(data_group)
        layout.addStretch()

        return w

    def _connect_signals(self):
        self._serial_reader.data_received.connect(self._on_data_received)
        self._serial_reader.connection_changed.connect(self._on_connection_changed)
        self._serial_reader.error_occurred.connect(self._on_error)
        self._serial_reader.bootloader_detected.connect(self._on_bootloader)

        self._wifi_reader.data_received.connect(self._on_data_received)
        self._wifi_reader.connection_changed.connect(self._on_connection_changed)
        self._wifi_reader.error_occurred.connect(self._on_error)

        self._burnin.tick.connect(self._on_burnin_tick)
        self._burnin.completed.connect(self._on_burnin_complete)

        self._tabs.currentChanged.connect(self._on_tab_changed)

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
        self._tabs.setCurrentWidget(self._train_tab)

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
        else:
            self._detect_btn.setText("Detect Board")
            self._detect_btn.setToolTip("Scan USB ports for connected ESP32 boards")
            self._port_combo.setToolTip("Select the serial port your board is connected to")
            self._port_combo.clearEditText()
            self._refresh_ports()

    def _detect_or_discover(self):
        if self._connection_mode == "WiFi":
            self._discover_wifi()
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

    def _disconnect_device(self):
        self._serial_reader.stop_streaming()
        self._serial_reader.disconnect()
        self._wifi_reader.stop_streaming()
        self._wifi_reader.disconnect()

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
                f"background-color: {COLORS['accent_red']}; color: white; font-weight: bold;"
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

    def _on_bootloader(self):
        pass

    def _on_tab_changed(self, index: int):
        if self._tabs.widget(index) is self._train_tab:
            self._train_tab.set_recordings(self._session_manager.get_records())

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
            self.dashboard.update_prediction(result.substance, result.confidence, result.warning or "")
            self.dashboard.update_chemprint(result.chemoprint)
            self._status.showMessage(f"OpenSmell: {result.substance} (conf={result.confidence:.3f})", 5000)
            return {
                "substance": result.substance,
                "confidence": result.confidence,
                "warning": result.warning,
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

    def _start_burnin(self):
        hours = self._burnin_hours_spin.value()
        self._burnin.set_burnin_hours(hours)
        self._burnin.reset(hours)
        self._burnin.start()
        self._status.showMessage(f"Burn-in started: {hours}h", 5000)

    def _reset_burnin(self):
        confirm = ConfirmDialog("Reset Burn-In", "Reset the burn-in timer to 0?", "Reset")
        if confirm.exec():
            hours = self._burnin_hours_spin.value()
            self._burnin.reset(hours)

    def _on_burnin_hours_change(self, hours: float):
        pass

    def _browse_save_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if path:
            self._save_dir_input.setText(path)
            self._settings.setValue("data/save_dir", path)
            self._recorder = CSVRecorder(path)

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

    def _show_about(self):
        InfoDialog(
            f"About {__app_name__}",
            f"<h2>{__app_name__} v{__version__}</h2>"
            "<p>Electronic nose GUI for the OpenSmell project.</p>"
            "<p>Manages ESP32-based MQ sensor arrays, records sessions, "
            "trains adapters, and integrates with the OpenSmell SDK.</p>"
            "<p>Part of the OpenSmell ecosystem.</p>"
        ).exec()

    def closeEvent(self, event):
        self._serial_reader.stop_streaming()
        self._serial_reader.cleanup()
        self._wifi_reader.stop_streaming()
        self._wifi_reader.cleanup()
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
