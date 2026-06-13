from pathlib import Path
from PySide6.QtCore import QSettings

APP_NAME = "Osmograph"
ORG_NAME = "OpenSmell"
SETTINGS_FILE = Path.home() / ".config" / "Osmograph" / "settings.ini"


def get_settings() -> QSettings:
    return QSettings(str(SETTINGS_FILE), QSettings.Format.IniFormat)


def migrate_settings():
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    s = get_settings()
    defaults = {
        "burnin/hours": 24,
        "burnin/elapsed_seconds": "0",
        "burnin/last_active": "",
        "serial/baud": "115200",
        "serial/port": "",
        "sensor/preset": "3-sensor food",
        "adapter/model_path": str(Path.home() / ".cache" / "osmograph" / "adapter.pth"),
        "data/save_dir": str(Path.home() / "Osmograph_Recordings"),
        "ui/geometry": "",
        "ui/window_state": "",
    }
    for key, val in defaults.items():
        if s.value(key) is None:
            s.setValue(key, val)
    s.sync()
