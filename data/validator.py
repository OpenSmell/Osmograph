import numpy as np

SENSOR_RANGES: dict[str, tuple[float, float]] = {
    "MQ-135": (0.0, 4095.0),
    "MQ-3": (0.0, 4095.0),
    "MQ-6": (0.0, 4095.0),
    "MQ-7": (0.0, 4095.0),
    "MQ-4": (0.0, 4095.0),
    "MQ-8": (0.0, 4095.0),
}

BOOTLOADER_KEYWORDS = [
    "ets", "rst", "boot", "configsip", "load", "entry",
    "waiting", "download", "flash", "error", "bundles",
    "csum", "secure", "spi", "doubt", "mode",
]


class DataValidator:
    def __init__(self):
        self._consecutive_zeros = 0
        self._total_gibberish = 0
        self._last_valid: np.ndarray | None = None

    def validate(self, sample: np.ndarray) -> np.ndarray | None:
        if sample is None or len(sample) == 0:
            return None

        if not isinstance(sample, np.ndarray):
            return None

        if not np.issubdtype(sample.dtype, np.floating):
            try:
                sample = sample.astype(np.float32)
            except (ValueError, TypeError):
                return None

        if np.any(np.isnan(sample)) or np.any(np.isinf(sample)):
            self._total_gibberish += 1
            return None

        if np.all(sample == 0):
            self._consecutive_zeros += 1
            if self._consecutive_zeros > 10:
                return None
            return sample

        self._consecutive_zeros = 0

        if np.any(sample < 0) or np.any(sample > 5000):
            self._total_gibberish += 1
            return None

        if np.std(sample) < 1e-8:
            self._total_gibberish += 1
            return None

        self._last_valid = sample
        return sample

    @property
    def gibberish_count(self) -> int:
        return self._total_gibberish

    @property
    def signal_stable(self) -> bool:
        return self._total_gibberish < 50

    def reset(self) -> None:
        self._consecutive_zeros = 0
        self._total_gibberish = 0
        self._last_valid = None

    @staticmethod
    def is_bootloader_line(text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in BOOTLOADER_KEYWORDS)
