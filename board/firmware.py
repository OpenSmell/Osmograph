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
        if not fw_dir.exists():
            fw_dir.mkdir(parents=True, exist_ok=True)

        presets = cls._default_presets(fw_dir)
        for key, image in presets.items():
            cls._bundled[key] = image
            if not Path(image.path).exists():
                cls._generate_placeholder(image)

    @classmethod
    def _default_presets(cls, base: Path) -> dict[str, FirmwareImage]:
        return {
            "3-sensor food": FirmwareImage(
                name="firmware_3food",
                path=str(base / "firmware_3food.bin"),
                board="esp32",
                sensor_count=3,
                sensors=["MQ-135", "MQ-3", "MQ-7"],
                pins=[34, 35, 32],
                description="3-sensor food spoilage detection (MQ-135, MQ-3, MQ-7)",
            ),
            "4-sensor food": FirmwareImage(
                name="firmware_4food",
                path=str(base / "firmware_4food.bin"),
                board="esp32",
                sensor_count=4,
                sensors=["MQ-135", "MQ-3", "MQ-6", "MQ-7"],
                pins=[34, 35, 32, 33],
                description="4-sensor food spoilage detection (+ MQ-6)",
            ),
            "3-sensor safety": FirmwareImage(
                name="firmware_3safety",
                path=str(base / "firmware_3safety.bin"),
                board="esp32",
                sensor_count=3,
                sensors=["MQ-7", "MQ-8", "MQ-135"],
                pins=[34, 35, 32],
                description="3-sensor safety (CO, H₂, NH₃)",
            ),
            "4-sensor safety": FirmwareImage(
                name="firmware_4safety",
                path=str(base / "firmware_4safety.bin"),
                board="esp32",
                sensor_count=4,
                sensors=["MQ-7", "MQ-8", "MQ-135", "MQ-3"],
                pins=[34, 35, 32, 33],
                description="4-sensor safety build (+ alcohol)",
            ),
            "6-sensor full": FirmwareImage(
                name="firmware_6full",
                path=str(base / "firmware_6full.bin"),
                board="esp32",
                sensor_count=6,
                sensors=["MQ-135", "MQ-3", "MQ-6", "MQ-7", "MQ-4", "MQ-8"],
                pins=[34, 35, 32, 33, 25, 26],
                description="6-sensor full spectrum build",
            ),
        }

    @classmethod
    def _generate_placeholder(cls, image: FirmwareImage) -> None:
        fw_path = Path(image.path)
        fw_path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"# Osmograph firmware placeholder\n"
            f"# Board: {image.board}\n"
            f"# Sensors: {', '.join(image.sensors)}\n"
            f"# Pins: {image.pins}\n"
            f"# Flash this binary using esptool.py\n"
        )
        fw_path.write_text(header)

    @classmethod
    def list_presets(cls) -> list[FirmwareImage]:
        return list(cls._bundled.values())

    @classmethod
    def get(cls, name: str) -> Optional[FirmwareImage]:
        return cls._bundled.get(name)

    @classmethod
    def find_for_config(cls, sensor_count: int, board: str = "esp32") -> Optional[FirmwareImage]:
        for image in cls._bundled.values():
            if image.sensor_count == sensor_count and image.board == board:
                return image
        return None

    @classmethod
    def get_preset_labels(cls) -> list[str]:
        return list(cls._bundled.keys())
