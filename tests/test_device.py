"""Tests for device protocol conformance and StubDevice behavior."""

from __future__ import annotations

from baby_macropad.device import DeviceProtocol, StreamDockDevice, StubDevice


def test_stream_dock_implements_protocol() -> None:
    """StreamDockDevice satisfies DeviceProtocol at runtime."""
    assert isinstance(StreamDockDevice(), DeviceProtocol)


def test_stub_device_implements_protocol() -> None:
    """StubDevice satisfies DeviceProtocol at runtime."""
    assert isinstance(StubDevice(), DeviceProtocol)


def test_stub_simulate_key_press_triggers_callback() -> None:
    """simulate_key_press() fires the registered key callback."""
    device = StubDevice()
    received: list[tuple[int, bool]] = []

    device.set_key_callback(lambda key, pressed: received.append((key, pressed)))
    device.simulate_key_press(5)

    assert received == [(5, True)]


def test_stub_stores_brightness() -> None:
    """set_brightness() stores the value on _brightness."""
    device = StubDevice()
    device.set_brightness(50)
    assert device._brightness == 50


def test_stub_stores_led_color() -> None:
    """set_led_color() stores the color tuple on _led_color."""
    device = StubDevice()
    device.set_led_color(255, 0, 0)
    assert device._led_color == (255, 0, 0)
