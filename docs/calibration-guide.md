# M18 Display Calibration Guide

## Overview

The StreamDock M18 has a continuous 480x272 LCD panel behind a 5x3 physical button grid. The button bezels obscure significant portions of the screen — typically ~12px per side horizontally and ~15-20px per side vertically. This means the visible area per button is only ~72x60px, not the full 96x91px cell.

**You must calibrate the visible areas before rendering icons**, or content will be hidden under the bezels.

## What You Need

- SSH access to the Pi running the macropad
- Physical access to look at the device
- The calibration scripts in `tools/`

## Calibration Process

### Step 1: Stop the service

```bash
ssh nursery@10.0.0.75 'sudo systemctl stop baby-macropad'
```

### Step 2: Generate calibration images

On your development machine:

```bash
cd /path/to/baby-macropad
python3 tools/gen_calibration.py    # Corner brackets, rulers, row fills
python3 tools/gen_calibration2.py   # Per-edge measurement patterns
python3 tools/gen_coordinates.py    # Coordinate rulers (the key tool)
```

### Step 3: Upload to the Pi

```bash
ssh nursery@10.0.0.75 'mkdir -p ~/baby-macropad/tools/test_images/calibration'
scp tools/test_images/calibration/*.jpg nursery@10.0.0.75:~/baby-macropad/tools/test_images/calibration/
scp tools/show_one.py nursery@10.0.0.75:~/baby-macropad/tools/show_one.py
```

### Step 4: Measure Y coordinates (row boundaries)

Show the Y ruler on the device:

```bash
ssh nursery@10.0.0.75 'cd ~/baby-macropad && nohup ~/macropad-venv/bin/python tools/show_one.py tools/test_images/calibration/10_y_ruler.jpg > /tmp/show_one.log 2>&1 &'
```

The Y ruler shows horizontal colored stripes labeled with Y pixel coordinates. Colors cycle every 70px: Red(0), Green(10), Blue(20), Yellow(30), Purple(40), Cyan(50), Orange(60), Red(70)...

**For each row of buttons**, report which color bands are visible and approximate Y ranges:
- Top row: first visible color to last visible color → Y range
- Middle row: same
- Bottom row: same

Example result: Top=10-70, Mid=110-170, Bot=200-270

Kill the script before moving on:
```bash
ssh nursery@10.0.0.75 'pkill -f show_one.py'
```

### Step 5: Measure X coordinates (column boundaries)

```bash
ssh nursery@10.0.0.75 'cd ~/baby-macropad && nohup ~/macropad-venv/bin/python tools/show_one.py tools/test_images/calibration/11_x_ruler.jpg > /tmp/show_one.log 2>&1 &'
```

Same approach but with vertical stripes. The color cycle is the same: R(0), G(10), B(20), Y(30), P(40), C(50), O(60), repeating.

**For each column**, report the color bands visible. Since numbers are hard to read on vertical stripes, report colors and percentages of first/last bands.

Map colors back to X coordinates using the cycle:
- Column N starts at X = N × 96
- Find which color corresponds to the first visible stripe near that X

Example: Column 0 sees G(90%)...G(70%) → X=11 to X=83

### Step 6: Update icons.py

Edit `src/baby_macropad/ui/icons.py` and update these constants:

```python
VIS_COL_X = [11, 107, 203, 299, 395]  # Left edge of visible area per column
VIS_COL_W = [72, 72, 72, 72, 72]      # Visible width per column
VIS_ROW_Y = [10, 110, 200]            # Top edge of visible area per row
VIS_ROW_H = [60, 60, 70]              # Visible height per row
```

Also adjust `icon_size` to fit the visible height minus label space:
- For 60px visible height: `icon_size = 36`, `content_height = 52`
- For 70px visible height: could go up to 42 but keep consistent

### Step 7: Deploy and verify

```bash
git push origin main
ssh nursery@10.0.0.75 'cd ~/baby-macropad && git pull && sudo systemctl restart baby-macropad'
```

## Color-to-Coordinate Reference

The calibration rulers use 7 colors cycling every 10px:

| Index | Color  | RGB            |
|-------|--------|----------------|
| 0     | Red    | (200, 60, 60)  |
| 1     | Green  | (60, 180, 60)  |
| 2     | Blue   | (60, 100, 220) |
| 3     | Yellow | (220, 180, 40) |
| 4     | Purple | (180, 60, 220) |
| 5     | Cyan   | (60, 200, 180) |
| 6     | Orange | (220, 120, 40) |

**Formula**: Color at position P = `colors[(P // 10) % 7]`

## Tips

- The LCD sits below the button grid. Viewing angle affects what you see — look straight on for the most accurate measurement.
- Button bezels have rounded corners, so the very corners of the visible area are slightly clipped. Use the center of each edge for measurement.
- Color accuracy varies by LCD panel. If you can't distinguish Cyan from Yellow, focus on counting the number of visible bands (each = 10px) and matching the sequence pattern.
- Corner bracket patterns (`1_corners.jpg`) are useful as a quick sanity check after calibration — if brackets are visible, alignment is good. If not, recalibrate.

## M18 Calibration Results (2026-02-26)

Device: HOTSPOTEKUSB Stream Dock M18 (VID=0x5548, PID=0x1000)

```
Visible areas (pixels):
  Row 0 (top):    Y = 10..70   (height 60)
  Row 1 (middle): Y = 110..170 (height 60)
  Row 2 (bottom): Y = 200..270 (height 70)

  Col 0: X = 11..83   (width 72)
  Col 1: X = 107..179 (width 72)
  Col 2: X = 203..275 (width 72)
  Col 3: X = 299..371 (width 72)
  Col 4: X = 395..467 (width 72)

Bezel gaps:
  Between cols: ~24px (96 - 72)
  Between row 0-1: ~40px (110 - 70)
  Between row 1-2: ~30px (200 - 170)
  Top bezel: ~10px
  Bottom bezel: ~2px (272 - 270)
  Left bezel: ~11px
  Right bezel: ~13px (480 - 467)
```
