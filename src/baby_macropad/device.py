"""Stream Dock M18 device wrapper.

Abstracts the StreamDock SDK so the rest of the app doesn't depend on it.
Falls back to a stub when the SDK is not installed (development/testing).

Hardware notes (VSD Inside / HOTSPOTEKUSB Stream Dock M18):
- USB VID=0x5548, PID=0x1000 (HOTSPOTEKUSB variant)
- 15 screen keys are one 480x272 LCD panel (5 cols x 3 rows)
- Individual set_key_image_stream doesn't work on this variant
- Must compose all keys into one 480x272 image and send via
  set_background_image_stream (the only working image method)
- 3 additional physical (non-display) buttons in row 4
- M18 report sizes: input=513, output=1025, feature=0
- ARM64 lib selection bug in SDK: copy libtransport_arm64.so over libtransport.so
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Callable

from PIL import Image

logger = logging.getLogger(__name__)

KeyCallback = Callable[[int, bool], None]  # (key_number, is_pressed)

# HOTSPOTEKUSB Stream Dock M18
DEFAULT_VID = 0x5548
DEFAULT_PID = 0x1000


class DeviceError(Exception):
    pass


class StreamDockDevice:
    """Wrapper around the StreamDock SDK device.

    Uses StreamDockM18 class with direct transport enumeration.
    All display updates go through set_screen_image() which sends
    a full 480x272 composite to the LCD panel.
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
        """Discover and open the first StreamDock M18 device.

        Returns True if a device was found and opened.
        """
        try:
            from StreamDock.Devices.StreamDockM18 import StreamDockM18
            from StreamDock.Transport.LibUSBHIDAPI import LibUSBHIDAPI
        except ImportError:
            logger.warning("StreamDock SDK not installed — running in stub mode")
            return False

        try:
            transport = LibUSBHIDAPI()
            found = transport.enumerate_devices(self._vid, self._pid)
            if not found:
                logger.warning(
                    "No StreamDock devices found (VID=%04x PID=%04x)",
                    self._vid, self._pid,
                )
                return False

            logger.info(
                "Found %d HID interface(s), using %s",
                len(found), found[0]["path"],
            )
            self._transport = transport
            self._device = StreamDockM18(transport, found[0])
            self._device.open()
            self._device.init()

            self._connected = True
            logger.info("StreamDock M18 opened on %s", found[0]["path"])
            return True
        except Exception:
            logger.exception("Failed to open StreamDock device")
            return False

    def close(self) -> None:
        """Close the device connection."""
        if self._device:
            try:
                self._device.clearAllIcon()
            except Exception:
                pass
            try:
                self._device.close()
            except Exception:
                logger.debug("Native close() failed (expected on ARM64), ignoring")
            self._device = None
            self._transport = None
            self._connected = False
            logger.info("StreamDock device released")

    def enable_button_events(self) -> None:
        """Switch to mode 1 to enable HID button event reporting.

        MUST be called AFTER set_screen_image(). Calling it before
        other transport commands (brightness, background image) can
        cause it to be silently reset by the firmware.
        """
        if self._transport:
            self._transport.change_mode(1)
            logger.info("Switched to mode 1 (button events enabled)")

    def turn_off_leds(self) -> None:
        """Turn off the LED ring completely."""
        if self._device:
            try:
                self._device.set_led_color(0, 0, 0)
                self._device.set_led_brightness(0)
                logger.info("LED ring turned off")
            except Exception:
                pass

    def set_brightness(self, level: int) -> None:
        if self._device:
            self._device.set_brightness(level)

    def set_screen_image(self, jpeg_data: bytes) -> None:
        """Send a full 480x272 JPEG image to the LCD panel.

        This is the only working image method on the HOTSPOTEKUSB M18
        variant. The entire 15-key grid is one LCD, so we send one
        composite image containing all key icons.
        """
        if not self._transport:
            return
        try:
            self._transport.set_background_image_stream(jpeg_data)
            logger.debug("Screen image sent (%d bytes)", len(jpeg_data))
        except Exception:
            logger.exception("Failed to send screen image")

    def set_screen_image_file(self, image_path: str | Path) -> None:
        """Send a 480x272 JPEG file to the LCD panel."""
        if not self._transport:
            return
        try:
            with open(str(image_path), "rb") as f:
                jpeg_data = f.read()
            self.set_screen_image(jpeg_data)
        except Exception:
            logger.exception("Failed to send screen image from %s", image_path)

    def set_led_color(self, r: int, g: int, b: int) -> None:
        """Set the LED ring color (M18 has 24 RGB LEDs)."""
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

        The SDK uses InputEvent-based callbacks. We bridge to our
        simpler (key_number, is_pressed) callback format.
        """
        if not self._device:
            return

        def _key_handler(device: Any, event: Any) -> None:
            """Bridge SDK InputEvent to our KeyCallback format."""
            try:
                from StreamDock.InputTypes import EventType
                if event.event_type == EventType.BUTTON:
                    key_num = int(event.key)  # ButtonKey IntEnum -> int
                    is_pressed = event.state == 1
                    if self._key_callback:
                        self._key_callback(key_num, is_pressed)
            except Exception:
                logger.exception("Error in key event handler")

        self._device.set_key_callback(_key_handler)
        logger.info("Key event listener registered (M18 InputEvent mode)")


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

    def set_screen_image(self, jpeg_data: bytes) -> None:
        logger.debug("Stub: screen image set (%d bytes)", len(jpeg_data))

    def set_screen_image_file(self, image_path: str | Path) -> None:
        logger.debug("Stub: screen image from %s", image_path)

    def set_led_color(self, r: int, g: int, b: int) -> None:
        self._led_color = (r, g, b)
        logger.debug("Stub: LED color set to (%d, %d, %d)", r, g, b)

    def set_led_brightness(self, level: int) -> None:
        logger.debug("Stub: LED brightness set to %d", level)

    def set_key_callback(self, callback: KeyCallback) -> None:
        self._key_callback = callback

    def enable_button_events(self) -> None:
        logger.debug("Stub: button events enabled (no-op)")

    def turn_off_leds(self) -> None:
        logger.debug("Stub: LEDs turned off (no-op)")

    def start_listening(self) -> None:
        logger.info("Stub: key listener started (no-op)")

    def simulate_key_press(self, key: int) -> None:
        """For testing: simulate a key press event."""
        if self._key_callback:
            self._key_callback(key, True)
