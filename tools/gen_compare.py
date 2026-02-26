"""Generate labeled A/B/C comparison images for grid alignment testing."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

SCREEN_W = 480
SCREEN_H = 272
COLS = 5

# Key numbers per row (physical layout)
ROW_KEYS = [
    [11, 12, 13, 14, 15],  # top
    [6, 7, 8, 9, 10],      # middle
    [1, 2, 3, 4, 5],       # bottom
]

COLORS = [
    (220, 60, 60), (60, 180, 60), (60, 120, 220),
    (220, 180, 40), (180, 60, 220), (60, 200, 200),
    (220, 120, 60), (100, 220, 100), (100, 100, 220),
    (220, 220, 60), (220, 60, 180), (60, 220, 180),
    (180, 180, 60), (60, 60, 180), (180, 60, 60),
]

out_dir = Path("tools/test_images/compare")
out_dir.mkdir(parents=True, exist_ok=True)


def get_font(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc"]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_grid(row_y, row_h, label=""):
    """Render a numbered cell grid with given row positions."""
    cell_w = SCREEN_W // COLS
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (20, 20, 22))
    draw = ImageDraw.Draw(img)
    big_font = get_font(32)
    small_font = get_font(10)

    for row_idx in range(3):
        for col in range(5):
            key = ROW_KEYS[row_idx][col]
            color_idx = (row_idx * 5 + col) % len(COLORS)
            color = COLORS[color_idx]

            x = col * cell_w
            y = row_y[row_idx]
            h = row_h[row_idx]

            # Fill cell
            draw.rectangle([x, y, x + cell_w - 1, y + h - 1], fill=color)

            # Draw key number centered
            text = str(key)
            bbox = draw.textbbox((0, 0), text, font=big_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = x + (cell_w - tw) // 2
            ty = y + (h - th) // 2
            draw.text((tx, ty), text, fill=(255, 255, 255), font=big_font)

            # Small label
            sub = f"KEY_{key}"
            bbox2 = draw.textbbox((0, 0), sub, font=small_font)
            sw = bbox2[2] - bbox2[0]
            draw.text((x + (cell_w - sw) // 2, y + h - 16), sub,
                      fill=(255, 255, 255, 180), font=small_font)

    # Label in corner
    if label:
        draw.text((4, 2), label, fill=(255, 255, 255), font=small_font)

    return img


# Round 1: Coarse vertical position (shifts all rows)
configs_r1 = {
    "r1_A": ([0, 91, 182], [91, 91, 90], "A: Current (0, 91, 182)"),
    "r1_B": ([0, 91, 181], [91, 90, 91], "B: (0, 91, 181) h=91,90,91"),
    "r1_C": ([0, 90, 181], [90, 91, 91], "C: (0, 90, 181) h=90,91,91"),
}

# Round 2: Fine-tune row 0/1 boundary
configs_r2 = {
    "r2_A": ([0, 88, 179], [88, 91, 93], "A: Row0=88 Row1=91 Row2=93"),
    "r2_B": ([0, 89, 180], [89, 91, 92], "B: Row0=89 Row1=91 Row2=92"),
    "r2_C": ([0, 90, 181], [90, 91, 91], "C: Row0=90 Row1=91 Row2=91"),
    "r2_D": ([0, 91, 182], [91, 91, 90], "D: Row0=91 Row1=91 Row2=90"),
    "r2_E": ([0, 92, 183], [92, 91, 89], "E: Row0=92 Row1=91 Row2=89"),
    "r2_F": ([0, 93, 184], [93, 91, 88], "F: Row0=93 Row1=91 Row2=88"),
}

# Round 3: Fine-tune middle row height (keep row0 fixed, vary row1 height)
def gen_r3(r0h):
    """Generate round 3 variants with row0 height fixed."""
    configs = {}
    for r1h in range(88, 95):
        r2h = SCREEN_H - r0h - r1h
        if r2h < 85 or r2h > 95:
            continue
        name = f"r3_{r0h}_{r1h}"
        label = f"R0={r0h} R1={r1h} R2={r2h}"
        configs[name] = ([0, r0h, r0h + r1h], [r0h, r1h, r2h], label)
    return configs

# Generate round 3 for a range of row0 heights
for r0h in range(88, 95):
    for name, (ry, rh, label) in gen_r3(r0h).items():
        img = render_grid(ry, rh, label)
        img.save(out_dir / f"{name}.jpg", "JPEG", quality=92)

# Generate rounds 1 and 2
for name, (ry, rh, label) in {**configs_r1, **configs_r2}.items():
    img = render_grid(ry, rh, label)
    img.save(out_dir / f"{name}.jpg", "JPEG", quality=92)

print(f"Generated images in {out_dir}/")
for f in sorted(out_dir.glob("*.jpg")):
    print(f"  {f.name}")
