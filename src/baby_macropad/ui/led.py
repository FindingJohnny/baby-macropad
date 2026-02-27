"""LED ring controller extracted from main.py.

Manages LED flash animations with a generation counter pattern:
newer flashes cancel older ones by incrementing the counter.
Each flash thread checks the counter before sleeping to exit early
if superseded.
"""

from __future__ import annotations

import threading
import time
from typing import Any

# Category colors for LED feedback
CATEGORY_COLORS = {
    "feeding": (102, 204, 102),
    "diaper": (204, 170, 68),
    "sleep_start": (102, 153, 204),
    "sleep_end": (255, 220, 150),
    "note": (153, 153, 153),
    "pump": (153, 153, 153),
    "undo": (255, 255, 255),
    "queued": (255, 180, 0),
    "error": (220, 60, 60),
    "acknowledge": (255, 255, 255),
}


class LedController:
    """Manages LED ring state and flash animations.

    The generation counter ensures that if a new flash is requested while
    a previous animation is still running, the old one exits early.
    """

    def __init__(self, device: Any) -> None:
        self._device = device
        self._generation = 0
        self._lock = threading.Lock()

    def _next_gen(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def _is_current(self, gen: int) -> bool:
        with self._lock:
            return self._generation == gen

    def flash_acknowledge(self) -> None:
        """Immediate white flash on any key press (150ms)."""
        r, g, b = CATEGORY_COLORS["acknowledge"]
        self._flash_simple(r, g, b, brightness=60, duration=0.15)

    def flash_category(self, category: str) -> None:
        """Flash the LED ring in the category color."""
        if category in ("feeding", "diaper"):
            r, g, b = CATEGORY_COLORS[category]
            self._flash_simple(r, g, b, brightness=65, duration=0.6)
        elif category in ("pump", "note"):
            r, g, b = CATEGORY_COLORS["note"]
            self._flash_simple(r, g, b, brightness=50, duration=0.4)

    def flash_sleep_start(self) -> None:
        """Blue triple pulse for sleep start."""
        gen = self._next_gen()

        def _pulse():
            r, g, b = CATEGORY_COLORS["sleep_start"]
            for _ in range(3):
                if not self._is_current(gen):
                    return
                self._device.set_led_color(r, g, b)
                self._device.set_led_brightness(50)
                time.sleep(0.3)
                if not self._is_current(gen):
                    return
                self._device.turn_off_leds()
                time.sleep(0.2)

        threading.Thread(target=_pulse, daemon=True).start()

    def flash_wake(self) -> None:
        """Warm white burst for wake up (400ms full, fade out)."""
        gen = self._next_gen()

        def _burst():
            r, g, b = CATEGORY_COLORS["sleep_end"]
            self._device.set_led_color(r, g, b)
            self._device.set_led_brightness(100)
            time.sleep(0.4)
            for level in (80, 60, 40, 20, 0):
                if not self._is_current(gen):
                    return
                self._device.set_led_brightness(level)
                time.sleep(0.12)
            self._device.turn_off_leds()

        threading.Thread(target=_burst, daemon=True).start()

    def flash_queued(self) -> None:
        """Amber triple beat for queued/offline."""
        gen = self._next_gen()

        def _beat():
            r, g, b = CATEGORY_COLORS["queued"]
            for _ in range(3):
                if not self._is_current(gen):
                    return
                self._device.set_led_color(r, g, b)
                self._device.set_led_brightness(55)
                time.sleep(0.5)
                if not self._is_current(gen):
                    return
                self._device.turn_off_leds()
                time.sleep(0.3)

        threading.Thread(target=_beat, daemon=True).start()

    def flash_error(self) -> None:
        """Red triple flash for error."""
        gen = self._next_gen()

        def _flash():
            r, g, b = CATEGORY_COLORS["error"]
            for _ in range(3):
                if not self._is_current(gen):
                    return
                self._device.set_led_color(r, g, b)
                self._device.set_led_brightness(80)
                time.sleep(0.2)
                if not self._is_current(gen):
                    return
                self._device.turn_off_leds()
                time.sleep(0.1)

        threading.Thread(target=_flash, daemon=True).start()

    def flash_undo(self) -> None:
        """White flash for undo (300ms)."""
        r, g, b = CATEGORY_COLORS["undo"]
        self._flash_simple(r, g, b, brightness=65, duration=0.3)

    def flash_sync_success(self) -> None:
        """Short green flash for successful offline sync."""
        self._flash_simple(0, 255, 0, duration=0.3)

    def clear(self) -> None:
        """Cancel all animations and turn LEDs off."""
        self._next_gen()
        self._device.turn_off_leds()

    def _flash_simple(
        self, r: int, g: int, b: int, brightness: int = 50, duration: float = 0.5
    ) -> None:
        """Flash a single color then turn off. Generation-counter protected."""
        gen = self._next_gen()

        def _do_flash():
            self._device.set_led_color(r, g, b)
            self._device.set_led_brightness(brightness)
            time.sleep(duration)
            if self._is_current(gen):
                self._device.turn_off_leds()

        threading.Thread(target=_do_flash, daemon=True).start()
