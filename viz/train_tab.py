import sys
import pickle
import logging
from pathlib import Path
from typing import Optional, Callable

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar, QScrollArea,
    QSpinBox, QMessageBox, QGroupBox, QCheckBox,
)
from PySide6.QtGui import QFont

from Osmograph.viz.realtime_classifier import extract_features

logger = logging.getLogger(__name__)

FW_DIR = Path.home() / "Osmograph_Recordings" / "legacy"
REC_DIR = Path.home() / "Osmograph_Recordings"
CLASSIFIERS_DIR = Path(__file__).resolve().parent.parent / "classifiers"

MQ6_COLS = ["MQ135", "MQ3", "MQ6", "MQ7", "MQ4", "MQ8"]
RECORDER_COLS = ["VOC", "Alcohol", "LPG", "CO", "NO2", "C2H5OH"]
ALL_COL_SETS = [MQ6_COLS, RECORDER_COLS]
FW_MAPPING = [(0, 0), (1, 1), (0, 2), (2, 3), (1, 4)]

MAX_SUBSTANCES = {3: 7, 4: 12, 5: 20, 6: 40}


def discover_recordings() -> list[dict]:
    found = []
    seen = set()
    for d, fmt in [(FW_DIR, "fw"), (REC_DIR, "osm")]:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.csv")):
            if f.name in seen:
                continue
            seen.add(f.name)
            label = suggest_label(f, fmt)
            found.append({"path": str(f), "label": label, "fmt": fmt, "name": f.name})
    return found


def suggest_label(path: Path, fmt: str) -> str:
    name = path.stem.lower()
    for kw in ["room air", "room_air", "fresh_air", "air"]:
        if kw in name:
            return "room_air" if "room" in name else "fresh_air"
    known = ["garlic", "ginger", "onion", "cinnamon", "nutmeg", "lime",
             "lemon", "coffee", "mint", "basil", "oregano", "cloves",
             "star_anise", "coriander", "cumin", "allspice", "pepper",
             "salt", "sugar", "vinegar", "alcohol", "ethanol"]
    for k in known:
        if k in name:
            return k
    clean = name.replace("_", " ").replace("-", " ").strip()
    words = clean.split()
    if words:
        return words[0]
    return "unknown"


def load_recording(path: str, fmt: str) -> Optional[np.ndarray]:
    try:
        if fmt == "fw":
            raw = np.genfromtxt(path, delimiter=",", dtype=np.float32, invalid_raise=False)
            raw = raw[~np.isnan(raw).any(axis=1)]
            if raw.ndim == 1:
                raw = raw.reshape(-1, 1)
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "opensmell"))
            from opensmell.preprocessing import expand_channels
            return expand_channels(raw, mapping=FW_MAPPING)
        else:
            import pandas as pd
            df = pd.read_csv(path)
            raw = None
            for col_set in ALL_COL_SETS:
                avail = [c for c in col_set if c in df.columns]
                if avail:
                    raw = df[avail].values.astype(np.float32)
                    break
            if raw is None:
                logger.warning(f"No known columns in {path} (tried MQ6_COLS and RECORDER_COLS)")
                return None
            # Apply same expansion as live _predict() so training matches inference
            src_cols = raw.shape[1]
            if src_cols < 6:
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "opensmell"))
                from opensmell.preprocessing import expand_channels
                raw = expand_channels(raw[:, :src_cols])
            elif raw.shape[1] > 6:
                raw = raw[:, :6]
            return raw
    except Exception as e:
        logger.warning(f"Failed to load {path}: {e}")
        return None


def compute_warning(n_classes: int, n_sensors: int) -> str:
    max_ok = MAX_SUBSTANCES.get(n_sensors, 12)
    if n_classes <= 3:
        return ""
    if n_classes > max_ok:
        return (
            f"⚠ {n_classes} classes with {n_sensors} sensors "
            f"(~{MAX_SUBSTANCES.get(n_sensors, 1)//2}-{max_ok} max). "
            f"Predictions will overlap. Add more sensors or reduce classes."
        )
    if n_classes > max_ok * 0.7:
        return (
            f"⚡ {n_classes} classes approaching the ~{max_ok} limit "
            f"for {n_sensors} sensors. Consider reducing classes."
        )
    return ""


