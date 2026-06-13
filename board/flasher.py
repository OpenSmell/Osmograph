import sys
import subprocess
import shutil
import logging
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

FLASH_BAUD = 921600


class FlashingService:
    def __init__(self, esptool_path: Optional[str] = None):
        self._esptool = esptool_path or self._find_esptool()

    @staticmethod
    def _find_esptool() -> str:
        candidates = [
            shutil.which("esptool.py"),
            shutil.which("esptool"),
            str(Path(__file__).resolve().parent.parent / "bin" / "esptool.py"),
            str(Path(__file__).resolve().parent.parent / "firmware" / "esptool.py"),
        ]
        for c in candidates:
            if c:
                return c
        return "esptool.py"

    def is_available(self) -> bool:
        try:
            subprocess.run(
                [sys.executable, "-m", "esptool", "--help"],
                capture_output=True, timeout=10
            )
            return True
        except Exception:
            try:
                subprocess.run(
                    [self._esptool, "--help"],
                    capture_output=True, timeout=10
                )
                return True
            except Exception:
                return False

    def flash(
        self,
        port: str,
        firmware_path: str,
        board: str = "esp32",
        chip: str = "esp32",
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> tuple[bool, str]:
        if progress_callback:
            progress_callback(5)

        if not Path(firmware_path).exists():
            return False, f"Firmware not found: {firmware_path}"

        if not self.is_available():
            return False, "esptool.py not found. Install with: pip install esptool"

        if progress_callback:
            progress_callback(10)

        cmd = [
            sys.executable, "-m", "esptool",
            "--chip", chip,
            "--port", port,
            "--baud", str(FLASH_BAUD),
            "--before", "default_reset",
            "--after", "hard_reset",
            "write_flash",
            "-z",
            "--flash_mode", "dio",
            "--flash_freq", "40m",
            "--flash_size", "detect",
            "0x10000", firmware_path,
        ]

        try:
            logger.info(f"Flashing {firmware_path} to {port}...")
            if progress_callback:
                progress_callback(30)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            if process.stdout:
                for line in process.stdout:
                    logger.debug(f"esptool: {line.strip()}")
                    if "Writing at" in line:
                        try:
                            parts = line.strip().split()
                            for p in parts:
                                if p.endswith("%"):
                                    pct = int(p.rstrip("%"))
                                    if progress_callback:
                                        progress_callback(30 + int(pct * 0.65))
                        except (ValueError, IndexError):
                            pass

            returncode = process.wait(timeout=120)
            if progress_callback:
                progress_callback(95)

            if returncode == 0:
                return True, "Firmware flashed successfully"
            return False, f"esptool returned code {returncode}"

        except subprocess.TimeoutExpired:
            return False, "Flashing timed out after 120 seconds"
        except FileNotFoundError:
            return False, "esptool.py not found. Install: pip install esptool"
        except Exception as e:
            return False, f"Flash failed: {e}"

    def erase_flash(self, port: str, chip: str = "esp32") -> tuple[bool, str]:
        cmd = [
            sys.executable, "-m", "esptool",
            "--chip", chip,
            "--port", port,
            "erase_flash",
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return True, "Flash erased"
        except Exception as e:
            return False, f"Erase failed: {e}"

    def read_mac(self, port: str, chip: str = "esp32") -> Optional[str]:
        cmd = [
            sys.executable, "-m", "esptool",
            "--chip", chip,
            "--port", port,
            "read_mac",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            for line in result.stdout.split("\n"):
                if "MAC" in line:
                    return line.strip()
            return None
        except Exception:
            return None
