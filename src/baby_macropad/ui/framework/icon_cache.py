"""Icon loading and tinting with caching.

Extracted from icons.py. Loads PNG assets, tints white pixels with a
target color, and caches results to avoid redundant disk I/O and
pixel-level processing.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Icon asset directory (relative to package root)
_ASSETS_DIR = Path(__file__).parent.parent.parent.parent / "assets" / "icons"

# Cache loaded + tinted icons
_icon_cache: dict[str, Image.Image] = {}


def load_and_tint(asset_name: str, color: tuple[int, int, int], size: int) -> Image.Image | None:
    """Load a white PNG icon, tint it with the given color, and resize."""
    cache_key = f"{asset_name}_{color}_{size}"
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    png_path = _ASSETS_DIR / f"{asset_name}.png"
    if not png_path.exists():
        logger.warning("Icon asset not found: %s", png_path)
        return None

    # Load white icon with alpha
    icon = Image.open(png_path).convert("RGBA")
    icon = icon.resize((size, size), Image.LANCZOS)

    # Tint: multiply white pixels by color, preserving alpha
    r, g, b = color
    pixels = icon.load()
    for y in range(icon.height):
        for x in range(icon.width):
            pr, pg, pb, pa = pixels[x, y]
            if pa > 0:
                # Scale the white pixel by the target color
                pixels[x, y] = (
                    pr * r // 255,
                    pg * g // 255,
                    pb * b // 255,
                    pa,
                )

    _icon_cache[cache_key] = icon
    return icon


def load_composite(
    asset_a: str,
    asset_b: str,
    color: tuple[int, int, int],
    size: int,
) -> Image.Image | None:
    """Render two icons as a 2x2 quadrant composite (a top-left, b bottom-right)."""
    half = size // 2
    a = load_and_tint(asset_a, color, half)
    b = load_and_tint(asset_b, color, half)
    if a is None or b is None:
        return None
    composite = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    composite.paste(a, (0, 0), a)
    composite.paste(b, (half, half), b)
    return composite
