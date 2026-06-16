import sys
import pickle
import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QProgressBar, QScrollArea,
    QWidget, QFormLayout, QGroupBox, QFrame, QMessageBox,
)
from PySide6.QtGui import QFont

from Osmograph.viz.realtime_classifier import extract_features

logger = logging.getLogger(__name__)

FW_DIR = Path(__file__).resolve().parent.parent.parent / "electronic-nose" / "firmware"
REC_DIR = Path.home() / "Osmograph_Recordings"
CLASSIFIERS_DIR = Path(__file__).resolve().parent.parent / "classifiers"

MQ6_COLS = ["MQ135", "MQ3", "MQ6", "MQ7", "MQ4", "MQ8"]
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
            avail = [c for c in MQ6_COLS if c in df.columns]
            if not avail:
                logger.warning(f"No MQ columns in {path}")
                return None
            raw = df[avail].values.astype(np.float32)
            if raw.shape[1] < 6:
                padded = np.zeros((raw.shape[0], 6), dtype=np.float32)
                padded[:, :raw.shape[1]] = raw
                raw = padded
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
    from scipy.stats import skew, kurtosis
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "opensmell"))
    from opensmell.preprocessing import per_recording_zscore, SEGMENT_LEN

    TRAIN_STRIDE = 5
    X, y = [], []
    total = len(recordings)
    for i, rec in enumerate(recordings):
        raw = load_recording(rec["path"], rec["fmt"])
        if raw is None:
            continue
        N = raw.shape[0]
        if N >= SEGMENT_LEN:
            windows = [raw[j:j+SEGMENT_LEN] for j in range(0, N - SEGMENT_LEN + 1, TRAIN_STRIDE)]
        else:
            windows = [np.pad(raw, ((0, SEGMENT_LEN - N), (0, 0)), mode="edge")]
        for w in windows:
            zed = per_recording_zscore(w)
            feats = extract_features(zed)
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
    model = {
        "clf": clf,
        "label_encoder": le,
        "classes": classes,
        "scaler": feat_scaler,
        "classifier_name": classifier_name,
        "n_sensors": n_sensors,
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
        result = train_classifier(
            self.recordings, self.classifier_name,
            self.n_sensors, self.window_size,
            progress_callback=lambda p: self.progress.emit(p),
        )
        self.finished.emit(result)


class TrainingWizard(QDialog):
    def __init__(self, n_sensors: int = 3, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Train a Classifier")
        self.setMinimumSize(600, 500)
        self._n_sensors = n_sensors
        self._recordings = []
        self._training = False
        self._setup_ui()
        self._load_recordings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Train a Classifier")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #88ccff;")
        layout.addWidget(title)

        desc = QLabel(
            "Select recordings, assign labels, and train a real-time classifier. "
            "The classifier will appear in the toolbar dropdown."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; padding: 4px 0;")
        layout.addWidget(desc)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Classifier name:"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. Kitchen Spices, My Substances...")
        name_layout.addWidget(self._name_input)
        layout.addLayout(name_layout)

        sensors_layout = QHBoxLayout()
        sensors_layout.addWidget(QLabel("Sensors:"))
        self._sensors_spin = type("Spin", (), {
            "value": lambda self: 3, "setValue": lambda self, v: None,
        })()
        sensor_label = QLabel(f"{self._n_sensors}")
        sensor_label.setStyleSheet("font-weight: bold; color: #ccc;")
        sensors_layout.addWidget(sensor_label)
        sensors_layout.addStretch()

        sensors_layout.addWidget(QLabel("Window size:"))
        self._window_spin = type("Spin", (), {
            "value": lambda self: 50, "setValue": lambda self, v: None,
        })()
        window_label = QLabel("50 samples")
        window_label.setStyleSheet("font-weight: bold; color: #ccc;")
        sensors_layout.addWidget(window_label)
        sensors_layout.addStretch()
        layout.addLayout(sensors_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll)

        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #ff8844; padding: 4px; font-weight: bold;")
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        btn_layout = QHBoxLayout()
        self._train_btn = QPushButton("Train Classifier")
        self._train_btn.setStyleSheet(
            "background-color: #44bb77; color: black; font-weight: bold; "
            "padding: 6px 20px; border-radius: 4px;"
        )
        self._train_btn.clicked.connect(self._on_train)
        self._train_btn.setEnabled(False)
        btn_layout.addWidget(self._train_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #aaa; padding: 2px;")
        layout.addWidget(self._status_label)

    def _load_recordings(self):
        for r in discover_recordings():
            self._add_recording_row(r)

        if self._list_layout.count() == 0:
            self._status_label.setText(
                "No recordings found. Record some substances first, then open this dialog."
            )
        self._update_warnings()

    def _add_recording_row(self, info: dict):
        row = QHBoxLayout()
        row.setContentsMargins(4, 2, 4, 2)

        name_label = QLabel(info["name"])
        name_label.setMinimumWidth(200)
        row.addWidget(name_label)

        label_combo = QComboBox()
        label_combo.setEditable(True)
        label_combo.setMinimumWidth(130)

        known = sorted(set(r["label"] for r in self._recordings))
        if info["label"] and info["label"] not in known:
            known = [info["label"]] + known
        for k in known:
            label_combo.addItem(k)
        existing = label_combo.findText(info["label"])
        if existing >= 0:
            label_combo.setCurrentIndex(existing)
        else:
            label_combo.setEditText(info["label"])

        row.addWidget(label_combo)
        self._list_layout.addLayout(row)
        self._recordings.append({**info, "combo": label_combo})

    def _get_config(self) -> list[dict]:
        result = []
        seen_labels = set()
        for r in self._recordings:
            label = r["combo"].currentText().strip().lower().replace(" ", "_")
            if not label:
                continue
            seen_labels.add(label)
            result.append({"path": r["path"], "label": label, "fmt": r["fmt"]})
        return result, seen_labels

    def _update_warnings(self):
        config, labels = self._get_config()
        n_classes = len(labels)
        self._train_btn.setEnabled(n_classes >= 2 and self._name_input.text().strip())

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
        if not name:
            QMessageBox.warning(self, "No Name", "Enter a classifier name.")
            return
        config, labels = self._get_config()
        if len(labels) < 2:
            QMessageBox.warning(self, "Too Few Classes",
                                "Assign at least 2 different substance labels.")
            return

        window_size = 50
        self._training = True
        self._train_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
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
        self._cancel_btn.setEnabled(True)

        if result["success"]:
            path = result["path"]
            classes = ", ".join(result["classes"])
            acc = result["accuracy"]
            self._status_label.setText(
                f"✓ Saved: {Path(path).name}\n"
                f"  Classes: {classes}  |  "
                f"Accuracy: {acc:.1%}  |  "
                f"Windows: {result['n_windows']}"
            )
            self._status_label.setStyleSheet("color: #88dd88; padding: 2px;")
            QMessageBox.information(self, "Training Complete",
                f"Classifier saved as:\n{Path(path).name}\n\n"
                f"Classes: {classes}\n"
                f"Training accuracy: {acc:.1%}\n\n"
                f"It will appear in the toolbar dropdown after restarting or refreshing."
            )
            self.accept()
        else:
            self._status_label.setText(f"✗ {result.get('error', 'Training failed')}")
            self._status_label.setStyleSheet("color: #ff6666; padding: 2px;")
            QMessageBox.critical(self, "Training Failed", result.get("error", "Unknown error"))
