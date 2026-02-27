# Baby Macropad

Stream Dock M18 macropad controller for [Baby Basics](https://github.com/FindingJohnny/baby-basics) baby tracking.

Press physical buttons to instantly log feedings, diapers, sleep, and notes. No phone needed at 3 AM.

## Hardware

- **Macropad**: VSDinside Stream Dock M18 (15 LCD keys + 480x272 touchscreen)
- **Computer**: Raspberry Pi (tested on Pi 2B, should work on 3/4/Zero 2 W)
- **OS**: Raspberry Pi OS Bookworm (Python 3.11+)
- **Connection**: USB (the device exposes two HID interfaces via hidraw)

## How It Works

The device has a continuous 480x272 LCD panel behind a 5x3 button grid. We
render all button icons into a single JPEG and send it to the panel. Physical
button presses are read from the HID interface and dispatched to the Baby
Basics API.

**No SDK required.** The driver (`device.py`) communicates with the device
using 100% raw hidraw I/O via the CRT protocol. The official MiraboxSpace SDK
was abandoned because its C library causes USB disconnects after ~60 seconds.
See [docs/debugging-journal.md](docs/debugging-journal.md) for the full story.

## Button Layout

```
Row 1: [Breast L] [Breast R] [Bottle]  [      ]  [      ]
Row 2: [  Pee  ] [  Poop  ] [ Both ]  [ Sleep ]  [ Note ]
Row 3: [Nursery] [ Night  ] [  Fan ]  [ Sound ]  [All Off]
```

## Quick Start

```bash
# Clone
git clone https://github.com/FindingJohnny/baby-macropad.git
cd baby-macropad

# Install (on Pi)
chmod +x scripts/install.sh
./scripts/install.sh

# Configure
cp config/default.yaml config/local.yaml
# Edit config/local.yaml with your API token and child ID

# Run
sudo systemctl start baby-macropad
```

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Architecture

```
src/baby_macropad/
  main.py              # Entry point, controller, button dispatch + debounce
  config.py            # YAML config + Pydantic validation
  device.py            # StreamDock raw hidraw driver (CRT protocol)
  actions/
    baby_basics.py     # Baby Basics API client (httpx)
    home_assistant.py  # Home Assistant REST API client (Phase 2)
  ui/
    icons.py           # Button icon generation (Pillow, calibrated to bezels)
  offline/
    queue.py           # SQLite offline event buffer
    sync.py            # Background sync worker
```

### Device Driver

The `StreamDockDevice` class in `device.py` implements the CRT protocol:

- **CONNECT** heartbeat every 10s (prevents firmware demo mode)
- **LOG** command for full-screen JPEG transfer (header + chunks + STP refresh)
- **LIG** / **LBLIG** for screen and LED brightness
- **Button reads** via select() + os.read() with 0xFF echo filtering
- **Write lock** serializes all hidraw writes (critical for multi-threaded use)
- **300ms button debounce** (firmware sends 12+ HID events per physical press)

See [docs/streamdock-protocol.md](docs/streamdock-protocol.md) for the full
protocol reference.

### Offline Support

Button presses are dispatched to the API immediately. If the API is unreachable,
events are queued in a local SQLite database and retried by a background sync
worker. LED feedback shows green (success), amber (queued), or the configured
color per button.

## Documentation

- [StreamDock CRT Protocol Reference](docs/streamdock-protocol.md) — Complete
  reverse-engineered protocol for the M18 firmware
- [Display Calibration Guide](docs/calibration-guide.md) — How to measure
  visible areas behind button bezels
- [Debugging Journal](docs/debugging-journal.md) — Chronological record of
  the 15+ experiments that led to the stable raw hidraw driver

## Pi Deployment

The macropad runs as a systemd service on the Raspberry Pi:

```bash
# Check status
sudo systemctl status baby-macropad

# View logs
sudo journalctl -u baby-macropad -f

# Restart
sudo systemctl restart baby-macropad

# Full recovery (USB reset + restart)
sudo systemctl stop baby-macropad
echo 0 | sudo tee /sys/bus/usb/devices/1-1/authorized
sleep 2
echo 1 | sudo tee /sys/bus/usb/devices/1-1/authorized
sleep 3
sudo systemctl start baby-macropad
```

## License

MIT