def train_classifier(recordings: list[dict], classifier_name: str,
                     n_sensors: int = 3, window_size: int = 100,
                     progress_callback=None) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import LabelEncoder, StandardScaler

    TRAIN_STRIDE = 5
    X, y = [], []
    total = len(recordings)
    for i, rec in enumerate(recordings):
        raw = load_recording(rec["path"], rec["fmt"])
        if raw is None:
            continue
        N = raw.shape[0]
        if N >= window_size:
            windows = [raw[j:j+window_size] for j in range(0, N - window_size + 1, TRAIN_STRIDE)]
        else:
            windows = [np.pad(raw, ((0, window_size - N), (0, 0)), mode="edge")]
        for w in windows:
            feats = extract_features(w)
            X.append(feats)
            y.append(rec["label"])
        if progress_callback:
            progress_callback(int((i + 1) / total * 50))

    if not X:
        return {"success": False, "error": "No recordings could be loaded"}

    X = np.array(X)
    feat_scaler = StandardScaler()
    X_scaled = feat_scaler.fit_transform(X)
    le = LabelEncoder()
    y_enc = le.fit_transform(y)

    clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0)
    clf.fit(X_scaled, y_enc)
    acc = clf.score(X_scaled, y_enc)

    if progress_callback:
        progress_callback(80)

    classes = le.classes_.tolist()
    n_features = X.shape[1]
    model = {
        "clf": clf,
        "label_encoder": le,
        "classes": classes,
        "scaler": feat_scaler,
        "classifier_name": classifier_name,
        "n_sensors": n_sensors,
        "n_features": n_features,
        "window_size": window_size,
        "training_accuracy": float(acc),
    }

    safe_name = classifier_name.replace(" ", "_").lower()
    save_path = CLASSIFIERS_DIR / f"{safe_name}.pkl"
    CLASSIFIERS_DIR.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        pickle.dump(model, f)

    if progress_callback:
        progress_callback(100)

    return {
        "success": True,
        "path": str(save_path),
        "name": classifier_name,
        "classes": classes,
        "accuracy": float(acc),
        "n_windows": len(X),
    }


class TrainingThread(QThread):
    progress = Signal(int)
    finished = Signal(dict)

    def __init__(self, recordings, classifier_name, n_sensors, window_size):
        super().__init__()
        self.recordings = recordings
        self.classifier_name = classifier_name
        self.n_sensors = n_sensors
        self.window_size = window_size

    def run(self):
        try:
            result = train_classifier(
                self.recordings, self.classifier_name,
                self.n_sensors, self.window_size,
                progress_callback=lambda p: self.progress.emit(p),
            )
        except ImportError as e:
            result = {"success": False, "error": f"Missing module: {e.name}. Check opensmell and sklearn are installed."}
        except Exception as e:
            result = {"success": False, "error": f"Training failed: {e}"}
        self.finished.emit(result)


