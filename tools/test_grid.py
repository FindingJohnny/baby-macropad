#!/usr/bin/env python3
"""Generate diagnostic test images for StreamDock M18 grid alignment.

The M18 has a 480x272 LCD panel behind a 5x3 physical button grid (15 keys).
This script generates several JPEG test patterns to help diagnose whether
the rendered grid cells align with the physical button cutouts.

Key mapping (physical layout):
    Top row (row 0):    KEY_11  KEY_12  KEY_13  KEY_14  KEY_15
    Middle row (row 1): KEY_6   KEY_7   KEY_8   KEY_9   KEY_10
    Bottom row (row 2): KEY_1   KEY_2   KEY_3   KEY_4   KEY_5

Usage:
    python tools/test_grid.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --- Screen geometry ---
SCREEN_W = 480
SCREEN_H = 272
COLS = 5
ROWS = 3
CELL_W = SCREEN_W // COLS  # 96

# Current tuned layout
ROW_Y = [0, 91, 182]
ROW_H = [91, 91, 90]

OUTPUT_DIR = Path(__file__).parent / "test_images"

# 15 distinct background colors for numbered cells
CELL_COLORS = [
    (220, 50, 50),    # 1  - Red
    (50, 180, 50),    # 2  - Green
    (50, 100, 220),   # 3  - Blue
    (220, 180, 30),   # 4  - Gold
    (180, 50, 220),   # 5  - Purple
    (30, 200, 200),   # 6  - Cyan
    (220, 120, 30),   # 7  - Orange
    (120, 200, 80),   # 8  - Lime
    (200, 80, 160),   # 9  - Pink
    (80, 140, 200),   # 10 - Steel blue
    (200, 200, 60),   # 11 - Yellow
    (100, 220, 180),  # 12 - Teal
    (220, 100, 100),  # 13 - Salmon
    (140, 100, 220),  # 14 - Indigo
    (180, 180, 180),  # 15 - Silver
]


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a bold font at the given size, with fallbacks."""
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in font_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _key_number(row: int, col: int) -> int:
    """Grid position (row, col) to physical key number.

    Top row (0):    11-15
    Middle row (1): 6-10
    Bottom row (2): 1-5
    """
    if row == 0:
        return 11 + col
    elif row == 1:
        return 6 + col
    else:
        return 1 + col


def _draw_label(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, font: ImageFont.FreeTypeFont) -> None:
    """Draw text with a dark outline for readability on any background."""
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font)
    draw.text((x, y), text, fill=(255, 255, 255), font=font)


def _draw_test_label(draw: ImageDraw.ImageDraw, label: str) -> None:
    """Draw a small label in the top-left corner describing the test."""
    font = _get_font(10)
    # Semi-transparent background strip
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = 3
    draw.rectangle([0, 0, tw + pad * 2, th + pad * 2], fill=(0, 0, 0, 200))
    draw.text((pad, pad), label, fill=(255, 255, 200), font=font)


