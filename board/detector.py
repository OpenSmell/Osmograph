import sys
import subprocess
import re
from pathlib import Path
from enum import Enum
from typing import Optional
from dataclasses import dataclass


class BoardType(Enum):
    ESP32 = "esp32"
    ARDUINO_UNO = "arduino_uno"
    RASPBERRY_PI_PICO = "raspberry_pi_pico"
    UNKNOWN = "unknown"


VID_PID_MAP: dict[str, BoardType] = {
    "10c4:ea60": BoardType.ESP32,   # CP2102
    "1a86:7523": BoardType.ESP32,   # CH340
    "10c4:ea70": BoardType.ESP32,   # CP2105
    "2e8a:0005": BoardType.RASPBERRY_PI_PICO,
    "2341:0043": BoardType.ARDUINO_UNO,
    "2341:0001": BoardType.ARDUINO_UNO,
}

BOARD_LABELS: dict[BoardType, str] = {
    BoardType.ESP32: "ESP32",
    BoardType.ARDUINO_UNO: "Arduino Uno",
    BoardType.RASPBERRY_PI_PICO: "Raspberry Pi Pico",
    BoardType.UNKNOWN: "Unknown Board",
}


@dataclass
class BoardInfo:
    board_type: BoardType
    port: str
    vid_pid: str
    serial_number: str = ""
    manufacturer: str = ""

    @property
    def label(self) -> str:
        return BOARD_LABELS.get(self.board_type, "Unknown Board")

    @property
    def is_known(self) -> bool:
        return self.board_type != BoardType.UNKNOWN


class BoardDetector:
    @staticmethod
    def list_ports() -> list[str]:
        if sys.platform == "linux":
            ports = list(Path("/dev").glob("ttyUSB*")) + \
                    list(Path("/dev").glob("ttyACM*")) + \
                    list(Path("/dev").glob("ttyS*"))
            return sorted(str(p) for p in ports)
        elif sys.platform == "darwin":
            ports = list(Path("/dev").glob("tty.usbserial*")) + \
                    list(Path("/dev").glob("tty.wchusbserial*")) + \
                    list(Path("/dev").glob("cu.usbserial*"))
            return sorted(str(p) for p in ports)
        elif sys.platform == "win32":
            try:
                import serial.tools.list_ports
                return [p.device for p in serial.tools.list_ports.comports()]
            except ImportError:
                return []
        return []

    @staticmethod
    def detect() -> list[BoardInfo]:
        boards: list[BoardInfo] = []
        try:
            import serial.tools.list_ports
            for port in serial.tools.list_ports.comports():
                vid_pid = f"{port.vid:04x}:{port.pid:04x}" if port.vid and port.pid else ""
                bt = VID_PID_MAP.get(vid_pid, BoardType.UNKNOWN)
                boards.append(BoardInfo(
                    board_type=bt,
                    port=port.device,
                    vid_pid=vid_pid,
                    serial_number=port.serial_number or "",
                    manufacturer=port.manufacturer or "",
                ))
        except ImportError:
            for port_path in BoardDetector.list_ports():
                boards.append(BoardInfo(
                    board_type=BoardType.UNKNOWN,
                    port=port_path,
                    vid_pid="",
                ))
        return boards

    @staticmethod
    def find_esp32() -> Optional[BoardInfo]:
        boards = BoardDetector.detect()
        for b in boards:
            if b.board_type == BoardType.ESP32:
                return b
        esp_like = [b for b in boards if "usb" in b.port.lower() or "acm" in b.port.lower()]
        return esp_like[0] if esp_like else None

    @staticmethod
    def auto_fix_permissions(port: str) -> bool:
        if sys.platform != "linux":
            return True
        try:
            result = subprocess.run(
                ["ls", "-l", port], capture_output=True, text=True, timeout=5
            )
            if "dialout" in result.stdout or "uucp" in result.stdout:
                return True
            current_user = subprocess.run(
                ["whoami"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            group_result = subprocess.run(
                ["groups", current_user], capture_output=True, text=True, timeout=5
            ).stdout
            if "dialout" in group_result or "uucp" in group_result:
                return True
            subprocess.run(
                ["sudo", "chmod", "666", port],
                capture_output=True, timeout=10
            )
            return True
        except Exception:
            return False
