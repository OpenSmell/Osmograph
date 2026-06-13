import time
import logging
from typing import Optional, Callable
from PySide6.QtCore import QTimer, Signal, QObject

from Osmograph.settings import get_settings

logger = logging.getLogger(__name__)

DEFAULT_BURNIN_HOURS = 24


class BurnInTracker(QObject):
    tick = Signal(int)
    completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = get_settings()
        self._total_hours = float(self._settings.value("burnin/hours", DEFAULT_BURNIN_HOURS))
        self._elapsed_seconds = int(self._settings.value("burnin/elapsed_seconds", "0"))
        self._last_active = self._settings.value("burnin/last_active", "")
        self._running = False
        self._paused = False
        self._completed = False
        self._on_complete: Optional[Callable] = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._detect_power_loss()

    def _detect_power_loss(self) -> None:
        if self._last_active and self._elapsed_seconds > 0:
            try:
                last_time = float(self._last_active)
                gap = time.time() - last_time
                if gap > 60:
                    logger.info(f"Power loss detected: gap={gap:.0f}s, elapsed paused at {self._elapsed_seconds}s")
            except (ValueError, TypeError):
                pass

    def _tick(self) -> None:
        if self._paused or self._completed:
            return
        self._elapsed_seconds += 1
        self._save_state()
        self.tick.emit(self._elapsed_seconds)

        if self._elapsed_seconds >= self._total_hours * 3600:
            self.stop()
            self.completed.emit()
            if self._on_complete:
                self._on_complete()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._paused = False
        self._timer.start(1000)
        logger.info(f"Burn-in tracker started ({self._elapsed_seconds}/{int(self._total_hours*3600)}s)")

    def stop(self) -> None:
        self._running = False
        self._timer.stop()
        self._completed = True
        self._save_state()
        logger.info("Burn-in tracker stopped")

    def pause(self) -> None:
        self._paused = True
        self._save_state()

    def resume(self) -> None:
        self._paused = False

    def reset(self, hours: float = DEFAULT_BURNIN_HOURS) -> None:
        self._total_hours = hours
        self._elapsed_seconds = 0
        self._running = False
        self._paused = False
        self._timer.stop()
        self._save_state()
        logger.info(f"Burn-in tracker reset to {hours}h")

    def set_burnin_hours(self, hours: float) -> None:
        self._total_hours = hours
        self._settings.setValue("burnin/hours", hours)

    def _save_state(self) -> None:
        self._settings.setValue("burnin/elapsed_seconds", str(self._elapsed_seconds))
        self._settings.setValue("burnin/last_active", str(time.time()))
        self._settings.sync()

    @property
    def elapsed_seconds(self) -> int:
        return self._elapsed_seconds

    @property
    def remaining_seconds(self) -> int:
        return max(0, int(self._total_hours * 3600) - self._elapsed_seconds)

    @property
    def remaining_hours(self) -> float:
        return self.remaining_seconds / 3600.0

    @property
    def total_hours(self) -> float:
        return self._total_hours

    @property
    def is_complete(self) -> bool:
        return self._elapsed_seconds >= self._total_hours * 3600

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def progress(self) -> float:
        total = self._total_hours * 3600
        return min(1.0, self._elapsed_seconds / total) if total > 0 else 0.0

    def format_remaining(self) -> str:
        remaining = self.remaining_seconds
        h, rem = divmod(remaining, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def set_on_complete(self, callback: Callable) -> None:
        self._on_complete = callback
