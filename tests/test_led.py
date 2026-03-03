"""Tests for LedController using StubDevice."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from baby_macropad.device import StubDevice
from baby_macropad.ui.led import LedController


@pytest.fixture
def device() -> StubDevice:
    return StubDevice()


@pytest.fixture
def led(device: StubDevice) -> LedController:
    return LedController(device)


def test_next_gen_increments(led: LedController) -> None:
    """Each call to _next_gen() returns a strictly increasing value."""
    g1 = led._next_gen()
    g2 = led._next_gen()
    g3 = led._next_gen()
    assert g1 < g2 < g3


def test_new_flash_cancels_previous(led: LedController) -> None:
    """Starting a second flash increments the generation, cancelling the first."""
    g1 = led._next_gen()
    assert led._is_current(g1)
    g2 = led._next_gen()
    assert not led._is_current(g1)
    assert led._is_current(g2)


def test_flash_acknowledge_calls_device(device: StubDevice) -> None:
    """flash_acknowledge() calls set_led_color and set_led_brightness."""
    mock_device = MagicMock(spec=StubDevice)
    led = LedController(mock_device)
    led.flash_acknowledge()
    time.sleep(0.3)
    mock_device.set_led_color.assert_called()
    mock_device.set_led_brightness.assert_called()


def test_flash_category_feeding(device: StubDevice) -> None:
    """flash_category('feeding') sets the feeding color (102, 204, 102)."""
    mock_device = MagicMock(spec=StubDevice)
    led = LedController(mock_device)
    led.flash_category("feeding")
    time.sleep(0.3)
    mock_device.set_led_color.assert_called_with(102, 204, 102)


def test_flash_category_diaper(device: StubDevice) -> None:
    """flash_category('diaper') sets the diaper color (204, 170, 68)."""
    mock_device = MagicMock(spec=StubDevice)
    led = LedController(mock_device)
    led.flash_category("diaper")
    time.sleep(0.3)
    mock_device.set_led_color.assert_called_with(204, 170, 68)


def test_flash_category_pump(device: StubDevice) -> None:
    """flash_category('pump') uses the note color (153, 153, 153)."""
    mock_device = MagicMock(spec=StubDevice)
    led = LedController(mock_device)
    led.flash_category("pump")
    time.sleep(0.3)
    mock_device.set_led_color.assert_called_with(153, 153, 153)


def test_flash_category_unknown_is_noop(device: StubDevice) -> None:
    """flash_category('unknown') does not call set_led_color."""
    mock_device = MagicMock(spec=StubDevice)
    led = LedController(mock_device)
    led.flash_category("unknown_category")
    time.sleep(0.1)
    mock_device.set_led_color.assert_not_called()


def test_clear_increments_generation_and_turns_off(device: StubDevice) -> None:
    """clear() increments the generation counter and calls turn_off_leds()."""
    mock_device = MagicMock(spec=StubDevice)
    led = LedController(mock_device)
    gen_before = led._generation
    led.clear()
    assert led._generation > gen_before
    mock_device.turn_off_leds.assert_called()


def test_flash_undo_uses_white(device: StubDevice) -> None:
    """flash_undo() uses white color (255, 255, 255)."""
    mock_device = MagicMock(spec=StubDevice)
    led = LedController(mock_device)
    led.flash_undo()
    time.sleep(0.5)
    mock_device.set_led_color.assert_called_with(255, 255, 255)


def test_flash_sync_success_uses_green(device: StubDevice) -> None:
    """flash_sync_success() uses green (0, 255, 0)."""
    mock_device = MagicMock(spec=StubDevice)
    led = LedController(mock_device)
    led.flash_sync_success()
    time.sleep(0.5)
    mock_device.set_led_color.assert_called_with(0, 255, 0)


def test_concurrent_flashes_do_not_crash(device: StubDevice) -> None:
    """Two rapid flash calls complete without raising exceptions."""
    led = LedController(device)
    led.flash_category("feeding")
    led.flash_category("diaper")
    time.sleep(0.2)
    # No assertion needed — just verifying no exception is raised
