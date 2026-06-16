from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class FirmwareImage:
    name: str
    path: str
    board: str
    sensor_count: int
    sensors: list[str]
    pins: list[int]
    description: str
    flash_address: str = "0x10000"
    flash_mode: str = "dio"
    flash_freq: str = "40m"

    @property
    def size_bytes(self) -> int:
        try:
            return Path(self.path).stat().st_size
        except OSError:
            return 0


_BUILTIN_FW_KEY = "universal"


class FirmwareRepository:
    _bundled: dict[str, FirmwareImage] = {}

    @classmethod
    def initialize(cls, firmware_dir: str | Path) -> None:
        fw_dir = Path(firmware_dir)
        fw_dir.mkdir(parents=True, exist_ok=True)
        universal = cls._make_universal(fw_dir)
        cls._bundled[_BUILTIN_FW_KEY] = universal
        for alias in cls._preset_aliases():
            cls._bundled[alias] = universal

    @classmethod
    def _make_universal(cls, base: Path) -> FirmwareImage:
        return FirmwareImage(
            name="firmware_universal",
            path=str(base / "firmware_universal.bin"),
            board="esp32",
            sensor_count=6,
            sensors=["GPIO32", "GPIO33", "GPIO34", "GPIO35", "GPIO25", "GPIO26"],
            pins=[32, 33, 34, 35, 25, 26],
            description="Universal: USB Serial + WiFi AP. Works with 1-6 sensors on GPIO 32-35, 25-26.",
        )

    @classmethod
    def _preset_aliases(cls) -> list[str]:
        return [
            "3-sensor food",
            "4-sensor food",
            "3-sensor safety",
            "4-sensor safety",
            "6-sensor full",
            "2-sensor alcohol",
            "5-sensor environmental",
        ]

    @classmethod
    def list_presets(cls) -> list[FirmwareImage]:
        return list(cls._bundled.values())

    @classmethod
    def get(cls, name: str) -> Optional[FirmwareImage]:
        return cls._bundled.get(name) or cls._bundled.get(_BUILTIN_FW_KEY)

    @classmethod
    def find_for_config(cls, sensor_count: int, board: str = "esp32") -> Optional[FirmwareImage]:
        return cls._bundled.get(_BUILTIN_FW_KEY)

    @classmethod
    def get_preset_labels(cls) -> list[str]:
        return list(cls._bundled.keys())
