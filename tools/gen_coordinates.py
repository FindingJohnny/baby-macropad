"""Generate coordinate ruler patterns to locate visible button areas.

Instead of assuming where cells are, these patterns show absolute pixel
coordinates so we can find where the physical button windows actually are.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SCREEN_W = 480
SCREEN_H = 272

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


def gen_y_ruler():
    """Horizontal stripes with Y coordinates.

    Every 10px: bright colored stripe with the Y value labeled.
    Every 5px: dimmer stripe.
    This tells you which Y pixel range is visible through each row of buttons.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (15, 15, 18))
    draw = ImageDraw.Draw(img)
    font = get_font(11)
    big_font = get_font(16)

    # Alternating colored bands every 10px
    colors_10 = [
        (200, 60, 60),   # red
        (60, 180, 60),   # green
        (60, 100, 220),  # blue
        (220, 180, 40),  # yellow
        (180, 60, 220),  # purple
        (60, 200, 180),  # teal
        (220, 120, 40),  # orange
    ]

    for y in range(0, SCREEN_H, 5):
        if y % 10 == 0:
            # Bold stripe every 10px
            color_idx = (y // 10) % len(colors_10)
            color = colors_10[color_idx]
            draw.rectangle([0, y, SCREEN_W - 1, y + 4], fill=color)

            # Label the Y value at multiple X positions so it's visible
            # through any column
            label = str(y)
            for lx in [5, 100, 200, 300, 400]:
                outlined_text(draw, (lx, y - 1), label, font, fill=(255, 255, 255))
        else:
            # Dim stripe at 5px intervals
            draw.rectangle([0, y, SCREEN_W - 1, y + 2], fill=(60, 60, 65))

    img.save(OUT_DIR / "10_y_ruler.jpg", "JPEG", quality=99)
    print("  10_y_ruler.jpg")


def gen_x_ruler():
    """Vertical stripes with X coordinates.

    Every 10px: bright colored stripe with the X value labeled.
    This tells you which X pixel range is visible through each column.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (15, 15, 18))
    draw = ImageDraw.Draw(img)
    font = get_font(9)

    colors_10 = [
        (200, 60, 60),
        (60, 180, 60),
        (60, 100, 220),
        (220, 180, 40),
        (180, 60, 220),
        (60, 200, 180),
        (220, 120, 40),
    ]

    for x in range(0, SCREEN_W, 5):
        if x % 10 == 0:
            color_idx = (x // 10) % len(colors_10)
            color = colors_10[color_idx]
            draw.rectangle([x, 0, x + 4, SCREEN_H - 1], fill=color)

            # Rotated labels are hard, so place horizontal labels at
            # multiple Y positions
            label = str(x)
            for ly in [5, 50, 95, 140, 185, 230]:
                outlined_text(draw, (x + 1, ly), label, font, fill=(255, 255, 255))
        else:
            draw.rectangle([x, 0, x + 2, SCREEN_H - 1], fill=(60, 60, 65))

    img.save(OUT_DIR / "11_x_ruler.jpg", "JPEG", quality=99)
    print("  11_x_ruler.jpg")


def gen_coarse_grid():
    """Large numbered grid — 20px blocks with coordinates.

    Each 20x20 block shows its (X,Y) coordinate. Alternating colors
    like a checkerboard. This gives a coarse overview of what's
    visible through each button.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (15, 15, 18))
    draw = ImageDraw.Draw(img)
    font = get_font(9)

    block = 20
    for by in range(0, SCREEN_H, block):
        for bx in range(0, SCREEN_W, block):
            checker = ((bx // block) + (by // block)) % 2
            if checker:
                color = (50, 50, 55)
            else:
                color = (80, 80, 90)
            draw.rectangle([bx, by, bx + block - 1, by + block - 1], fill=color)

            # Label every other block to avoid clutter
            if (bx // block) % 2 == 0 and (by // block) % 2 == 0:
                outlined_text(draw, (bx + 1, by + 1), f"{bx}", font, fill=(180, 180, 180))
                outlined_text(draw, (bx + 1, by + 11), f"{by}", font, fill=(140, 140, 140))

    # Draw major grid lines at 40px intervals
    for x in range(0, SCREEN_W, 40):
        draw.line([(x, 0), (x, SCREEN_H)], fill=(255, 255, 255), width=1)
    for y in range(0, SCREEN_H, 40):
        draw.line([(0, y), (SCREEN_W, y)], fill=(255, 255, 255), width=1)

    img.save(OUT_DIR / "12_coarse_grid.jpg", "JPEG", quality=99)
    print("  12_coarse_grid.jpg")


def gen_bright_center_dots():
    """Bright dots at specific known positions across the screen.

    Places a large bright circle every 48px horizontally and every 45px
    vertically, labeled with absolute coordinates. Helps confirm which
    positions are visible through which buttons.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (15, 15, 18))
    draw = ImageDraw.Draw(img)
    font = get_font(9)

    step_x = 48  # 480/10 = 48
    step_y = 27  # 272/~10 = 27

    for y in range(step_y // 2, SCREEN_H, step_y):
        for x in range(step_x // 2, SCREEN_W, step_x):
            # Bright circle
            r = 8
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 0))
            # Coordinate label
            label = f"{x},{y}"
            bbox = draw.textbbox((0, 0), label, font)
            lw = bbox[2] - bbox[0]
            outlined_text(draw, (x - lw // 2, y + r + 2), label, font,
                          fill=(200, 200, 200))

    img.save(OUT_DIR / "13_dots.jpg", "JPEG", quality=99)
    print("  13_dots.jpg")


if __name__ == "__main__":
    print("Generating coordinate patterns...")
    gen_y_ruler()
    gen_x_ruler()
    gen_coarse_grid()
    gen_bright_center_dots()
    print("Done!")
