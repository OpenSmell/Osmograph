# Osmograph — Electronic Nose Desktop Application

All-in-one GUI for OpenSmell hardware: manage ESP32 boards, record sensor sessions, train adapters, and visualize chemoprints.

## Quick Start

```bash
pip install -r requirements.txt
export PYTHONPATH="$PYTHONPATH:$PWD/../opensmell"
python -m Osmograph
```

## Architecture

```
Osmograph/
├── board/          # Board detection, firmware flashing
├── sensor/         # Sensor profiles, pin mapping, presets
├── data/           # Serial reader, CSV recorder, session management
├── viz/            # Live traces, chemoprint bar chart
├── burnin/         # Persistent burn-in timer
├── wizard/         # Adapter training wizard
├── plugins/        # Plugin system
├── ui/             # Dark theme, dialogs
├── firmware/       # Pre-compiled .bin files (3-sensor, 4-sensor, 6-sensor)
└── app.py          # Main window
```

## Features

- **Board Manager**: Auto-detect ESP32, one-click firmware flash
- **Sensor Configurator**: Preset profiles or custom pin mapping
- **Live Visualization**: PyQtGraph real-time traces, 29-dim chemoprint
- **Recording**: Labeled CSV sessions with auto-save
- **Burn-In Tracker**: 24h countdown across restarts
- **Adapter Wizard**: Record 3–5 substances, train with one click
- **Plugin System**: Drop `.py` files with a `run(latent_vector)` function

## Firmware

Pre-compiled firmware binaries for different sensor configurations are in `firmware/`. The source code for these binaries is in the [electronic-nose](https://github.com/opensmell/electronic-nose) repository.

| Binary | Sensors |
|--------|---------|
| `firmware_3food.bin` | MQ-135, MQ-3, MQ-7 |
| `firmware_3safety.bin` | MQ-7, MQ-135, MQ-6 |
| `firmware_4food.bin` | MQ-135, MQ-3, MQ-6, MQ-7 |
| `firmware_4safety.bin` | MQ-7, MQ-135, MQ-6, MQ-8 |
| `firmware_6full.bin` | All 6 MQ sensors |

## Scalability

The Osmograph's `sensor/presets.py` defines pin mappings for different sensor configurations. To add your own hardware:
1. Add a new preset to `sensor/presets.py` with your pin mapping
2. The app handles the rest
