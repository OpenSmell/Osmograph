from dataclasses import dataclass, field
from typing import Optional

ESP32_ADC_PINS = [32, 33, 34, 35, 36, 37, 38, 39]
ESP32_DIGITAL_PINS = list(range(0, 40))

GPIO_FUNCTIONS: dict[int, str] = {
    0: "STRAPPING (DO NOT USE)",
    1: "UART TX",
    2: "ONBOARD LED",
    3: "UART RX",
    5: "STRAPPING",
    6: "FLASH (DO NOT USE)",
    7: "FLASH (DO NOT USE)",
    8: "FLASH (DO NOT USE)",
    9: "FLASH (DO NOT USE)",
    10: "FLASH (DO NOT USE)",
    11: "FLASH (DO NOT USE)",
    12: "STRAPPING",
    15: "STRAPPING",
}


@dataclass
class PinAssignment:
    sensor_model: str
    gpio_pin: int
    is_adc: bool = True

    def validate(self) -> tuple[bool, str]:
        if self.gpio_pin not in ESP32_ADC_PINS and self.is_adc:
            return False, f"GPIO {self.gpio_pin} is not an ADC-capable pin. Use: {ESP32_ADC_PINS}"
        if self.gpio_pin in GPIO_FUNCTIONS:
            warning = GPIO_FUNCTIONS[self.gpio_pin]
            if "DO NOT USE" in warning:
                return False, f"GPIO {self.gpio_pin}: {warning}"
        return True, "OK"


@dataclass
class PinMap:
    assignments: dict[str, PinAssignment] = field(default_factory=dict)

    def add(self, sensor: str, pin: int) -> tuple[bool, str]:
        assignment = PinAssignment(sensor_model=sensor, gpio_pin=pin)
        ok, msg = assignment.validate()
        if not ok:
            return False, msg
        for existing in self.assignments.values():
            if existing.gpio_pin == pin:
                return False, f"Pin {pin} already assigned to {existing.sensor_model}"
        self.assignments[sensor] = assignment
        return True, f"{sensor} → GPIO {pin}"

    def remove(self, sensor: str) -> None:
        self.assignments.pop(sensor, None)

    def to_firmware_config(self) -> dict:
        return {
            s: a.gpio_pin
            for s, a in sorted(self.assignments.items())
        }

    def to_sensor_order(self) -> list[str]:
        return sorted(self.assignments.keys(), key=lambda s: self.assignments[s].gpio_pin)

    def to_smellnet_array(self) -> list[float]:
        order = ["MQ-135", "MQ-3", "MQ-6", "MQ-7", "MQ-4", "MQ-8"]
        size = max(6, len(self.assignments))
        arr = [0.0] * size
        for sensor, assignment in self.assignments.items():
            if sensor in order:
                idx = order.index(sensor)
                arr[idx] = float(assignment.gpio_pin)
        return arr


class PinMapper:
    @staticmethod
    def get_available_adc_pins() -> list[int]:
        return [p for p in ESP32_ADC_PINS if p not in GPIO_FUNCTIONS or "DO NOT USE" not in GPIO_FUNCTIONS[p]]

    @staticmethod
    def get_all_gpio_pins() -> list[int]:
        return [p for p in ESP32_DIGITAL_PINS if p not in GPIO_FUNCTIONS or "DO NOT USE" not in GPIO_FUNCTIONS[p]]

    @staticmethod
    def suggest_pins(sensor_count: int) -> list[int]:
        available = PinMapper.get_available_adc_pins()
        return available[:sensor_count]

    @staticmethod
    def autodetect_pins(sensors: list[str]) -> PinMap:
        from .profiles import SensorProfiles

        pm = PinMap()
        used_pins = set()
        for sensor in sensors:
            profile = SensorProfiles.get(sensor)
            if profile and profile.default_pin not in used_pins:
                pm.add(sensor, profile.default_pin)
                used_pins.add(profile.default_pin)
            else:
                for pin in ESP32_ADC_PINS:
                    if pin not in used_pins:
                        pm.add(sensor, pin)
                        used_pins.add(pin)
                        break
        return pm
