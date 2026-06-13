import socket
import time
import logging
from typing import Optional
from PySide6.QtCore import QThread, Signal
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8080


class WifiReader(QThread):
    data_received = Signal(object)
    connection_changed = Signal(bool, str)
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sock: Optional[socket.socket] = None
        self._running = False
        self._host = ""
        self._port = DEFAULT_PORT
        self._buffer = b""

    def configure(self, host: str, port: int = DEFAULT_PORT) -> None:
        self._host = host
        self._port = port

    def connect(self) -> tuple[bool, str]:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(5)
            self._sock.connect((self._host, self._port))
            self._sock.settimeout(0.1)
            self.connection_changed.emit(True, f"Connected to {self._host}:{self._port}")
            logger.info(f"WiFi connected: {self._host}:{self._port}")
            return True, "Connected"
        except Exception as e:
            self.connection_changed.emit(False, str(e))
            return False, str(e)

    def disconnect(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self.connection_changed.emit(False, "Disconnected")

    def start_streaming(self) -> None:
        if not self.isRunning():
            self._running = True
            self.start()

    def stop_streaming(self) -> None:
        self._running = False

    def run(self) -> None:
        if not self._sock:
            self.error_occurred.emit("Socket not connected")
            return

        while self._running:
            try:
                if self._sock is None:
                    self._running = False
                    self.connection_changed.emit(False, "Socket closed")
                    break

                raw = self._sock.recv(4096)
                if not raw:
                    time.sleep(0.01)
                    continue

                self._buffer += raw
                lines = self._buffer.split(b"\n")
                self._buffer = lines[-1]

                for line in lines[:-1]:
                    line = line.strip()
                    if not line:
                        continue
                    parsed = self._parse_line(line)
                    if parsed is not None:
                        self.data_received.emit(parsed)

            except socket.timeout:
                continue
            except (ConnectionError, OSError) as e:
                logger.warning(f"WiFi disconnected: {e}")
                self._running = False
                self.connection_changed.emit(False, str(e))
                break
            except Exception as e:
                logger.warning(f"WiFi read error: {e}")
                time.sleep(0.1)

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

    def cleanup(self) -> None:
        self._running = False
        self.disconnect()
        self.wait(2000)


def discover_via_mdns(timeout: int = 3) -> list[dict]:
    discovered = []
    try:
        from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange
        from threading import Event

        found = []
        done = Event()

        def on_change(zeroconf, service_type, name, state_change):
            if state_change == ServiceStateChange.Added:
                info = zeroconf.get_service_info(service_type, name)
                if info:
                    addr = ".".join(str(b) for b in info.addresses[0])
                    found.append({
                        "name": name,
                        "host": addr,
                        "port": info.port,
                    })
                done.set()

        zc = Zeroconf()
        browser = ServiceBrowser(zc, "_osmograph._tcp.local.", handlers=[on_change])
        done.wait(timeout)
        zc.close()
        discovered = found
    except ImportError:
        logger.debug("zeroconf not installed, skipping mDNS discovery")
    except Exception as e:
        logger.warning(f"mDNS discovery error: {e}")
    return discovered
