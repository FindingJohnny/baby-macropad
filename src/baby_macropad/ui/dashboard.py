"""480x272 touchscreen dashboard renderer using Pillow."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .framework.primitives import BG_COLOR, SCREEN_H, SCREEN_W, SECONDARY_TEXT

logger = logging.getLogger(__name__)

SCREEN_SIZE = (SCREEN_W, SCREEN_H)

# Colors from the UX design doc (dark mode)
SURFACE_COLOR = (44, 44, 46)      # bbSurface dark
TEXT_PRIMARY = (229, 229, 231)     # bbText dark
TEXT_SECONDARY = SECONDARY_TEXT    # bbTextSecondary dark
FEED_ACCENT = (143, 184, 150)     # Desaturated jewel green
DIAPER_ACCENT = (196, 149, 106)   # Desaturated jewel amber
SLEEP_ACCENT = (123, 155, 196)    # Desaturated jewel blue
SUCCESS_COLOR = (102, 187, 106)   # bbSuccess dark
WARNING_COLOR = (255, 167, 38)    # bbWarning dark
ERROR_COLOR = (239, 83, 80)       # bbDanger dark


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load DejaVu Sans or fall back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in font_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _get_bold_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    bold_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in bold_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return _get_font(size)


def _elapsed_str(timestamp_str: str | None) -> str:
    """Convert an ISO timestamp to a human-readable elapsed time string."""
    if not timestamp_str:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        total_minutes = int(delta.total_seconds() / 60)
        if total_minutes < 1:
            return "Just now"
        if total_minutes < 60:
            return f"{total_minutes}m ago"
        hours = total_minutes // 60
        mins = total_minutes % 60
        if hours < 24:
            return f"{hours}h {mins}m ago" if mins else f"{hours}h ago"
        days = hours // 24
        return f"{days}d ago"
    except (ValueError, TypeError):
        return "Unknown"


def _elapsed_duration(timestamp_str: str | None) -> str:
    """Convert an ISO start time to an ongoing duration string."""
    if not timestamp_str:
        return "0m"
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        total_minutes = int(delta.total_seconds() / 60)
        if total_minutes < 60:
            return f"{total_minutes}m"
        hours = total_minutes // 60
        mins = total_minutes % 60
        return f"{hours}h {mins}m"
    except (ValueError, TypeError):
        return "0m"


def render_dashboard(
    dashboard_data: dict[str, Any] | None = None,
    connected: bool = True,
    queued_count: int = 0,
) -> Image.Image:
    """Render the 480x272 touchscreen dashboard image.

    Args:
        dashboard_data: Parsed dashboard response (or None for initial/offline state)
        connected: Whether the API is reachable
        queued_count: Number of events in the offline queue

    Returns:
        PIL Image (480x272, RGB) ready for set_touchscreen_image()
    """
    img = Image.new("RGB", SCREEN_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_sm = _get_font(14)
    font_md = _get_font(18)
    font_lg = _get_bold_font(24)
    font_xl = _get_bold_font(28)

    # === Top bar: Clock + Connection ===
    now_str = datetime.now().strftime("%I:%M %p")
    draw.text((12, 6), now_str, fill=TEXT_SECONDARY, font=font_md)

    if connected:
        status_text = "Connected"
        status_color = SUCCESS_COLOR
    elif queued_count > 0:
        status_text = f"Queued ({queued_count})"
        status_color = WARNING_COLOR
    else:
        status_text = "Offline"
        status_color = ERROR_COLOR

    # Right-align status
    bbox = draw.textbbox((0, 0), status_text, font=font_sm)
    status_w = bbox[2] - bbox[0]
    draw.text((SCREEN_SIZE[0] - status_w - 12, 8), status_text, fill=status_color, font=font_sm)

    # Separator line
    draw.line([(8, 30), (472, 30)], fill=SURFACE_COLOR, width=1)

    if not dashboard_data:
        draw.text((120, 120), "Waiting for data...", fill=TEXT_SECONDARY, font=font_lg)
        return img

    # === Hero: Sleep status ===
    active_sleep = dashboard_data.get("active_sleep")
    if active_sleep:
        sleep_duration = _elapsed_duration(active_sleep.get("start_time"))
        hero_text = f"Sleeping: {sleep_duration}"
        hero_color = SLEEP_ACCENT
        hero_icon = "\u263e"  # moon
    else:
        last_sleep = dashboard_data.get("last_sleep")
        if last_sleep and last_sleep.get("end_time"):
            awake_time = _elapsed_duration(last_sleep["end_time"])
            hero_text = f"Awake: {awake_time}"
        else:
            hero_text = "Awake"
        hero_color = TEXT_PRIMARY
        hero_icon = "\u2600"  # sun

    draw.text((16, 46), hero_text, fill=hero_color, font=font_xl)

    # === Two-column detail ===
    col_y = 100
    mid_x = SCREEN_SIZE[0] // 2

    # Left column: Last feeding
    draw.text((16, col_y), "LAST FEED", fill=TEXT_SECONDARY, font=font_sm)
    last_feeding = dashboard_data.get("last_feeding")
    if last_feeding:
        feed_time = _elapsed_str(last_feeding.get("created_at") or last_feeding.get("timestamp"))
        draw.text((16, col_y + 20), feed_time, fill=TEXT_PRIMARY, font=font_md)

        feed_type = last_feeding.get("type", "")
        side = last_feeding.get("started_side", "")
        detail = f"{side.capitalize()} breast" if feed_type == "breast" and side else feed_type.capitalize()
        draw.text((16, col_y + 44), detail, fill=FEED_ACCENT, font=font_sm)

        suggested = dashboard_data.get("suggested_side")
        if suggested:
            draw.text((16, col_y + 62), f"Next: {suggested.capitalize()}", fill=TEXT_SECONDARY, font=font_sm)
    else:
        draw.text((16, col_y + 20), "No data", fill=TEXT_SECONDARY, font=font_md)

    # Vertical separator
    draw.line([(mid_x - 4, col_y), (mid_x - 4, col_y + 80)], fill=SURFACE_COLOR, width=1)

    # Right column: Last diaper
    draw.text((mid_x + 8, col_y), "LAST DIAPER", fill=TEXT_SECONDARY, font=font_sm)
    last_diaper = dashboard_data.get("last_diaper")
    if last_diaper:
        diaper_time = _elapsed_str(last_diaper.get("created_at") or last_diaper.get("timestamp"))
        draw.text((mid_x + 8, col_y + 20), diaper_time, fill=TEXT_PRIMARY, font=font_md)

        diaper_type = last_diaper.get("type", "unknown").capitalize()
        draw.text((mid_x + 8, col_y + 44), diaper_type, fill=DIAPER_ACCENT, font=font_sm)
    else:
        draw.text((mid_x + 8, col_y + 20), "No data", fill=TEXT_SECONDARY, font=font_md)

    # === Bottom bar: Today's counts ===
    draw.line([(8, 214), (472, 214)], fill=SURFACE_COLOR, width=1)

    counts = dashboard_data.get("today_counts", {})
    feeds = counts.get("feedings", 0)
    pee = counts.get("pee", counts.get("diapers_pee", 0))
    poop = counts.get("poop", counts.get("diapers_poop", 0))
    sleep_hrs = counts.get("sleep_hours", 0)

    if isinstance(sleep_hrs, (int, float)):
        sleep_str = f"{sleep_hrs:.1f}h" if sleep_hrs else "0h"
    else:
        sleep_str = str(sleep_hrs)

    summary = f"TODAY:  {feeds} feeds  |  {pee} pee  |  {poop} poop  |  {sleep_str} sleep"
    draw.text((16, 230), summary, fill=TEXT_SECONDARY, font=font_sm)

    return img


def save_dashboard(
    output_path: Path,
    dashboard_data: dict[str, Any] | None = None,
    connected: bool = True,
    queued_count: int = 0,
) -> Path:
    """Render and save dashboard image as JPEG."""
    img = render_dashboard(dashboard_data, connected, queued_count)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=85)
    return output_path
