"""Tests for LedController using StubDevice and MagicMock."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

from baby_macropad.device import StubDevice
from baby_macropad.ui.led import CATEGORY_COLORS, LedController, _build_rgb_data


@pytest.fixture
def device() -> StubDevice:
    return StubDevice()


@pytest.fixture
def led(device: StubDevice) -> LedController:
    return LedController(device)


@pytest.fixture
def mock_device() -> MagicMock:
    return MagicMock(spec=StubDevice)


@pytest.fixture
def mock_led(mock_device: MagicMock) -> LedController:
    return LedController(mock_device)


# --- Generation counter ---

def test_next_gen_increments(led: LedController) -> None:
    g1 = led._next_gen()
    g2 = led._next_gen()
    g3 = led._next_gen()
    assert g1 < g2 < g3


def test_new_flash_cancels_previous(led: LedController) -> None:
    g1 = led._next_gen()
    assert led._is_current(g1)
    g2 = led._next_gen()
    assert not led._is_current(g1)
    assert led._is_current(g2)


# --- set_led_colors 72-byte payload ---

def test_build_rgb_data_is_72_bytes() -> None:
    ring = [(255, 0, 0)] * 22
    strip = (0, 255, 0)
    data = _build_rgb_data(ring, strip)
    assert len(data) == 72


def test_build_rgb_data_ring_and_strips() -> None:
    ring = [(10, 20, 30)] * 22
    strip = (40, 50, 60)
    data = _build_rgb_data(ring, strip)
    # Check first ring LED
    assert data[0:3] == bytes([10, 20, 30])
    # Check last ring LED (index 21)
    assert data[63:66] == bytes([10, 20, 30])
    # Check left strip (index 22)
    assert data[66:69] == bytes([40, 50, 60])
    # Check right strip (index 23)
    assert data[69:72] == bytes([40, 50, 60])


def test_set_led_colors_called_with_72_bytes(mock_led: LedController, mock_device: MagicMock) -> None:
    """flash_acknowledge uses set_led_colors with 72-byte payload."""
    mock_led.flash_acknowledge("feeding")
    time.sleep(0.2)
    mock_device.set_led_colors.assert_called()
    payload = mock_device.set_led_colors.call_args[0][0]
    assert len(payload) == 72


# --- flash_acknowledge uses category color ---

def test_flash_acknowledge_feeding_uses_green(mock_led: LedController, mock_device: MagicMock) -> None:
    """flash_acknowledge('feeding') uses green-ish color, not white."""
    mock_led.flash_acknowledge("feeding")
    time.sleep(0.2)
    payload = mock_device.set_led_colors.call_args[0][0]
    # First LED should be the feeding color (102, 204, 102)
    r, g, b = payload[0], payload[1], payload[2]
    assert g > r, "Feeding acknowledge should be green-dominant"


def test_flash_acknowledge_diaper_uses_amber(mock_led: LedController, mock_device: MagicMock) -> None:
    """flash_acknowledge('diaper') uses amber color."""
    mock_led.flash_acknowledge("diaper")
    time.sleep(0.2)
    payload = mock_device.set_led_colors.call_args[0][0]
    r, g, b = payload[0], payload[1], payload[2]
    assert r > b, "Diaper acknowledge should be warm (red > blue)"


def test_flash_acknowledge_nav_uses_gray(mock_led: LedController, mock_device: MagicMock) -> None:
    """flash_acknowledge('nav') uses cool gray."""
    mock_led.flash_acknowledge("nav")
    time.sleep(0.2)
    payload = mock_device.set_led_colors.call_args[0][0]
    r, g, b = payload[0], payload[1], payload[2]
    # Gray means r ≈ g ≈ b (within tolerance)
    assert abs(r - g) < 30, "Nav acknowledge should be gray-ish"


# --- flash_success (cotton candy) ---

def test_flash_success_feeding(mock_led: LedController, mock_device: MagicMock) -> None:
    """flash_success('feeding') calls set_led_colors (animated)."""
    mock_led.flash_success("feeding")
    time.sleep(0.3)  # Wait for a few frames
    assert mock_device.set_led_colors.call_count >= 2, "Should have multiple animation frames"


def test_flash_success_diaper(mock_led: LedController, mock_device: MagicMock) -> None:
    """flash_success('diaper') runs animation frames."""
    mock_led.flash_success("diaper")
    time.sleep(0.3)
    assert mock_device.set_led_colors.call_count >= 2


# --- flash_error is double-pulse ---

def test_flash_error_double_pulse(mock_led: LedController, mock_device: MagicMock) -> None:
    """flash_error() produces exactly 2 pulses (on-off cycles)."""
    mock_led.flash_error()
    time.sleep(1.2)  # 2 * (0.25 on + 0.2 off) = 0.9s + margin
    # Should have called set_led_colors twice and turn_off_leds twice
    assert mock_device.set_led_colors.call_count == 2
    assert mock_device.turn_off_leds.call_count == 2


# --- Quiet hours ---

def test_quiet_hours_off_by_default(led: LedController) -> None:
    assert led.quiet_hours_setting == "off"
    assert not led._is_quiet_hours()


def test_quiet_hours_brightness_capped(mock_led: LedController, mock_device: MagicMock) -> None:
    """During quiet hours, brightness is capped at 30."""
    assert mock_led._apply_quiet_hours_brightness(80) == 30
    assert mock_led._apply_quiet_hours_brightness(20) == 20


def test_quiet_hours_rgb_dims_and_clamps_blue(mock_led: LedController) -> None:
    """Quiet hours dims to 30% and clamps blue to 40."""
    # Pure blue (0, 0, 255) → dimmed to 30% = (0, 0, 76) → blue clamped to 40
    rgb_data = bytes([0, 0, 255] * 24)
    result = mock_led._apply_quiet_hours_rgb(rgb_data)
    for i in range(0, len(result), 3):
        assert result[i + 2] <= 40, f"Blue at LED {i//3} should be capped at 40"


def test_quiet_hours_setting_property(led: LedController) -> None:
    led.quiet_hours_setting = "9pm-6am"
    assert led.quiet_hours_setting == "9pm-6am"


# --- Clear ---

def test_clear_increments_generation_and_turns_off(mock_led: LedController, mock_device: MagicMock) -> None:
    gen_before = mock_led._generation
    mock_led.clear()
    assert mock_led._generation > gen_before
    mock_device.turn_off_leds.assert_called()


# --- Flash undo ---

def test_flash_undo_runs_animation(mock_led: LedController, mock_device: MagicMock) -> None:
    """flash_undo() runs an outward sweep animation."""
    mock_led.flash_undo()
    time.sleep(0.6)
    assert mock_device.set_led_colors.call_count >= 5


# --- Flash sync ---

def test_flash_sync_success_runs_animation(mock_led: LedController, mock_device: MagicMock) -> None:
    """flash_sync_success() runs green sparkle animation."""
    mock_led.flash_sync_success()
    time.sleep(0.5)
    assert mock_device.set_led_colors.call_count >= 3


# --- Concurrent flashes ---

def test_concurrent_flashes_do_not_crash(led: LedController) -> None:
    """Two rapid flash calls complete without raising exceptions."""
    led.flash_success("feeding")
    led.flash_success("diaper")
    time.sleep(0.2)
