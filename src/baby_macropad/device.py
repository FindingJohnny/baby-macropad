"""Stream Dock M18 device wrapper.

Abstracts the StreamDock SDK so the rest of the app doesn't depend on it.
Falls back to a stub when the SDK is not installed (development/testing).

Hardware notes (VSD Inside / HOTSPOTEKUSB Stream Dock M18):
- USB VID=0x5548, PID=0x1000 (NOT 0x6603 as some docs claim)
- Two HID interfaces: interface 0 = device control, interface 1 = keyboard
- Only use interface 0 (first enumerated path)
- SDK's DeviceManager creates duplicate entries — bypass it
- SDK's open() starts a reader thread automatically — don't call whileread()
- Native transport lib segfaults on close() — skip native cleanup
- ARM64 lib selection bug in SDK: copies libtransport_arm64.so over libtransport.so
"""

from __future__ import annotations

import ctypes
import io
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

KeyCallback = Callable[[int, bool], None]  # (key_number, is_pressed)

# HOTSPOTEKUSB Stream Dock M18
DEFAULT_VID = 0x5548
DEFAULT_PID = 0x1000


class DeviceError(Exception):
    pass


class StreamDockDevice:
    """Wrapper around the StreamDock SDK device.

    Bypasses DeviceManager to avoid dual-interface enumeration bugs.
    Uses direct transport + StreamDock293 for reliable operation.
    """

    def __init__(self, vid: int = DEFAULT_VID, pid: int = DEFAULT_PID) -> None:
        self._vid = vid
        self._pid = pid
        self._device: Any = None
        self._transport: Any = None
        self._key_callback: KeyCallback | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def open(self) -> bool:
        """Discover and open the first StreamDock device.

        Uses direct transport enumeration (not DeviceManager) to avoid
        the dual-interface bug where both HID interfaces create separate
        device objects sharing one transport.

        Returns True if a device was found and opened.
        """
        try:
            from StreamDock.Devices.StreamDock293 import StreamDock293
            from StreamDock.Transport.LibUSBHIDAPI import LibUSBHIDAPI
        except ImportError:
            logger.warning("StreamDock SDK not installed — running in stub mode")
            return False

        try:
            transport = LibUSBHIDAPI()
            found = transport.enumerate(self._vid, self._pid)
            if not found:
                logger.warning(
                    "No StreamDock devices found (VID=%04x PID=%04x)",
                    self._vid, self._pid,
                )
                return False

            # Use only the first interface (interface 0 = device control)
            logger.info(
                "Found %d HID interface(s), using %s",
                len(found), found[0]["path"],
            )
            self._transport = transport
            self._device = StreamDock293(transport, found[0])
            self._device.open()

            # Cancel the SDK's auto screen-off timer (we manage this ourselves)
            if hasattr(self._device, "screenlicent"):
                self._device.screenlicent.cancel()

            # Wake screen and refresh display
            self._device.wakeScreen()
            self._device.screen_On()
            self._device.refresh()

            self._connected = True
            logger.info("StreamDock device opened on %s", found[0]["path"])
            return True
        except Exception:
            logger.exception("Failed to open StreamDock device")
            return False

    def close(self) -> None:
        """Close the device connection.

        Skips native transport close() to avoid segfault in the ARM64
        transport library. For a systemd service this is fine — the
        process exits and the OS cleans up the USB handle.
        """
        if self._device:
            try:
                self._device.clearAllIcon()
            except Exception:
                pass
            # Cancel any timers
            if hasattr(self._device, "screenlicent"):
                try:
                    self._device.screenlicent.cancel()
                except Exception:
                    pass
            # Stop reader thread
            if hasattr(self._device, "run_read_thread"):
                self._device.run_read_thread = False
            # Do NOT call self._device.close() — native lib segfaults
            self._device = None
            self._transport = None
            self._connected = False
            logger.info("StreamDock device released (skipped native close)")

    def set_brightness(self, level: int) -> None:
        if self._device:
            self._device.set_brightness(level)

    def set_key_image(self, key: int, image_path: str | Path) -> None:
        """Set the icon on a specific key (1-15).

        Loads the image, converts to 100x100 JPEG with 180° rotation
        (required by the M18 hardware), and sends raw bytes via
        set_key_imagedata for maximum compatibility.
        """
        if not self._device:
            return
        try:
            img = Image.open(str(image_path)).convert("RGB").resize((100, 100))
            img = img.rotate(180)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            jpeg_bytes = buf.getvalue()
            arr_type = ctypes.c_char * len(jpeg_bytes)
            arr = arr_type(*jpeg_bytes)
            result = self._device.set_key_imagedata(key, arr, 100, 100)
            logger.info("Set key %d image (%d bytes) result=%s", key, len(jpeg_bytes), result)
        except Exception:
            logger.exception("Failed to set key %d image from %s", key, image_path)

    def set_key_image_bytes(self, key: int, jpeg_data: bytes) -> None:
        """Set the icon on a specific key from raw JPEG bytes."""
        if not self._device:
            return
        arr_type = ctypes.c_char * len(jpeg_data)
        arr = arr_type(*jpeg_data)
        self._device.set_key_imagedata(key, arr, 100, 100)

    def set_touchscreen_image(self, image_path: str | Path) -> None:
        """Set the full touchscreen background image."""
        if self._device:
            try:
                self._device.set_touchscreen_image(str(image_path))
            except Exception:
                logger.exception("Failed to set touchscreen image")

    def set_led_color(self, r: int, g: int, b: int) -> None:
        """Set the LED ring color (not supported on all models)."""
        if self._device:
            try:
                self._device.set_led_color(r, g, b)
            except (AttributeError, Exception):
                pass

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
        """Register the key callback with the SDK.

        The SDK's open() already starts a reader thread via _setup_reader().
        We do NOT start another whileread() thread — that would conflict.
        Just register our callback and let the existing thread dispatch events.
        """
        if not self._device:
            return

        def _key_handler(device: Any, key: int, state: int) -> None:
            is_pressed = state == 1
            if self._key_callback:
                try:
                    self._key_callback(key, is_pressed)
                except Exception:
                    logger.exception("Error in key callback for key %d", key)

        self._device.set_key_callback(_key_handler)
        logger.info("Key event listener registered")


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
