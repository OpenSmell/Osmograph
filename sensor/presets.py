from dataclasses import dataclass


@dataclass
class BuildPreset:
    name: str
    sensors: list[str]
    pins: list[int]
    description: str
    firmware_key: str = ""

    @property
    def sensor_count(self) -> int:
        return len(self.sensors)


class PresetManager:
    _presets: dict[str, BuildPreset] = {
        "3-sensor food": BuildPreset(
            name="3-sensor food",
            sensors=["MQ-135", "MQ-3", "MQ-7"],
            pins=[34, 35, 32],
            description="Food spoilage detection: ammonia, alcohol, CO",
            firmware_key="3-sensor food",
        ),
        "4-sensor food": BuildPreset(
            name="4-sensor food",
            sensors=["MQ-135", "MQ-3", "MQ-6", "MQ-7"],
            pins=[34, 35, 32, 33],
            description="Food spoilage + LPG detection",
            firmware_key="4-sensor food",
        ),
        "3-sensor safety": BuildPreset(
            name="3-sensor safety",
            sensors=["MQ-7", "MQ-8", "MQ-135"],
            pins=[34, 35, 32],
            description="Safety: CO, H₂, NH₃ detection",
            firmware_key="3-sensor safety",
        ),
        "4-sensor safety": BuildPreset(
            name="4-sensor safety",
            sensors=["MQ-7", "MQ-8", "MQ-135", "MQ-3"],
            pins=[34, 35, 32, 33],
            description="Safety + alcohol detection",
            firmware_key="4-sensor safety",
        ),
        "6-sensor full": BuildPreset(
            name="6-sensor full",
            sensors=["MQ-135", "MQ-3", "MQ-6", "MQ-7", "MQ-4", "MQ-8"],
            pins=[34, 35, 32, 33, 25, 26],
            description="Full spectrum: all 6 MQ sensors",
            firmware_key="6-sensor full",
        ),
        "2-sensor alcohol": BuildPreset(
            name="2-sensor alcohol",
            sensors=["MQ-3", "MQ-135"],
            pins=[35, 34],
            description="Minimal alcohol + air quality",
            firmware_key="",
        ),
        "5-sensor environmental": BuildPreset(
            name="5-sensor environmental",
            sensors=["MQ-135", "MQ-4", "MQ-7", "MQ-8", "MQ-3"],
            pins=[34, 25, 33, 26, 35],
            description="Environmental monitoring: air quality, methane, CO, H₂, alcohol",
            firmware_key="",
        ),
    }

    @classmethod
    def list_presets(cls) -> list[BuildPreset]:
        return list(cls._presets.values())

    @classmethod
    def get(cls, name: str):
        return cls._presets.get(name)

    @classmethod
    def get_preset_names(cls) -> list[str]:
        return list(cls._presets.keys())

    @classmethod
    def register_preset(cls, preset: BuildPreset) -> None:
        cls._presets[preset.name] = preset
