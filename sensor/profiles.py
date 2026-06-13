from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SensorProfile:
    model: str
    target_gases: list[str]
    default_pin: int
    heating_voltage: float = 5.0
    load_resistance: float = 10.0
    sensitivity_range: tuple[float, float] = (10, 10000)
    warmup_minutes: int = 5
    description: str = ""

    def __hash__(self):
        return hash(self.model)


class SensorProfiles:
    _profiles: dict[str, SensorProfile] = {
        "MQ-135": SensorProfile(
            model="MQ-135",
            target_gases=["NH₃", "VOC", "CO₂", "Smoke"],
            default_pin=34,
            warmup_minutes=5,
            description="Air quality sensor for NH₃, VOC, CO₂",
        ),
        "MQ-3": SensorProfile(
            model="MQ-3",
            target_gases=["Alcohol", "Ethanol"],
            default_pin=35,
            warmup_minutes=5,
            description="Alcohol vapor sensor",
        ),
        "MQ-6": SensorProfile(
            model="MQ-6",
            target_gases=["LPG", "Propane", "Butane"],
            default_pin=32,
            warmup_minutes=5,
            description="LPG / propane / butane sensor",
        ),
        "MQ-7": SensorProfile(
            model="MQ-7",
            target_gases=["Carbon Monoxide (CO)"],
            default_pin=33,
            warmup_minutes=5,
            description="Carbon monoxide sensor",
        ),
        "MQ-4": SensorProfile(
            model="MQ-4",
            target_gases=["Methane (CH₄)", "Natural Gas"],
            default_pin=25,
            warmup_minutes=5,
            description="Methane / natural gas sensor",
        ),
        "MQ-8": SensorProfile(
            model="MQ-8",
            target_gases=["Hydrogen (H₂)"],
            default_pin=26,
            warmup_minutes=5,
            description="Hydrogen gas sensor",
        ),
    }

    smelnet_channel_map: dict[str, int] = {
        "MQ-135": 0,
        "MQ-3": 1,
        "MQ-6": 2,
        "MQ-7": 3,
        "MQ-4": 4,
        "MQ-8": 5,
    }

    @classmethod
    def get(cls, model: str) -> Optional[SensorProfile]:
        return cls._profiles.get(model)

    @classmethod
    def list_models(cls) -> list[str]:
        return list(cls._profiles.keys())

    @classmethod
    def all(cls) -> dict[str, SensorProfile]:
        return dict(cls._profiles)

    @classmethod
    def register_custom(cls, profile: SensorProfile) -> None:
        cls._profiles[profile.model] = profile

    @classmethod
    def validate_config(cls, sensors: list[str]) -> list[str]:
        warnings = []
        seen_pins = set()
        for s in sensors:
            profile = cls.get(s)
            if profile:
                if profile.default_pin in seen_pins:
                    warnings.append(f"Pin conflict: {s} shares pin {profile.default_pin}")
                seen_pins.add(profile.default_pin)
        return warnings
