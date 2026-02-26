# Baby Macropad

Stream Dock M18 macropad controller for [Baby Basics](https://github.com/FindingJohnny/baby-basics) baby tracking.

Press physical buttons to instantly log feedings, diapers, sleep, and notes. No phone needed at 3 AM.

## Hardware

- **Macropad**: VSDinside Stream Dock M18 (15 LCD keys + touchscreen)
- **Computer**: Raspberry Pi (2B, 3, 4, or Zero 2 W)
- **OS**: Raspberry Pi OS Bookworm (Python 3.11+)

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
  main.py              # Entry point and device controller
  config.py            # YAML config + Pydantic validation
  actions/
    baby_basics.py     # Baby Basics API client
    home_assistant.py  # Home Assistant REST API client
  ui/
    icons.py           # 64x64 button icon generation (Pillow)
    dashboard.py       # 480x272 touchscreen renderer
  offline/
    queue.py           # SQLite offline event buffer
    sync.py            # Background sync worker
```

## License

MIT
