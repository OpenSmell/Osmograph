import sys
import time
import struct
import logging
from typing import Optional, Callable
from enum import Enum
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import numpy as np
import serial

logger = logging.getLogger(__name__)

DEFAULT_BAUD = 115200
EXPECTED_HEADER = b"OSM"
CSV_HEADER = "VOC,Alcohol,LPG,CO,NO2,C2H5OH\n"


class ReadState(Enum):
    IDLE = "idle"
    READY = "ready"
    STREAMING = "streaming"
    ERROR = "error"


class SerialReader(QThread):
    data_received = Signal(object)
    connection_changed = Signal(bool, str)
    error_occurred = Signal(str)
    bootloader_detected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._serial = None
        self._running = False
        self._mutex = QMutex()
        self._port: Optional[str] = None
        self._baud = DEFAULT_BAUD
        self._buffer = b""
        self._state = ReadState.IDLE
        self._sample_count = 0
        self._bootloader_lines = 0
        self._validator: Optional[Callable] = None

    @property
    def state(self) -> ReadState:
        return self._state

    @property
    def sample_count(self) -> int:
        return self._sample_count

    def configure(self, port: str, baud: int = DEFAULT_BAUD) -> None:
        self._port = port
        self._baud = baud

    def set_validator(self, validator: Callable) -> None:
        self._validator = validator

    def connect(self) -> tuple[bool, str]:
        try:
            if self._serial and self._serial.is_open:
                self._serial.close()
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
            )
            time.sleep(0.5)
            self._serial.reset_input_buffer()
            self._state = ReadState.READY
            self.connection_changed.emit(True, f"Connected to {self._port}")
            logger.info(f"Serial connected: {self._port} @ {self._baud}")
            return True, "Connected"
        except Exception as e:
            self._state = ReadState.ERROR
            self.connection_changed.emit(False, str(e))
            return False, str(e)

    def disconnect(self) -> None:
        locker = QMutexLocker(self._mutex)
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._state = ReadState.IDLE
        self.connection_changed.emit(False, "Disconnected")

    def start_streaming(self) -> None:
        if not self.isRunning():
            self._running = True
            self._state = ReadState.STREAMING
            self.start()

    def stop_streaming(self) -> None:
        self._running = False
        self._state = ReadState.IDLE

    def run(self) -> None:
        if not self._serial or not self._serial.is_open:
            self.error_occurred.emit("Serial port not open")
            return

        while self._running:
            try:
                if self._serial is None or not self._serial.is_open:
                    self._running = False
                    self.connection_changed.emit(False, "Serial disconnected")
                    break

                raw = self._serial.read(512)
                if not raw:
                    time.sleep(0.01)
                    continue

                self._buffer += raw
                self._bootloader_lines += raw.count(b"\n")

                if self._bootloader_lines < 5:
                    self.bootloader_detected.emit()

                lines = self._buffer.split(b"\n")
                self._buffer = lines[-1]

                for line in lines[:-1]:
                    line = line.strip()
                    if not line:
                        continue
                    parsed = self._parse_line(line)
                    if parsed is not None:
                        self._sample_count += 1
                        if self._validator:
                            parsed = self._validator(parsed)
                        if parsed is not None:
                            self.data_received.emit(parsed)

            except (serial.SerialException, OSError, TypeError, AttributeError) as e:
                logger.warning(f"Serial disconnected: {e}")
                self._running = False
                self.connection_changed.emit(False, str(e))
                break

    def _parse_line(self, line: bytes):
        try:
            decoded = line.decode("utf-8", errors="replace").strip()

            if decoded.startswith("OSM") or "OSM" in decoded:
                decoded = decoded.replace("OSM", "").strip()

            parts = decoded.split(",")
            values = []
            for p in parts:
                p = p.strip()
                if p:
                    try:
                        values.append(float(p))
                    except ValueError:
                        pass

            if len(values) >= 3:
                arr = np.array(values[:6], dtype=np.float32)
                if len(values) < 6:
                    arr = np.pad(arr, (0, 6 - len(arr)), constant_values=0.0)
                return arr
            return None
        except Exception:
            return None

    def write_command(self, cmd: str) -> bool:
        locker = QMutexLocker(self._mutex)
        if self._serial and self._serial.is_open:
            try:
                self._serial.write((cmd + "\n").encode())
                return True
            except Exception:
                return False
        return False

    def cleanup(self):
        self._running = False
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self.wait(2000)
