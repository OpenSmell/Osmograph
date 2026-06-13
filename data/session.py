import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class SessionRecord:
    substance: str
    csv_path: str
    timestamp: float
    duration_sec: float
    sensor_count: int
    preset_name: str
    label: str = ""
    notes: str = ""
    opensmell_result: Optional[dict] = None
    file_id: str = ""

    def __post_init__(self):
        if not self.file_id:
            self.file_id = datetime.fromtimestamp(self.timestamp).strftime("%Y%m%d_%H%M%S")

    @property
    def datetime_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionRecord":
        return cls(**d)


@dataclass
class SessionGroup:
    name: str
    records: list[SessionRecord] = field(default_factory=list)
    created: float = 0.0

    def __post_init__(self):
        if not self.created:
            self.created = time.time()


class SessionManager:
    def __init__(self, data_dir: str | Path = ""):
        self._dir = Path(data_dir) if data_dir else Path.home() / "Osmograph_Recordings"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._dir / ".session_index.json"
        self._records: list[SessionRecord] = []
        self._current_label: str = ""
        self._load_index()

    def _load_index(self) -> None:
        if self._index_file.exists():
            try:
                data = json.loads(self._index_file.read_text())
                self._records = [SessionRecord.from_dict(r) for r in data.get("records", [])]
            except Exception:
                self._records = []

    def _save_index(self) -> None:
        data = {
            "version": 1,
            "updated": time.time(),
            "records": [r.to_dict() for r in self._records],
        }
        self._index_file.write_text(json.dumps(data, indent=2))

    def add_record(self, record: SessionRecord) -> None:
        self._records.append(record)
        self._save_index()

    def remove_record(self, file_id: str) -> bool:
        for i, r in enumerate(self._records):
            if r.file_id == file_id:
                path = Path(r.csv_path)
                if path.exists():
                    path.unlink(missing_ok=True)
                self._records.pop(i)
                self._save_index()
                return True
        return False

    def get_records(self, substance: str = "") -> list[SessionRecord]:
        if substance:
            return [r for r in self._records if r.substance.lower() == substance.lower()]
        return list(self._records)

    def get_record_count(self) -> int:
        return len(self._records)

    def get_recorded_substances(self) -> list[str]:
        return list(set(r.substance for r in self._records))

    def get_records_for_adapter_training(self) -> list[SessionRecord]:
        return [r for r in self._records if r.substance]

    def clear(self) -> None:
        self._records.clear()
        self._save_index()

    @property
    def current_label(self) -> str:
        return self._current_label

    @current_label.setter
    def current_label(self, label: str) -> None:
        self._current_label = label
