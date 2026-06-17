# Osmograph — Electronic Nose Desktop Application

![Osmograph screenshot](screenshot.png)

All-in-one GUI for OpenSmell hardware: connect to your ESP32 board, record sensor sessions, train classifiers, and identify substances in real time.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Launch
python -m Osmograph
```

## Architecture

```
Osmograph/
├── board/          # Board detection, firmware compiler (universal WiFi + Serial)
├── sensor/         # Sensor profiles, pin mapping, hardware presets
├── data/           # Serial reader, WiFi reader, CSV recorder, session management
├── viz/            # Live traces, competition grid, substance display, chemoprint
├── burnin/         # Persistent burn-in timer
├── wizard/         # Adapter training wizard
├── ui/             # Dark theme, dialogs
├── firmware/       # Pre-compiled universal firmware binary
├── classifiers/    # User-trained classifier models (.pkl)
└── app.py          # Main window
```

## Features

- **Board Manager**: Auto-detect ESP32, one-click firmware flash via esptool
- **Dual-mode connection**: USB Serial or WiFi (ESP32 creates an AP + TCP server)
- **Live Visualization**: PyQtGraph real-time traces, competition grid, substance display
- **Recording**: Labeled CSV sessions with auto-save
- **Classifier Training**: Record a few substances, train a RandomForest or LogisticRegression model
- **Real-time Prediction**: Competition grid animates with class probabilities; locks on sustained high confidence
- **Burn-In Tracker**: 24h sensor stabilization countdown across restarts
- **Plugin System**: Drop `.py` files with a `run(latent_vector)` function

## Firmware

Osmograph includes a universal ESP32 firmware that works with any sensor count (1–6 MQ sensors).

- **USB Serial** + **WiFi AP** simultaneously — no modes to select
- **No PlatformIO required**: the app flashes a pre-compiled binary via esptool
- **Custom pins**: edit the `SENSOR_PINS[]` array in `board/compiler.py` and recompile, or use the Pin Mapping dialog in the app to export a custom sketch
- **Data format**: each line is `OSM,<adc0>,<adc1>,...` over serial or TCP (port 8080)

The firmware source lives in [`board/compiler.py`](board/compiler.py). The pre-compiled binary at `firmware/firmware_universal.bin` is built with all 6 default GPIO pins and works with any subset of connected sensors.

## Hardware Presets

The app ships with common sensor configurations in `sensor/presets.py`. When you auto-detect a board, you select the preset that matches your hardware, and Osmograph handles the rest — including flashing the correct firmware.

To add a custom configuration, add a new entry to `sensor/presets.py` with your pin mapping.
