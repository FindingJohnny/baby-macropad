"""Generate cleaner edge measurement patterns — one edge at a time."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SCREEN_W = 480
SCREEN_H = 272
COLS = 5
ROWS = 3
CELL_W = SCREEN_W // COLS  # 96
EQUAL_H = SCREEN_H / ROWS  # 90.67

ROW_KEYS = [
    [11, 12, 13, 14, 15],
    [6, 7, 8, 9, 10],
    [1, 2, 3, 4, 5],
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


def outlined_text(draw, xy, text, font, fill=(255, 255, 255)):
    x, y = xy
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font)
    draw.text((x, y), text, fill=fill, font=font)


def cell_rect(row, col):
    """Return (x, y, w, h) for a cell using equal division."""
    cx = col * CELL_W
    cy = int(row * EQUAL_H)
    ch = int((row + 1) * EQUAL_H) - cy
    return cx, cy, CELL_W, ch


def gen_top_edge():
    """Horizontal bars growing DOWN from the top of each cell.

    Bars at 0, 3, 6, 9, 12, 15px from top edge.
    Each bar is 3px tall, colored, with the depth number next to it.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (25, 25, 28))
    draw = ImageDraw.Draw(img)
    font = get_font(10)
    key_font = get_font(16)

    for row in range(ROWS):
        for col in range(COLS):
            cx, cy, cw, ch = cell_rect(row, col)
            key = ROW_KEYS[row][col]

            # Draw bars from top edge inward
            for depth in range(0, 18, 3):
                y = cy + depth
                bright = 255 if (depth // 3) % 2 == 0 else 160
                color = (bright, int(bright * 0.3), int(bright * 0.3))  # Red shades

                # Bar spans most of cell width
                draw.rectangle([cx + 2, y, cx + cw - 20, y + 2], fill=color)
                # Number label on the right side
                outlined_text(draw, (cx + cw - 17, y - 2), str(depth), font, fill=color)

            # Key number in lower half
            text = str(key)
            bbox = draw.textbbox((0, 0), text, font=key_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            outlined_text(draw, (cx + (cw - tw) // 2, cy + ch - th - 10), text, key_font)

    outlined_text(draw, (2, SCREEN_H - 14),
                  "TOP EDGE: What is the smallest red number you can see?",
                  get_font(9), fill=(200, 150, 150))

    img.save(OUT_DIR / "4_top_edge.jpg", "JPEG", quality=99)
    print("  4_top_edge.jpg")


def gen_bottom_edge():
    """Horizontal bars growing UP from the bottom of each cell."""
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (25, 25, 28))
    draw = ImageDraw.Draw(img)
    font = get_font(10)
    key_font = get_font(16)

    for row in range(ROWS):
        for col in range(COLS):
            cx, cy, cw, ch = cell_rect(row, col)
            key = ROW_KEYS[row][col]

            for depth in range(0, 18, 3):
                y = cy + ch - 1 - depth - 2
                bright = 255 if (depth // 3) % 2 == 0 else 160
                color = (int(bright * 0.3), int(bright * 0.5), bright)  # Blue shades

                draw.rectangle([cx + 2, y, cx + cw - 20, y + 2], fill=color)
                outlined_text(draw, (cx + cw - 17, y - 2), str(depth), font, fill=color)

            text = str(key)
            bbox = draw.textbbox((0, 0), text, font=key_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            outlined_text(draw, (cx + (cw - tw) // 2, cy + 8), text, key_font)

    outlined_text(draw, (2, 2),
                  "BOTTOM EDGE: What is the smallest blue number you can see?",
                  get_font(9), fill=(150, 170, 220))

    img.save(OUT_DIR / "5_bottom_edge.jpg", "JPEG", quality=99)
    print("  5_bottom_edge.jpg")


def gen_left_edge():
    """Vertical bars growing RIGHT from the left of each cell."""
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (25, 25, 28))
    draw = ImageDraw.Draw(img)
    font = get_font(10)
    key_font = get_font(16)

    for row in range(ROWS):
        for col in range(COLS):
            cx, cy, cw, ch = cell_rect(row, col)
            key = ROW_KEYS[row][col]

            for depth in range(0, 18, 3):
                x = cx + depth
                bright = 255 if (depth // 3) % 2 == 0 else 160
                color = (int(bright * 0.3), bright, int(bright * 0.3))  # Green shades

                draw.rectangle([x, cy + 2, x + 2, cy + ch - 16], fill=color)
                outlined_text(draw, (x - 1, cy + ch - 14), str(depth), font, fill=color)

            text = str(key)
            bbox = draw.textbbox((0, 0), text, font=key_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            outlined_text(draw, (cx + cw - tw - 8, cy + (ch - th) // 2), text, key_font)

    outlined_text(draw, (SCREEN_W - 280, 2),
                  "LEFT EDGE: Smallest green number visible?",
                  get_font(9), fill=(150, 220, 150))

    img.save(OUT_DIR / "6_left_edge.jpg", "JPEG", quality=99)
    print("  6_left_edge.jpg")


def gen_right_edge():
    """Vertical bars growing LEFT from the right of each cell."""
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (25, 25, 28))
    draw = ImageDraw.Draw(img)
    font = get_font(10)
    key_font = get_font(16)

    for row in range(ROWS):
        for col in range(COLS):
            cx, cy, cw, ch = cell_rect(row, col)
            key = ROW_KEYS[row][col]

            for depth in range(0, 18, 3):
                x = cx + cw - 1 - depth - 2
                bright = 255 if (depth // 3) % 2 == 0 else 160
                color = (bright, bright, int(bright * 0.2))  # Yellow shades

                draw.rectangle([x, cy + 2, x + 2, cy + ch - 16], fill=color)
                bbox = draw.textbbox((0, 0), str(depth), font)
                lw = bbox[2] - bbox[0]
                outlined_text(draw, (x + 2 - lw, cy + ch - 14), str(depth), font, fill=color)

            text = str(key)
            bbox = draw.textbbox((0, 0), text, font=key_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            outlined_text(draw, (cx + 8, cy + (ch - th) // 2), text, key_font)

    outlined_text(draw, (2, 2),
                  "RIGHT EDGE: Smallest yellow number visible?",
                  get_font(9), fill=(220, 220, 150))

    img.save(OUT_DIR / "7_right_edge.jpg", "JPEG", quality=99)
    print("  7_right_edge.jpg")


if __name__ == "__main__":
    print("Generating edge measurement patterns...")
    gen_top_edge()
    gen_bottom_edge()
    gen_left_edge()
    gen_right_edge()
    print("Done!")
