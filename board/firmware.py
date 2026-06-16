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


class FirmwareRepository:
    _bundled: dict[str, FirmwareImage] = {}

    @classmethod
    def initialize(cls, firmware_dir: str | Path) -> None:
        fw_dir = Path(firmware_dir)
        fw_dir.mkdir(parents=True, exist_ok=True)
        presets = cls._default_presets(fw_dir)
        for key, image in presets.items():
            cls._bundled[key] = image
            if not Path(image.path).exists():
                cls._generate_placeholder(image)

    @classmethod
    def _default_presets(cls, base: Path) -> dict[str, FirmwareImage]:
        return {
            "universal": FirmwareImage(
                name="firmware_universal",
                path=str(base / "firmware_universal.bin"),
                board="esp32",
                sensor_count=6,
                sensors=["GPIO32", "GPIO33", "GPIO34", "GPIO35", "GPIO25", "GPIO26"],
                pins=[32, 33, 34, 35, 25, 26],
                description="Universal: USB Serial + WiFi AP. Works with 1-6 sensors on GPIO 32-35, 25-26.",
            ),
        }

    @classmethod
    def _generate_placeholder(cls, image: FirmwareImage) -> None:
        fw_path = Path(image.path)
        fw_path.parent.mkdir(parents=True, exist_ok=True)
        fw_path.write_text(
            f"# Osmograph Universal Firmware\n"
            f"# Board: {image.board}\n"
            f"# Sensor pins: {image.pins}\n"
            f"# Compile with PlatformIO, then flash with:\n"
            f"#   esptool.py --chip esp32 --port PORT write_flash 0x10000 {image.path}\n"
        )

    @classmethod
    def list_presets(cls) -> list[FirmwareImage]:
        return list(cls._bundled.values())

    @classmethod
    def get(cls, name: str) -> Optional[FirmwareImage]:
        return cls._bundled.get(name)

    @classmethod
    def find_for_config(cls, sensor_count: int, board: str = "esp32") -> Optional[FirmwareImage]:
        # Universal firmware works for any config
        return cls._bundled.get("universal")

    @classmethod
    def get_preset_labels(cls) -> list[str]:
        return list(cls._bundled.keys())
