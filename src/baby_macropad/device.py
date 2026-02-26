"""Stream Dock M18 device wrapper.

Abstracts the StreamDock SDK so the rest of the app doesn't depend on it.
Falls back to a stub when the SDK is not installed (development/testing).
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

KeyCallback = Callable[[int, bool], None]  # (key_number, is_pressed)


class DeviceError(Exception):
    pass


class StreamDockDevice:
    """Wrapper around the StreamDock SDK device."""

    def __init__(self) -> None:
        self._device: Any = None
        self._read_thread: threading.Thread | None = None
        self._key_callback: KeyCallback | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def open(self) -> bool:
        """Discover and open the first StreamDock device.

        Returns True if a device was found and opened.
        """
        try:
            from StreamDock.DeviceManager import DeviceManager
        except ImportError:
            logger.warning("StreamDock SDK not installed — running in stub mode")
            return False

        try:
            manager = DeviceManager()
            devices = manager.enumerate()
            if not devices:
                logger.warning("No StreamDock devices found")
                return False

            self._device = devices[0]
            self._device.open()
            self._device.refresh()
            self._connected = True
            logger.info("StreamDock device opened")
            return True
        except Exception:
            logger.exception("Failed to open StreamDock device")
            return False

    def close(self) -> None:
        """Close the device connection."""
        if self._device:
            try:
                self._device.clearAllIcon()
                self._device.close()
            except Exception:
                logger.exception("Error closing device")
            self._device = None
            self._connected = False
            logger.info("StreamDock device closed")

    def set_brightness(self, level: int) -> None:
        if self._device:
            self._device.set_brightness(level)

    def set_key_image(self, key: int, image_path: str | Path) -> None:
        """Set the icon on a specific key (1-15)."""
        if self._device:
            self._device.set_key_image(str(image_path), key)

    def set_touchscreen_image(self, image_path: str | Path) -> None:
        """Set the full touchscreen background image."""
        if self._device:
            self._device.set_touchscreen_image(str(image_path))

    def set_led_color(self, r: int, g: int, b: int) -> None:
        """Set the LED ring color."""
        if self._device:
            try:
                self._device.set_led_color(r, g, b)
            except (AttributeError, Exception):
                pass  # Not all models support LED control

    def set_led_brightness(self, level: int) -> None:
        if self._device:
            try:
                self._device.set_led_brightness(level)
            except (AttributeError, Exception):
                pass

    def set_key_callback(self, callback: KeyCallback) -> None:
        """Register a callback for key press/release events."""
        self._key_callback = callback

    def start_listening(self) -> None:
        """Start listening for key events in a background thread."""
        if not self._device:
            return

        def _key_handler(device: Any, key: int, state: int) -> None:
            is_pressed = state == 1
            if self._key_callback:
                self._key_callback(key, is_pressed)

        self._device.set_key_callback(_key_handler)
        self._read_thread = threading.Thread(
            target=self._device.whileread,
            daemon=True,
            name="streamdock-reader",
        )
        self._read_thread.start()
        logger.info("Key event listener started")


class StubDevice:
    """Stub device for testing without hardware."""

    def __init__(self) -> None:
        self._key_callback: KeyCallback | None = None
        self._brightness = 80
        self._led_color = (0, 0, 0)

    @property
    def connected(self) -> bool:
        return True

    def open(self) -> bool:
        logger.info("Stub device opened")
        return True

    def close(self) -> None:
        logger.info("Stub device closed")

    def set_brightness(self, level: int) -> None:
        self._brightness = level

    def set_key_image(self, key: int, image_path: str | Path) -> None:
        logger.debug("Stub: set key %d image to %s", key, image_path)

    def set_touchscreen_image(self, image_path: str | Path) -> None:
        logger.debug("Stub: set touchscreen to %s", image_path)

    def set_led_color(self, r: int, g: int, b: int) -> None:
        self._led_color = (r, g, b)
        logger.debug("Stub: LED color set to (%d, %d, %d)", r, g, b)

    def set_led_brightness(self, level: int) -> None:
        logger.debug("Stub: LED brightness set to %d", level)

    def set_key_callback(self, callback: KeyCallback) -> None:
        self._key_callback = callback

    def start_listening(self) -> None:
        logger.info("Stub: key listener started (no-op)")

    def simulate_key_press(self, key: int) -> None:
        """For testing: simulate a key press event."""
        if self._key_callback:
            self._key_callback(key, True)
