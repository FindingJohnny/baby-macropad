"""Generate professional display calibration patterns for M18 grid alignment.

Creates two calibration images:
1. Corner brackets - quick visual check of which edges are clipped
2. Edge rulers - numbered tick marks growing inward from each edge,
   so the user can report the first visible number = exact bezel inset

The M18 has a 480x272 LCD behind a 5x3 physical button grid.
Each button's bezel obscures some pixels around the edges of its cell.
These patterns measure exactly how much is hidden.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SCREEN_W = 480
SCREEN_H = 272
COLS = 5
ROWS = 3
CELL_W = SCREEN_W // COLS  # 96

# We test multiple row height hypotheses
# Start with equal division as our baseline for measurement
EQUAL_H = SCREEN_H / ROWS  # 90.67

# Key numbers per row (physical layout)
ROW_KEYS = [
    [11, 12, 13, 14, 15],  # top
    [6, 7, 8, 9, 10],      # middle
    [1, 2, 3, 4, 5],       # bottom
]

OUT_DIR = Path("tools/test_images/calibration")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def get_font(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc"]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def outlined_text(draw, xy, text, font, fill=(255, 255, 255), outline=(0, 0, 0)):
    """Draw text with a 1px outline for readability on any background."""
    x, y = xy
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, fill=outline, font=font)
    draw.text((x, y), text, fill=fill, font=font)


# ============================================================
# Pattern 1: Corner Brackets
# ============================================================
def gen_corner_brackets():
    """L-shaped brackets in every cell corner.

    If you can see both arms of a bracket, that corner is visible.
    If one arm is cut off, the bezel hides that edge.
    Arms are 15px long, 3px wide. Easy to see at a glance.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (25, 25, 28))
    draw = ImageDraw.Draw(img)
    font = get_font(14)
    small = get_font(9)

    arm = 15  # arm length in pixels
    w = 3     # arm width

    # Use equal-division cells for measurement baseline
    for row in range(ROWS):
        for col in range(COLS):
            key = ROW_KEYS[row][col]
            cx = col * CELL_W
            cy = int(row * EQUAL_H)
            ch = int((row + 1) * EQUAL_H) - cy

            color = (255, 255, 255)

            # Top-left corner bracket
            draw.rectangle([cx, cy, cx + arm, cy + w - 1], fill=color)
            draw.rectangle([cx, cy, cx + w - 1, cy + arm], fill=color)

            # Top-right corner bracket
            draw.rectangle([cx + CELL_W - arm, cy, cx + CELL_W - 1, cy + w - 1], fill=color)
            draw.rectangle([cx + CELL_W - w, cy, cx + CELL_W - 1, cy + arm], fill=color)

            # Bottom-left corner bracket
            draw.rectangle([cx, cy + ch - w, cx + arm, cy + ch - 1], fill=color)
            draw.rectangle([cx, cy + ch - arm, cx + w - 1, cy + ch - 1], fill=color)

            # Bottom-right corner bracket
            draw.rectangle([cx + CELL_W - arm, cy + ch - w, cx + CELL_W - 1, cy + ch - 1], fill=color)
            draw.rectangle([cx + CELL_W - w, cy + ch - arm, cx + CELL_W - 1, cy + ch - 1], fill=color)

            # Key number in center
            text = str(key)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            outlined_text(draw, (cx + (CELL_W - tw) // 2, cy + (ch - th) // 2),
                          text, font, fill=(180, 180, 180))

    outlined_text(draw, (2, 2), "CORNER BRACKETS: Can you see both arms of each L?",
                  small, fill=(120, 120, 120))

    path = OUT_DIR / "1_corners.jpg"
    img.save(path, "JPEG", quality=99)
    print(f"  {path}")


# ============================================================
# Pattern 2: Edge Rulers (the main measurement tool)
# ============================================================
def gen_edge_rulers():
    """Numbered tick marks growing inward from each cell edge.

    Each edge has marks at 0, 3, 6, 9, 12, 15px depth.
    The first visible number = how many pixels the bezel hides.

    Colors: Red=top, Blue=bottom, Green=left, Yellow=right
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (25, 25, 28))
    draw = ImageDraw.Draw(img)
    num_font = get_font(8)
    key_font = get_font(12)
    small = get_font(9)

    tick_step = 3   # pixels between each tick mark
    max_depth = 18  # measure up to 18px from edge
    tick_h = 3      # tick thickness

    # Edge colors
    TOP_COLOR = (255, 80, 80)       # Red
    BOTTOM_COLOR = (80, 130, 255)   # Blue
    LEFT_COLOR = (80, 220, 80)      # Green
    RIGHT_COLOR = (255, 220, 50)    # Yellow

    for row in range(ROWS):
        for col in range(COLS):
            key = ROW_KEYS[row][col]
            cx = col * CELL_W
            cy = int(row * EQUAL_H)
            ch = int((row + 1) * EQUAL_H) - cy

            # --- TOP ruler (red) ---
            for depth in range(0, max_depth + 1, tick_step):
                y = cy + depth
                # Alternating bright/dim for clarity
                alpha = 1.0 if (depth // tick_step) % 2 == 0 else 0.6
                c = tuple(int(v * alpha) for v in TOP_COLOR)
                # Tick bar across most of cell width
                draw.rectangle([cx + 20, y, cx + CELL_W - 20, y + tick_h - 1], fill=c)
                # Number label
                label = str(depth)
                outlined_text(draw, (cx + 4, y - 1), label, num_font, fill=c)

            # --- BOTTOM ruler (blue) ---
            for depth in range(0, max_depth + 1, tick_step):
                y = cy + ch - 1 - depth - tick_h + 1
                alpha = 1.0 if (depth // tick_step) % 2 == 0 else 0.6
                c = tuple(int(v * alpha) for v in BOTTOM_COLOR)
                draw.rectangle([cx + 20, y, cx + CELL_W - 20, y + tick_h - 1], fill=c)
                label = str(depth)
                bbox = draw.textbbox((0, 0), label, num_font)
                lw = bbox[2] - bbox[0]
                outlined_text(draw, (cx + CELL_W - 4 - lw, y - 1), label, num_font, fill=c)

            # --- LEFT ruler (green) ---
            for depth in range(0, max_depth + 1, tick_step):
                x = cx + depth
                alpha = 1.0 if (depth // tick_step) % 2 == 0 else 0.6
                c = tuple(int(v * alpha) for v in LEFT_COLOR)
                draw.rectangle([x, cy + 20, x + tick_h - 1, cy + ch - 20], fill=c)
                label = str(depth)
                outlined_text(draw, (x, cy + ch - 18), label, num_font, fill=c)

            # --- RIGHT ruler (yellow) ---
            for depth in range(0, max_depth + 1, tick_step):
                x = cx + CELL_W - 1 - depth - tick_h + 1
                alpha = 1.0 if (depth // tick_step) % 2 == 0 else 0.6
                c = tuple(int(v * alpha) for v in RIGHT_COLOR)
                draw.rectangle([x, cy + 20, x + tick_h - 1, cy + ch - 20], fill=c)
                label = str(depth)
                bbox = draw.textbbox((0, 0), label, num_font)
                lw = bbox[2] - bbox[0]
                outlined_text(draw, (x - 1, cy + 18), label, num_font, fill=c)

            # Key number in center
            text = str(key)
            bbox = draw.textbbox((0, 0), text, font=key_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            outlined_text(draw, (cx + (CELL_W - tw) // 2, cy + (ch - th) // 2),
                          text, key_font, fill=(200, 200, 200))

    outlined_text(draw, (2, 2),
                  "RULERS: Report first visible number per edge. R=top B=bottom G=left Y=right",
                  small, fill=(120, 120, 120))

    path = OUT_DIR / "2_rulers.jpg"
    img.save(path, "JPEG", quality=99)
    print(f"  {path}")


# ============================================================
# Pattern 3: Full-bleed color fills per row
# ============================================================
def gen_row_fills():
    """Each row is a solid distinct color filling the full width.

    Helps confirm that the equal-division assumption (90.67px rows)
    is roughly correct before trusting the ruler measurements.
    Row boundaries drawn as thin white lines.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (25, 25, 28))
    draw = ImageDraw.Draw(img)
    font = get_font(20)
    small = get_font(9)

    row_colors = [(180, 50, 50), (50, 150, 50), (50, 80, 180)]

    for row in range(ROWS):
        cy = int(row * EQUAL_H)
        ch = int((row + 1) * EQUAL_H) - cy
        draw.rectangle([0, cy, SCREEN_W - 1, cy + ch - 1], fill=row_colors[row])

        # Row boundary line (white, 1px)
        if row > 0:
            draw.line([(0, cy), (SCREEN_W - 1, cy)], fill=(255, 255, 255), width=1)

        # Column boundary lines
        for col in range(1, COLS):
            x = col * CELL_W
            draw.line([(x, cy), (x, cy + ch - 1)], fill=(255, 255, 255), width=1)

        # Label each cell
        for col in range(COLS):
            key = ROW_KEYS[row][col]
            text = str(key)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            cx = col * CELL_W
            outlined_text(draw, (cx + (CELL_W - tw) // 2, cy + (ch - th) // 2),
                          text, font)

    outlined_text(draw, (2, 2),
                  "ROW FILLS: Does the white line between rows align with button gap?",
                  small, fill=(255, 255, 255))

    path = OUT_DIR / "3_row_fills.jpg"
    img.save(path, "JPEG", quality=99)
    print(f"  {path}")


if __name__ == "__main__":
    print("Generating calibration patterns...")
    gen_corner_brackets()
    gen_edge_rulers()
    gen_row_fills()
    print("Done!")
