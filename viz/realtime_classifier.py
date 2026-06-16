import pickle
import logging
import warnings
from pathlib import Path

import numpy as np
from scipy.stats import skew, kurtosis
from Osmograph.viz.paradigm_features import compute_window_paradigms

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", message="Precision loss occurred in moment calculation")

ROLLING_WINDOW = 30
LOCK_THRESHOLD = 0.7
LOCK_CONSECUTIVE = 10
UNKNOWN_THRESHOLD = 0.5
UNKNOWN_CONSECUTIVE = 20


def extract_features(window: np.ndarray) -> np.ndarray:
    return compute_window_paradigms(window, r0_samples=3)


def _extract_features_legacy(window: np.ndarray) -> np.ndarray:
    n_ch = window.shape[1]
    feats = []
    for c in range(n_ch):
        ch = window[:, c]
        ch = np.nan_to_num(ch, nan=0.0)
        ch_std = float(np.std(ch))
        feats.extend([
            float(np.mean(ch)),
            ch_std,
            float(np.max(ch) - np.min(ch)),
            float(np.sqrt(np.mean(ch ** 2))),
            float(np.mean(np.abs(np.diff(ch)))),
            float(np.mean(ch[:10]) - np.mean(ch[-10:])),
            float(skew(ch) if not np.isclose(ch_std, 0) and len(ch) > 2 else 0.0),
            float(kurtosis(ch) if not np.isclose(ch_std, 0) and len(ch) > 3 else 0.0),
        ])
    feats = [0.0 if np.isnan(f) or np.isinf(f) else f for f in feats]
    return np.array(feats, dtype=np.float32)