def generate_numbered_cells() -> Image.Image:
    """Test 1: Each cell gets a large key number and a distinct background color.

    Uses the current tuned ROW_Y/ROW_H layout.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    num_font = _get_font(36)
    sub_font = _get_font(10)

    for row in range(ROWS):
        for col in range(COLS):
            key_num = _key_number(row, col)
            x = col * CELL_W
            y = ROW_Y[row]
            h = ROW_H[row]
            color = CELL_COLORS[key_num - 1]

            draw.rectangle([x, y, x + CELL_W - 1, y + h - 1], fill=color)

            # Draw the key number centered in the cell
            text = str(key_num)
            bbox = num_font.getbbox(text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = x + (CELL_W - tw) // 2
            ty = y + (h - th) // 2 - 5
            _draw_label(draw, text, tx, ty, num_font)

            # Draw "KEY_N" subtitle below
            sub = f"KEY_{key_num}"
            bbox_s = sub_font.getbbox(sub)
            sw = bbox_s[2] - bbox_s[0]
            sx = x + (CELL_W - sw) // 2
            sy = ty + th + 4
            _draw_label(draw, sub, sx, sy, sub_font)

    _draw_test_label(draw, "TEST 1: Numbered cells (tuned ROW_Y)")
    return img


def generate_crosshair_grid() -> Image.Image:
    """Test 2: Grid lines at cell boundaries + crosshairs at cell centers.

    White grid lines on dark background. Helps see where boundaries
    fall relative to physical button edges.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (20, 20, 20))
    draw = ImageDraw.Draw(img)
    font = _get_font(10)

    grid_color = (255, 255, 255)
    cross_color = (255, 100, 100)

    # Vertical grid lines (column boundaries)
    for col in range(COLS + 1):
        x = col * CELL_W
        if x >= SCREEN_W:
            x = SCREEN_W - 1
        draw.line([(x, 0), (x, SCREEN_H - 1)], fill=grid_color, width=1)

    # Horizontal grid lines (row boundaries)
    for row in range(ROWS):
        y = ROW_Y[row]
        draw.line([(0, y), (SCREEN_W - 1, y)], fill=grid_color, width=1)
    # Bottom edge
    draw.line([(0, SCREEN_H - 1), (SCREEN_W - 1, SCREEN_H - 1)], fill=grid_color, width=1)

    # Row boundary between row 0 and row 1
    draw.line([(0, ROW_Y[1] - 1), (SCREEN_W - 1, ROW_Y[1] - 1)], fill=grid_color, width=1)
    # Row boundary between row 1 and row 2
    draw.line([(0, ROW_Y[2] - 1), (SCREEN_W - 1, ROW_Y[2] - 1)], fill=grid_color, width=1)

    # Crosshairs at cell centers
    cross_arm = 15
    for row in range(ROWS):
        for col in range(COLS):
            key_num = _key_number(row, col)
            cx = col * CELL_W + CELL_W // 2
            cy = ROW_Y[row] + ROW_H[row] // 2

            # Horizontal arm
            draw.line([(cx - cross_arm, cy), (cx + cross_arm, cy)], fill=cross_color, width=1)
            # Vertical arm
            draw.line([(cx, cy - cross_arm), (cx, cy + cross_arm)], fill=cross_color, width=1)
            # Small center dot
            draw.ellipse(
                [cx - 2, cy - 2, cx + 2, cy + 2],
                fill=cross_color,
            )

            # Key number near crosshair
            text = str(key_num)
            bbox = font.getbbox(text)
            tw = bbox[2] - bbox[0]
            draw.text((cx - tw // 2, cy + cross_arm + 3), text, fill=(180, 180, 180), font=font)

    _draw_test_label(draw, "TEST 2: Crosshair grid (tuned ROW_Y)")
    return img


def generate_edge_markers() -> Image.Image:
    """Test 3: Colored edge markers on each cell.

    Each cell has 5px colored bars at each edge:
      - Red = top edge
      - Blue = bottom edge
      - Green = left edge
      - Yellow = right edge

    If a color is invisible, the bezel covers that edge.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (40, 40, 40))
    draw = ImageDraw.Draw(img)
    font = _get_font(12)

    edge_thickness = 5
    top_color = (255, 60, 60)      # Red
    bottom_color = (60, 60, 255)   # Blue
    left_color = (60, 220, 60)     # Green
    right_color = (255, 255, 60)   # Yellow

    for row in range(ROWS):
        for col in range(COLS):
            key_num = _key_number(row, col)
            x = col * CELL_W
            y = ROW_Y[row]
            h = ROW_H[row]
            w = CELL_W

            # Top edge (red)
            draw.rectangle([x, y, x + w - 1, y + edge_thickness - 1], fill=top_color)
            # Bottom edge (blue)
            draw.rectangle([x, y + h - edge_thickness, x + w - 1, y + h - 1], fill=bottom_color)
            # Left edge (green)
            draw.rectangle([x, y, x + edge_thickness - 1, y + h - 1], fill=left_color)
            # Right edge (yellow)
            draw.rectangle([x + w - edge_thickness, y, x + w - 1, y + h - 1], fill=right_color)

            # Key number in center
            text = str(key_num)
            bbox = font.getbbox(text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = x + (w - tw) // 2
            ty = y + (h - th) // 2
            _draw_label(draw, text, tx, ty, font)

    # Legend at bottom-right corner (on top of bottom-right cell)
    legend_font = _get_font(9)
    legend_items = [
        ("R=top", top_color),
        ("B=bot", bottom_color),
        ("G=left", left_color),
        ("Y=right", right_color),
    ]
    lx = SCREEN_W - 55
    ly = 2
    for text, color in legend_items:
        draw.rectangle([lx, ly, lx + 6, ly + 6], fill=color)
        draw.text((lx + 9, ly - 1), text, fill=(200, 200, 200), font=legend_font)
        ly += 11

    _draw_test_label(draw, "TEST 3: Edge markers (5px, RGBY)")
    return img


def generate_uniform_cells() -> Image.Image:
    """Test 4: Same as numbered cells but using naive equal division.

    Each cell is 96 x 90.67 (rounded per-row). For comparison against
    the tuned layout.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    num_font = _get_font(36)
    sub_font = _get_font(10)

    # Naive equal division
    naive_row_h = SCREEN_H / ROWS  # 90.666...

    for row in range(ROWS):
        for col in range(COLS):
            key_num = _key_number(row, col)
            x = col * CELL_W
            y = round(row * naive_row_h)
            y_next = round((row + 1) * naive_row_h)
            h = y_next - y
            color = CELL_COLORS[key_num - 1]

            draw.rectangle([x, y, x + CELL_W - 1, y + h - 1], fill=color)

            # Key number
            text = str(key_num)
            bbox = num_font.getbbox(text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = x + (CELL_W - tw) // 2
            ty = y + (h - th) // 2 - 5
            _draw_label(draw, text, tx, ty, num_font)

            # Subtitle
            sub = f"KEY_{key_num}"
            bbox_s = sub_font.getbbox(sub)
            sw = bbox_s[2] - bbox_s[0]
            sx = x + (CELL_W - sw) // 2
            sy = ty + th + 4
            _draw_label(draw, sub, sx, sy, sub_font)

    _draw_test_label(draw, "TEST 4: Numbered cells (naive equal division)")
    return img


def generate_offset_tests() -> list[tuple[str, Image.Image]]:
    """Test 5: Progressive offset variations.

    Generates multiple images with the row Y positions shifted by a few
    pixels in different directions. Each filename encodes the offset.

    Variations tested:
      - Shift all rows down by 1-4px
      - Shift all rows up by 1-4px
      - Shift middle row only up/down by 1-3px
      - Compress/expand row 0 height by 1-3px
    """
    results = []
    num_font = _get_font(28)
    info_font = _get_font(10)

    def _make_offset_image(
        row_y: list[int],
        row_h: list[int],
        desc: str,
        filename: str,
    ) -> tuple[str, Image.Image]:
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        for row in range(ROWS):
            for col in range(COLS):
                key_num = _key_number(row, col)
                x = col * CELL_W
                y = row_y[row]
                h = row_h[row]
                color = CELL_COLORS[key_num - 1]

                # Slightly desaturated to keep text readable
                muted = tuple(max(40, c // 2 + 40) for c in color)
                draw.rectangle([x, y, x + CELL_W - 1, y + h - 1], fill=muted)

                # Key number
                text = str(key_num)
                bbox = num_font.getbbox(text)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                tx = x + (CELL_W - tw) // 2
                ty = y + (h - th) // 2
                _draw_label(draw, text, tx, ty, num_font)

        # Info bar with offset details
        _draw_test_label(draw, f"TEST 5: {desc}")

        # Draw ROW_Y/ROW_H values along right edge
        for row in range(ROWS):
            ry = row_y[row]
            rh = row_h[row]
            info = f"Y={ry} H={rh}"
            bbox = info_font.getbbox(info)
            iw = bbox[2] - bbox[0]
            ix = SCREEN_W - iw - 4
            iy = ry + rh // 2 - 5
            _draw_label(draw, info, ix, iy, info_font)

        return (filename, img)

    # --- Baseline (current tuned) for reference ---
    results.append(_make_offset_image(
        [0, 91, 182], [91, 91, 90],
        "Baseline (current tuned)",
        "05a_baseline",
    ))

    # --- Shift all rows down by 1-4px ---
    for shift in range(1, 5):
        ry = [0, 91 + shift, 182 + shift * 2]
        # Clamp last row so it doesn't exceed screen
        rh0 = ry[1]
        rh1 = ry[2] - ry[1]
        rh2 = SCREEN_H - ry[2]
        results.append(_make_offset_image(
            ry, [rh0, rh1, rh2],
            f"All rows +{shift}px down",
            f"05b_all_down_{shift}",
        ))

    # --- Shift all rows up by 1-4px ---
    for shift in range(1, 5):
        ry = [0, 91 - shift, 182 - shift * 2]
        rh0 = ry[1]
        rh1 = ry[2] - ry[1]
        rh2 = SCREEN_H - ry[2]
        results.append(_make_offset_image(
            ry, [rh0, rh1, rh2],
            f"All rows -{shift}px up",
            f"05c_all_up_{shift}",
        ))

    # --- Shift middle row only ---
    for shift in range(-3, 4):
        if shift == 0:
            continue
        direction = "down" if shift > 0 else "up"
        ry = [0, 91 + shift, 182]
        rh0 = ry[1]
        rh1 = ry[2] - ry[1]
        rh2 = SCREEN_H - ry[2]
        results.append(_make_offset_image(
            ry, [rh0, rh1, rh2],
            f"Mid row {direction} {abs(shift)}px (Y1={91 + shift})",
            f"05d_mid_{direction}_{abs(shift)}",
        ))

    # --- Vary row 0 height (shift row 1 boundary) ---
    for delta in range(-3, 4):
        if delta == 0:
            continue
        r0h = 91 + delta
        ry = [0, r0h, r0h + 91]
        rh0 = ry[1]
        rh1 = ry[2] - ry[1]
        rh2 = SCREEN_H - ry[2]
        if rh2 < 80 or rh2 > 100:
            continue  # Skip unreasonable values
        label = f"R0 height {r0h}px ({'+' if delta > 0 else ''}{delta})"
        results.append(_make_offset_image(
            ry, [rh0, rh1, rh2],
            label,
            f"05e_r0h_{r0h}",
        ))

    return results


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Generating test images in {OUTPUT_DIR}/")
    print(f"Screen: {SCREEN_W}x{SCREEN_H}, Grid: {COLS}x{ROWS}, Cell width: {CELL_W}")
    print(f"Current layout: ROW_Y={ROW_Y}, ROW_H={ROW_H}")
    print()

    # Test 1: Numbered cells (tuned)
    img = generate_numbered_cells()
    path = OUTPUT_DIR / "01_numbered_cells.jpg"
    img.save(path, "JPEG", quality=95)
    print(f"  [1] {path.name} - Numbered cells with tuned ROW_Y")

    # Test 2: Crosshair grid
    img = generate_crosshair_grid()
    path = OUTPUT_DIR / "02_crosshair_grid.jpg"
    img.save(path, "JPEG", quality=95)
    print(f"  [2] {path.name} - Grid lines + crosshairs")

    # Test 3: Edge markers
    img = generate_edge_markers()
    path = OUTPUT_DIR / "03_edge_markers.jpg"
    img.save(path, "JPEG", quality=95)
    print(f"  [3] {path.name} - Colored edge markers (RGBY)")

    # Test 4: Uniform equal division
    img = generate_uniform_cells()
    path = OUTPUT_DIR / "04_uniform_cells.jpg"
    img.save(path, "JPEG", quality=95)
    print(f"  [4] {path.name} - Numbered cells with naive equal division")

    # Test 5: Progressive offsets
    offsets = generate_offset_tests()
    for filename, img in offsets:
        path = OUTPUT_DIR / f"{filename}.jpg"
        img.save(path, "JPEG", quality=95)
    print(f"  [5] {len(offsets)} offset variants (05a_* through 05e_*)")

    total = 4 + len(offsets)
    print(f"\nDone. {total} images saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
