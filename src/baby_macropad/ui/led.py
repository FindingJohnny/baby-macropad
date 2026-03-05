"""LED ring controller with per-LED animations and quiet hours.

Manages LED flash animations with a generation counter pattern:
newer flashes cancel older ones by incrementing the counter.
Each flash thread checks the counter before sleeping to exit early
if superseded.

LED layout: 0-21 = ring, 22 = left button strip, 23 = right button strip.
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from datetime import time as dt_time
from typing import Callable

from baby_macropad.device import DeviceProtocol

logger = logging.getLogger(__name__)

_LED_COUNT = 24
_RING_COUNT = 22  # LEDs 0-21
_STRIP_LEFT = 22
_STRIP_RIGHT = 23

# Category colors for LED feedback
CATEGORY_COLORS: dict[str, tuple[int, int, int]] = {
    "feeding": (102, 204, 102),
    "diaper": (204, 170, 68),
    "sleep_start": (102, 153, 204),
    "sleep_end": (255, 220, 150),
    "pump": (200, 150, 255),
    "note": (200, 150, 255),
    "undo": (255, 255, 255),
    "queued": (255, 180, 0),
    "error": (220, 60, 60),
    "nav": (120, 120, 140),
    "sync": (0, 220, 80),
}

# Cotton candy tint pairs per category (color_a, color_b for sine blend)
_COTTON_CANDY_TINTS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "feeding": ((230, 120, 180), (102, 204, 102)),     # pink ↔ green
    "diaper": ((204, 170, 68), (255, 220, 130)),        # amber ↔ gold
    "pump": ((200, 150, 255), (150, 180, 255)),          # lavender ↔ blue
    "note": ((200, 150, 255), (230, 120, 180)),          # lavender ↔ pink
    "undo": ((255, 255, 255), (150, 180, 220)),          # white ↔ cool blue
}

# Quiet hours presets: setting value → (start_hour, end_hour)
QUIET_PRESETS: dict[str, tuple[int, int]] = {
    "9pm-6am": (21, 6),
    "10pm-6am": (22, 6),
    "8pm-6am": (20, 6),
}


def _clamp(v: int) -> int:
    return max(0, min(255, v))


def _lerp_color(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    return (
        _clamp(int(a[0] + (b[0] - a[0]) * t)),
        _clamp(int(a[1] + (b[1] - a[1]) * t)),
        _clamp(int(a[2] + (b[2] - a[2]) * t)),
    )


def _dim_color(c: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (_clamp(int(c[0] * factor)), _clamp(int(c[1] * factor)), _clamp(int(c[2] * factor)))


def _build_rgb_data(
    ring_colors: list[tuple[int, int, int]],
    strip_color: tuple[int, int, int],
) -> bytes:
    """Build 72-byte payload from 22 ring LEDs + 2 strip LEDs."""
    data = bytearray(72)
    for i in range(min(len(ring_colors), _RING_COUNT)):
        r, g, b = ring_colors[i]
        data[i * 3] = _clamp(r)
        data[i * 3 + 1] = _clamp(g)
        data[i * 3 + 2] = _clamp(b)
    # Fill remaining ring LEDs with black if ring_colors is short
    # Strip LEDs at positions 22 and 23
    data[_STRIP_LEFT * 3] = _clamp(strip_color[0])
    data[_STRIP_LEFT * 3 + 1] = _clamp(strip_color[1])
    data[_STRIP_LEFT * 3 + 2] = _clamp(strip_color[2])
    data[_STRIP_RIGHT * 3] = _clamp(strip_color[0])
    data[_STRIP_RIGHT * 3 + 1] = _clamp(strip_color[1])
    data[_STRIP_RIGHT * 3 + 2] = _clamp(strip_color[2])
    return bytes(data)


class LedController:
    """Manages LED ring state and flash animations.

    The generation counter ensures that if a new flash is requested while
    a previous animation is still running, the old one exits early.
    """

    def __init__(self, device: DeviceProtocol) -> None:
        self._device = device
        self._generation = 0
        self._lock = threading.Lock()
        self._quiet_hours_setting: str = "off"

    @property
    def quiet_hours_setting(self) -> str:
        return self._quiet_hours_setting

    @quiet_hours_setting.setter
    def quiet_hours_setting(self, value: str) -> None:
        self._quiet_hours_setting = value

    def _next_gen(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def _is_current(self, gen: int) -> bool:
        with self._lock:
            return self._generation == gen

    def _is_quiet_hours(self) -> bool:
        if self._quiet_hours_setting == "off":
            return False
        preset = QUIET_PRESETS.get(self._quiet_hours_setting)
        if not preset:
            return False
        start_h, end_h = preset
        now = dt_time.fromisoformat(time.strftime("%H:%M:%S"))
        start = dt_time(start_h, 0)
        end = dt_time(end_h, 0)
        if start > end:
            return now >= start or now < end
        return start <= now < end

    def _apply_quiet_hours_rgb(self, rgb_data: bytes) -> bytes:
        """Dim to 30% and clamp blue channel to shift blue → amber."""
        data = bytearray(rgb_data)
        for i in range(0, len(data), 3):
            data[i] = _clamp(int(data[i] * 0.3))
            data[i + 1] = _clamp(int(data[i + 1] * 0.3))
            data[i + 2] = _clamp(min(int(data[i + 2] * 0.3), 40))
        return bytes(data)

    def _apply_quiet_hours_brightness(self, brightness: int) -> int:
        return min(brightness, 30)

    def _animate(
        self,
        duration: float,
        fps: int,
        frame_fn: Callable[[int, float], tuple[bytes, int]],
    ) -> None:
        """Run a per-LED animation. frame_fn(frame_num, progress) -> (72-byte rgb_data, brightness)."""
        gen = self._next_gen()

        def _run() -> None:
            interval = 1.0 / fps
            frames = int(duration * fps)
            quiet = self._is_quiet_hours()
            for f in range(frames):
                if not self._is_current(gen):
                    return
                rgb_data, brightness = frame_fn(f, f / max(frames - 1, 1))
                if quiet:
                    rgb_data = self._apply_quiet_hours_rgb(rgb_data)
                    brightness = self._apply_quiet_hours_brightness(brightness)
                self._device.set_led_colors(rgb_data)
                self._device.set_led_brightness(brightness)
                time.sleep(interval)
            if self._is_current(gen):
                self._device.turn_off_leds()

        threading.Thread(target=_run, daemon=True).start()

    # --- Public flash methods ---

    def flash_acknowledge(self, category: str = "nav") -> None:
        """Brief category-hint pulse on key press — dim color confirms what was registered.

        120ms, low brightness. The success animation that follows an API call
        (~200ms later) is the dominant visual feedback.
        """
        color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["nav"])
        self._flash_simple(color, brightness=35, duration=0.12)

    def flash_success(self, category: str) -> None:
        """Cotton candy spin+breathe animation tinted by category (primary success feedback).

        2s at 25fps. Ring shows spinning sine blend, button strips hold solid category color.
        """
        cat_color = CATEGORY_COLORS.get(category, (200, 200, 200))
        tints = _COTTON_CANDY_TINTS.get(category, ((230, 180, 220), cat_color))
        color_a, color_b = tints

        def _frame(f: int, progress: float) -> tuple[bytes, int]:
            # Breathing envelope (sine wave, 0.5-1.0 range)
            breath = 0.5 + 0.5 * math.sin(progress * math.pi * 4)
            # Spinning offset
            spin = progress * _RING_COUNT * 2

            ring: list[tuple[int, int, int]] = []
            for i in range(_RING_COUNT):
                # Sine blend between two colors, offset per LED
                t = 0.5 + 0.5 * math.sin((i + spin) * math.pi / 5)
                base = _lerp_color(color_a, color_b, t)
                ring.append(_dim_color(base, breath))

            rgb_data = _build_rgb_data(ring, cat_color)
            brightness = int(70 + 20 * breath)
            return rgb_data, brightness

        self._animate(2.0, 25, _frame)

    def flash_sleep_start(self) -> None:
        """Blue breathing wave for sleep start (3 pulses)."""
        color = CATEGORY_COLORS["sleep_start"]

        def _frame(f: int, progress: float) -> tuple[bytes, int]:
            # 3 pulses over the duration
            pulse = 0.5 + 0.5 * math.sin(progress * math.pi * 6)
            wave_ring: list[tuple[int, int, int]] = []
            for i in range(_RING_COUNT):
                wave = 0.5 + 0.5 * math.sin((i / _RING_COUNT + progress * 3) * math.pi * 2)
                c = _dim_color(color, pulse * wave)
                wave_ring.append(c)
            rgb_data = _build_rgb_data(wave_ring, _dim_color(color, pulse))
            return rgb_data, int(50 * pulse)

        self._animate(2.0, 25, _frame)

    def flash_wake(self) -> None:
        """Warm sunrise sweep (amber → white) burst + fade."""
        amber = (255, 160, 50)
        warm_white = CATEGORY_COLORS["sleep_end"]

        def _frame(f: int, progress: float) -> tuple[bytes, int]:
            # Sweep from amber to warm white
            color = _lerp_color(amber, warm_white, min(progress * 2, 1.0))
            # Brightness: burst then fade
            if progress < 0.3:
                bright = 100
            else:
                bright = int(100 * (1.0 - (progress - 0.3) / 0.7))
            ring = [color] * _RING_COUNT
            return _build_rgb_data(ring, warm_white), max(bright, 0)

        self._animate(1.5, 25, _frame)

    def flash_queued(self) -> None:
        """Amber slow pulse for queued/offline (3 beats)."""
        color = CATEGORY_COLORS["queued"]

        def _frame(f: int, progress: float) -> tuple[bytes, int]:
            pulse = 0.5 + 0.5 * math.sin(progress * math.pi * 6)
            ring = [_dim_color(color, pulse)] * _RING_COUNT
            return _build_rgb_data(ring, _dim_color(color, pulse)), int(55 * pulse)

        self._animate(2.5, 20, _frame)

    def flash_error(self) -> None:
        """Red double-pulse (slow double reads as 'error', not 'alarm')."""
        color = CATEGORY_COLORS["error"]
        gen = self._next_gen()

        def _flash() -> None:
            quiet = self._is_quiet_hours()
            for _ in range(2):
                if not self._is_current(gen):
                    return
                ring = [color] * _RING_COUNT
                rgb_data = _build_rgb_data(ring, color)
                bright = 80
                if quiet:
                    rgb_data = self._apply_quiet_hours_rgb(rgb_data)
                    bright = self._apply_quiet_hours_brightness(bright)
                self._device.set_led_colors(rgb_data)
                self._device.set_led_brightness(bright)
                time.sleep(0.25)
                if not self._is_current(gen):
                    return
                self._device.turn_off_leds()
                time.sleep(0.2)

        threading.Thread(target=_flash, daemon=True).start()

    def flash_undo(self) -> None:
        """White outward sweep on ring (400ms)."""
        color = CATEGORY_COLORS["undo"]

        def _frame(f: int, progress: float) -> tuple[bytes, int]:
            ring: list[tuple[int, int, int]] = []
            center = _RING_COUNT // 2
            for i in range(_RING_COUNT):
                dist = abs(i - center) / center
                # LED lights up when sweep reaches it
                if dist <= progress:
                    fade = max(0.0, 1.0 - (progress - dist) * 3)
                    ring.append(_dim_color(color, fade))
                else:
                    ring.append((0, 0, 0))
            return _build_rgb_data(ring, color if progress < 0.7 else (0, 0, 0)), 65

        self._animate(0.4, 30, _frame)

    def flash_sync_success(self) -> None:
        """Green sparkle (random LEDs) for successful offline sync."""
        color = CATEGORY_COLORS["sync"]

        def _frame(f: int, progress: float) -> tuple[bytes, int]:
            ring: list[tuple[int, int, int]] = []
            for _ in range(_RING_COUNT):
                if random.random() < 0.3:
                    ring.append(_dim_color(color, 0.5 + random.random() * 0.5))
                else:
                    ring.append((0, 0, 0))
            return _build_rgb_data(ring, color), 50

        self._animate(0.3, 25, _frame)

    def clear(self) -> None:
        """Cancel all animations and turn LEDs off."""
        self._next_gen()
        self._device.turn_off_leds()

    # --- Private helpers ---

    def _flash_simple(
        self, color: tuple[int, int, int], brightness: int = 50, duration: float = 0.5
    ) -> None:
        """Flash a single color (all LEDs) then turn off. Generation-counter protected.

        LED-on commands run synchronously on the caller's thread so they
        execute BEFORE any screen refresh grabs the write lock. Only the
        delayed turn-off runs in a background thread.
        """
        gen = self._next_gen()
        quiet = self._is_quiet_hours()
        ring = [color] * _RING_COUNT
        rgb_data = _build_rgb_data(ring, color)
        if quiet:
            rgb_data = self._apply_quiet_hours_rgb(rgb_data)
            brightness = self._apply_quiet_hours_brightness(brightness)
        logger.info(
            "LED flash: color=%s bright=%d dur=%.2f gen=%d quiet=%s",
            color, brightness, duration, gen, quiet,
        )
        self._device.set_led_colors(rgb_data)
        self._device.set_led_brightness(brightness)

        def _turn_off() -> None:
            time.sleep(duration)
            if self._is_current(gen):
                logger.info("LED off (gen=%d current)", gen)
                self._device.turn_off_leds()
            else:
                logger.info("LED off skipped (gen=%d stale)", gen)

        threading.Thread(target=_turn_off, daemon=True).start()