class RealtimeClassifier:
    def __init__(self, n_sensors: int = 3):
        self._clf = None
        self._le = None
        self._classes = []
        self._scaler = None
        self._buffer = []
        self._window_size = ROLLING_WINDOW
        self._loaded_path = None
        self._n_sensors = n_sensors
        self._classifier_name = ""
        self._training_accuracy = 0.0
        self._confidence_threshold = 0.5
        self._current_probs = []
        self._current_prediction = ("", 0.0)
        self._lock_count = 0
        self._unknown_count = 0
        self._locked = False
        self._locked_class = ""
        self._prev_prediction = ("", 0.0)

    @property
    def is_loaded(self) -> bool:
        return self._clf is not None

    @property
    def classes(self) -> list[str]:
        return self._classes

    @property
    def loaded_path(self) -> str:
        return str(self._loaded_path) if self._loaded_path else ""

    @property
    def n_sensors(self) -> int:
        return self._n_sensors

    @n_sensors.setter
    def n_sensors(self, count: int) -> None:
        self._n_sensors = count

    @property
    def window_size(self) -> int:
        return self._window_size

    @window_size.setter
    def window_size(self, size: int) -> None:
        size = max(20, min(500, size))
        if size != self._window_size:
            self._window_size = size
            self._buffer = self._buffer[-size:] if len(self._buffer) > size else self._buffer

    @property
    def classifier_name(self) -> str:
        return self._classifier_name or (Path(self._loaded_path).stem if self._loaded_path else "")

    @classifier_name.setter
    def classifier_name(self, name: str) -> None:
        self._classifier_name = name

    @property
    def confidence_threshold(self) -> float:
        return self._confidence_threshold

    @confidence_threshold.setter
    def confidence_threshold(self, t: float) -> None:
        self._confidence_threshold = max(0.0, min(1.0, t))

    @property
    def training_accuracy(self) -> float:
        return self._training_accuracy

    @property
    def current_probabilities(self) -> list[float]:
        return self._current_probs

    @property
    def current_prediction(self) -> tuple[str, float]:
        return self._current_prediction

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def locked_class(self) -> str:
        return self._locked_class

    def reset_locks(self) -> None:
        self._locked = False
        self._locked_class = ""
        self._lock_count = 0
        self._unknown_count = 0

    def load(self, pkl_path: str | Path) -> None:
        pkl_path = Path(pkl_path)
        with open(pkl_path, "rb") as f:
            model = pickle.load(f)
        self._clf = model["clf"]
        self._le = model["label_encoder"]
        self._classes = model["classes"]
        self._scaler = model.get("scaler")
        self._classifier_name = model.get("classifier_name", pkl_path.stem)
        ws = model.get("window_size")
        if ws:
            self._window_size = ws
        self._training_accuracy = model.get("training_accuracy", 0.0)
        # Keep hardware sensor count (set by preset) — don't let model override
        self._loaded_path = pkl_path
        self._buffer = []
        self._current_probs = []
        self._current_prediction = ("", 0.0)
        self.reset_locks()
        logger.info(
            f"Loaded classifier: {self._classifier_name} "
            f"({len(self._classes)} classes: {self._classes}, "
            f"window={self._window_size}, sensors={self._n_sensors})"
        )

    def unload(self) -> None:
        self._clf = None
        self._le = None
        self._classes = []
        self._scaler = None
        self._loaded_path = None
        self._classifier_name = ""
        self._training_accuracy = 0.0
        self._buffer = []
        self._current_probs = []
        self._current_prediction = ("", 0.0)
        self.reset_locks()

    def add_sample(self, sample: np.ndarray) -> tuple[str, float] | None:
        if not self.is_loaded:
            return None
        self._buffer.append(sample.astype(np.float32))
        if len(self._buffer) < self._window_size:
            return None
        if len(self._buffer) > self._window_size * 2:
            self._buffer = self._buffer[-self._window_size:]
        return self._predict()

    def _lazy_import_preprocessing(self):
        if "expand_channels" in self.__dict__:
            return
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "opensmell"))
        from opensmell.preprocessing import expand_channels, per_recording_zscore
        self.__dict__["expand_channels"] = expand_channels
        self.__dict__["per_recording_zscore"] = per_recording_zscore

    def _predict(self) -> tuple[str, float]:
        window = np.array(self._buffer[-self._window_size:], dtype=np.float32)
        n_cols = window.shape[1]

        # Detect and expand padded data: hardware may have fewer sensors than 6
        # even though serial reader pads to 6. Check if trailing channels are dead.
        hw_sensors = self._n_sensors
        if hw_sensors >= 6:
            hw_sensors = 3  # no explicit hw count; assume 3-sensor device
        needs_expand = n_cols >= hw_sensors and hw_sensors < 6
        if needs_expand and n_cols >= hw_sensors:
            # Verify trailing channels are indeed padding (near-zero)
            trailing = window[:, hw_sensors:]
            if trailing.size > 0 and not np.all(np.abs(trailing) < 1e-3):
                needs_expand = False

        if needs_expand:
            if not hasattr(self, '_expander'):
                import sys
                from pathlib import Path as P
                sys.path.insert(0, str(P(__file__).resolve().parent.parent.parent / "opensmell"))
                from opensmell.preprocessing import expand_channels as _ec
                self._expander = _ec
            raw = self._expander(window[:, :hw_sensors])
        else:
            raw = window[:, :6]

        n_expected = self._scaler.mean_.shape[0] if self._scaler is not None else 30

        if n_expected == 48:
            self._lazy_import_preprocessing()
            zed = self.per_recording_zscore(raw)
            feats = _extract_features_legacy(zed).reshape(1, -1)
        else:
            feats = extract_features(raw).reshape(1, -1)

        if self._scaler is not None:
            feats = self._scaler.transform(feats)

        pred = self._clf.predict(feats)[0]
        proba = self._clf.predict_proba(feats)[0]
        confidence = float(max(proba))
        self._current_probs = [float(p) for p in proba]

        label = self._le.inverse_transform([pred])[0]
        self._prev_prediction = self._current_prediction

        if confidence < self._confidence_threshold:
            self._current_prediction = ("unknown", confidence)
        else:
            self._current_prediction = (label, confidence)

        if confidence >= LOCK_THRESHOLD:
            self._lock_count += 1
            self._unknown_count = 0
            if self._lock_count >= LOCK_CONSECUTIVE and not self._locked:
                self._locked = True
                self._locked_class = label
        else:
            self._lock_count = 0
            self._locked = False

        if confidence < UNKNOWN_THRESHOLD:
            self._unknown_count += 1
        else:
            self._unknown_count = 0

        return self._current_prediction

    @property
    def is_unknown(self) -> bool:
        return self._unknown_count >= UNKNOWN_CONSECUTIVE

    @property
    def unknown_count(self) -> int:
        return self._unknown_count