class TrainTab(QWidget):
    training_complete = Signal(str)

    def __init__(self, n_sensors: int = 3, parent=None):
        super().__init__(parent)
        self._n_sensors = n_sensors
        self._recordings = []
        self._training = False
        self._external_records = None
        self._setup_ui()

    def set_recordings(self, records: list):
        self._external_records = {Path(r.csv_path).name: r for r in records if hasattr(r, 'csv_path')}
        self._load_recordings()

    def set_sensor_count(self, count: int):
        self._n_sensors = count
        self._sensor_count_label.setText(str(count))
        self._update_warnings()

    def refresh_recordings(self):
        self._load_recordings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        header = QLabel("Train a Classifier")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #88ccff;")
        layout.addWidget(header)

        desc = QLabel(
            "Check the recordings you want, assign labels, and click Train. "
            "The classifier will be auto-loaded for real-time predictions."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #999; padding: 2px 0 8px 0;")
        layout.addWidget(desc)

        config_group = QGroupBox("Classifier Configuration")
        config_layout = QHBoxLayout(config_group)

        config_layout.addWidget(QLabel("Name:"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Kitchen Spices, My Substances...")
        self._name_input.textChanged.connect(self._update_warnings)
        config_layout.addWidget(self._name_input)

        config_layout.addWidget(QLabel("Sensors:"))
        self._sensor_count_label = QLabel(str(self._n_sensors))
        self._sensor_count_label.setStyleSheet("font-weight: bold; color: #ccc;")
        config_layout.addWidget(self._sensor_count_label)

        config_layout.addWidget(QLabel("Window:"))
        self._window_spin = QSpinBox()
        self._window_spin.setRange(20, 500)
        self._window_spin.setValue(100)
        self._window_spin.setSuffix(" samples")
        config_layout.addWidget(self._window_spin)

        config_layout.addStretch()
        layout.addWidget(config_group)

        recordings_group = QGroupBox("Recordings")
        rec_layout = QVBoxLayout(recordings_group)

        self._rec_count_label = QLabel("")
        self._rec_count_label.setStyleSheet("color: #888; font-size: 10px; padding: 2px 0;")
        rec_layout.addWidget(self._rec_count_label)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search recordings by name or label...")
        self._search_input.textChanged.connect(self._apply_filter)
        rec_layout.addWidget(self._search_input)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(4, 4, 4, 4)
        self._list_layout.setSpacing(2)
        scroll.setWidget(self._list_widget)
        rec_layout.addWidget(scroll, 1)

        refresh_btn = QPushButton("Refresh Recording List")
        refresh_btn.clicked.connect(self._load_recordings)
        rec_layout.addWidget(refresh_btn)

        layout.addWidget(recordings_group, 1)

        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #ff8844; padding: 4px; font-weight: bold;")
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        train_layout = QHBoxLayout()
        self._train_btn = QPushButton("Train Classifier")
        self._train_btn.setStyleSheet(
            "background-color: #44bb77; color: black; font-weight: bold; "
            "padding: 8px 24px; border-radius: 4px; font-size: 14px;"
        )
        self._train_btn.clicked.connect(self._on_train)
        self._train_btn.setEnabled(False)
        train_layout.addWidget(self._train_btn)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #aaa; padding: 4px;")
        train_layout.addWidget(self._status_label, 1)
        layout.addLayout(train_layout)

        layout.addStretch()

    def _load_recordings(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        self._recordings.clear()

        on_disk = discover_recordings()
        lookup = self._external_records or {}

        seen_names = set()
        all_rows = []
        for r in on_disk:
            fname = r["name"]
            seen_names.add(fname)
            meta = lookup.get(fname)
            if meta:
                r["timestamp"] = meta.timestamp
                r["duration_sec"] = meta.duration_sec
                r["label"] = meta.substance or r["label"]
            all_rows.append(r)

        for fname, meta in lookup.items():
            if fname not in seen_names:
                all_rows.append({
                    "path": meta.csv_path,
                    "label": meta.substance,
                    "fmt": "osm",
                    "name": fname,
                    "timestamp": meta.timestamp,
                    "duration_sec": meta.duration_sec,
                    "missing": True,
                })

        if not all_rows:
            self._status_label.setText("No recordings found. Record some substances first.")
            return

        for r in all_rows:
            self._add_recording_row(r)

        self._search_input.clear()
        self._update_warnings()

    def _apply_filter(self):
        text = self._search_input.text().strip().lower()
        for r in self._recordings:
            widget = r.get("row_widget")
            if not widget:
                continue
            if not text:
                widget.setVisible(True)
            else:
                keys = getattr(widget, '_search_keys', "")
                widget.setVisible(text in keys)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _add_recording_row(self, info: dict):
        row_widget = QWidget()
        missing = info.get("missing", False)

        row = QHBoxLayout(row_widget)
        row.setContentsMargins(4, 4, 4, 4)

        cb = QCheckBox()
        cb.setChecked(False)
        cb.setEnabled(not missing)
        cb.setToolTip("Include this recording in training")
        cb.toggled.connect(lambda _: self._update_warnings())
        row.addWidget(cb)

        name = info.get("name", "")
        ts = info.get("timestamp", 0)
        dur = info.get("duration_sec", 0)

        ts_label = QLabel("")
        dur_label = QLabel("")
        if ts:
            from datetime import datetime
            ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            ts_label.setText(f"[{ts_str}] {info.get('label', '?')} ({dur:.0f}s)")
            ts_label.setStyleSheet("color: #ccc; font-size: 11px;")
            dur_label.setText(f"-> {name}")
            dur_label.setStyleSheet("color: #888; font-size: 10px;")
        else:
            ts_label.setText(f"{info.get('label', '?')} -> {name}")
            ts_label.setStyleSheet("color: #ccc; font-size: 11px;")
        row.addWidget(ts_label, 1)
        row.addWidget(dur_label)

        if missing:
            warn = QLabel("⚠ file not found on disk")
            warn.setStyleSheet("color: #ff8844; font-size: 10px; font-weight: bold; padding: 0 8px;")
            row.addWidget(warn)

        label_input = QLineEdit()
        label_input.setPlaceholderText("class name")
        label_input.setText(info.get("label", ""))
        label_input.setMinimumWidth(140)
        label_input.setMaxLength(40)
        label_input.setEnabled(not missing)
        label_input.textChanged.connect(lambda _: self._update_warnings())
        row.addWidget(label_input)

        row_widget._checkbox = cb
        row_widget._label_input = label_input
        row_widget._search_keys = f"{name} {info.get('label', '')} {ts}".lower()
        self._list_layout.addWidget(row_widget)
        self._recordings.append({**info, "label_input": label_input, "checkbox": cb, "row_widget": row_widget})

    def _get_config(self) -> tuple[list[dict], set]:
        result = []
        seen_labels = set()
        for r in self._recordings:
            if not r.get("checkbox") or not r["checkbox"].isChecked():
                continue
            label = r["label_input"].text().strip().lower().replace(" ", "_")
            if not label:
                continue
            seen_labels.add(label)
            result.append({"path": r["path"], "label": label, "fmt": r["fmt"]})
        return result, seen_labels

    def _update_warnings(self):
        config, labels = self._get_config()
        n_classes = len(labels)
        total = len(self._recordings)
        selected = len(config)
        name_ok = bool(self._name_input.text().strip())
        self._train_btn.setEnabled(n_classes >= 2 and name_ok and selected >= 2)

        self._rec_count_label.setText(f"{selected} of {total} recordings selected ({n_classes} substance{'s' if n_classes != 1 else ''})")

        warning = compute_warning(n_classes, self._n_sensors)
        if warning:
            self._warning_label.setText(warning)
            self._warning_label.setVisible(True)
        else:
            self._warning_label.setVisible(False)

    def _on_train(self):
        if self._training:
            return
        name = self._name_input.text().strip()
        window_size = self._window_spin.value()
        config, labels = self._get_config()
        if len(labels) < 2:
            QMessageBox.warning(self, "Too Few Classes",
                                "Assign at least 2 different substance labels.")
            return

        if len(config) < 2:
            QMessageBox.warning(self, "Too Few Recordings",
                                "Select at least 2 recordings to train.")
            return

        self._training = True
        self._train_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status_label.setText("Training...")

        self._thread = TrainingThread(config, name, self._n_sensors, window_size)
        self._thread.progress.connect(self._progress.setValue)
        self._thread.finished.connect(self._on_training_done)
        self._thread.start()

    def _on_training_done(self, result: dict):
        self._training = False
        self._train_btn.setEnabled(True)

        if result["success"]:
            acc = result["accuracy"]
            self._status_label.setText(
                f"✓ {result['name']} — {', '.join(result['classes'])} "
                f"({acc:.1%}, {result['n_windows']} windows)"
            )
            self._status_label.setStyleSheet("color: #88dd88; padding: 4px;")
            self.training_complete.emit(result["path"])
        else:
            self._status_label.setText(f"✗ {result.get('error', 'Training failed')}")
            self._status_label.setStyleSheet("color: #ff6666; padding: 4px;")
