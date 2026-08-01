import asyncio
import logging
from typing import Optional
from PySide6.QtCore import QThread, Signal
import numpy as np

logger = logging.getLogger(__name__)

SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
DEVICE_NAME = "Osmograph-BLE"


class BleReader(QThread):
    data_received = Signal(object)
    connection_changed = Signal(bool, str)
    error_occurred = Signal(str)
    devices_discovered = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._device_address: Optional[str] = None
        self._buffer = b""

    def configure(self, address: str) -> None:
        self._device_address = address

    def start_scan(self, timeout: int = 5) -> None:
        self._timeout = timeout
        self._running = True
        self.start()

    def run(self) -> None:
        if self._device_address:
            self._connect_and_stream()
        else:
            self._scan_for_device()

    def stop_streaming(self) -> None:
        self._running = False

    def _scan_for_device(self) -> None:
        try:
            import bleak
        except ImportError:
            self.error_occurred.emit(
                "Install bleak for BLE support:\n  pip install bleak"
            )
            return

        async def scan():
            from bleak import BleakScanner
            devices = await BleakScanner.discover(timeout=self._timeout)
            found = []
            for d in devices:
                if d.name and DEVICE_NAME in d.name:
                    found.append({"name": d.name, "address": d.address})
                    logger.info(f"BLE device found: {d.name} ({d.address})")
            self.devices_discovered.emit(found)
            if found:
                self._device_address = found[0]["address"]
                await self._stream(found[0]["address"])
            else:
                self.connection_changed.emit(False, "No BLE devices found")

        loop = asyncio.new_event_loop()
        loop.run_until_complete(scan())
        loop.close()

    def _connect_and_stream(self) -> None:
        async def connect():
            await self._stream(self._device_address)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(connect())
        loop.close()

    async def _stream(self, address: str) -> None:
        from bleak import BleakClient

        def notify_handler(sender, data: bytearray):
            self._buffer += data
            lines = self._buffer.split(b"\n")
            self._buffer = lines[-1] if lines else b""
            for line in lines[:-1]:
                line = line.strip()
                if not line:
                    continue
                parsed = self._parse_line(line)
                if parsed is not None:
                    self.data_received.emit(parsed)

        try:
            async with BleakClient(address, timeout=10) as client:
                self.connection_changed.emit(True, f"BLE connected: {address}")
                await client.start_notify(CHARACTERISTIC_UUID, notify_handler)
                while self._running:
                    await asyncio.sleep(0.1)
                await client.stop_notify(CHARACTERISTIC_UUID)
        except Exception as e:
            logger.warning(f"BLE error: {e}")
            self.connection_changed.emit(False, str(e))

    def _parse_line(self, line: bytes):
        try:
            decoded = line.decode("utf-8", errors="replace").strip()
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

    def cleanup(self) -> None:
        self._running = False
        self.wait(2000)
