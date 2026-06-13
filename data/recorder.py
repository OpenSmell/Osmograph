import time
import csv
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)

CSV_HEADERS = [
    "timestamp_ms", "VOC", "Alcohol", "LPG", "CO", "NO2", "C2H5OH"
]

SENSOR_LABELS = ["VOC", "Alcohol", "LPG", "CO", "NO2", "C2H5OH"]


class CSVRecorder:
    def __init__(self, save_dir: str | Path = ""):
        self._save_dir = Path(save_dir) if save_dir else Path.home() / "Osmograph_Recordings"
        self._save_dir.mkdir(parents=True, exist_ok=True)
        self._file: Optional[Path] = None
        self._csv_writer = None
        self._file_handle = None
        self._recording = False
        self._start_time = 0.0
        self._duration = 0.0
        self._buffer: list[list] = []
        self._sensor_count = 6
        self._label: str = ""
        self._on_complete: Optional[Callable] = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def elapsed(self) -> float:
        if not self._recording:
            return 0.0
        return time.time() - self._start_time

    @property
    def file_path(self) -> Optional[Path]:
        return self._file

    @property
    def label(self) -> str:
        return self._label

    @property
    def duration(self) -> float:
        return self._duration

    def start(self, label: str = "", duration_sec: float = 60.0, on_complete: Optional[Callable] = None) -> Path:
        self._label = label or f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._duration = duration_sec
        self._on_complete = on_complete

        safe_label = "".join(c if c.isalnum() or c in " _-" else "_" for c in self._label)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_label}.csv"
        self._file = self._save_dir / filename
        self._file_handle = self._file.open("w", newline="")
        self._csv_writer = csv.writer(self._file_handle)
        self._csv_writer.writerow(CSV_HEADERS)
        self._buffer = []
        self._start_time = time.time()
        self._recording = True

        logger.info(f"Recording started: {self._file} (duration={duration_sec}s, label='{label}')")
        return self._file

    def write_sample(self, sensor_values: np.ndarray) -> None:
        if not self._recording:
            return
        ts = int((time.time() - self._start_time) * 1000)
        row = [ts]
        for i in range(self._sensor_count):
            row.append(float(sensor_values[i]) if i < len(sensor_values) else 0.0)
        self._buffer.append(row)

        if len(self._buffer) >= 100:
            self._flush_buffer()

        if self.elapsed >= self._duration:
            self.stop()

    def stop(self) -> Optional[Path]:
        if not self._recording:
            return self._file
        self._flush_buffer()
        self._recording = False
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
        elapsed = time.time() - self._start_time
        logger.info(f"Recording stopped: {self._file} ({elapsed:.1f}s)")

        if self._on_complete:
            self._on_complete(self._file, elapsed)

        return self._file

    def _flush_buffer(self) -> None:
        if self._csv_writer and self._buffer:
            self._csv_writer.writerows(self._buffer)
            self._file_handle.flush()
            self._buffer.clear()

    def cancel(self) -> None:
        self._recording = False
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
        if self._file and self._file.exists():
            self._file.unlink(missing_ok=True)
        logger.info("Recording cancelled")

    def __del__(self):
        if self._recording:
            self.stop()
