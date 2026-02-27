"""Tests for YAML config loading and Pydantic validation."""

import os
import textwrap
from pathlib import Path

import pytest

from baby_macropad.config import MacropadConfig, load_config


@pytest.fixture
def minimal_yaml(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(textwrap.dedent("""\
        baby_basics:
          api_url: "https://example.com/api/v1"
          token: "bb_test_token"
          child_id: "abc-123"
    """))
    return config


@pytest.fixture
def full_yaml(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(textwrap.dedent("""\
        device:
          brightness: 60
          led_idle_color: [10, 20, 30]

        baby_basics:
          api_url: "https://example.com/api/v1"
          token: "bb_test_token"
          child_id: "abc-123"

        home_assistant:
          url: "http://ha.local:8123"
          token: "ha_token"
          enabled: true

        buttons:
          1:
            label: "Breast L"
            icon: "breast_left"
            action: "baby_basics.log_feeding"
            params:
              type: "breast"
              started_side: "left"
            feedback:
              success_led: [0, 255, 0]
          9:
            label: "Sleep"
            icon: "sleep"
            action: "baby_basics.toggle_sleep"

        dashboard:
          poll_interval_seconds: 30
          show_clock: false
    """))
    return config


def test_load_minimal_config(minimal_yaml: Path):
    cfg = load_config(minimal_yaml)
    assert cfg.baby_basics.api_url == "https://example.com/api/v1"
    assert cfg.baby_basics.token == "bb_test_token"
    assert cfg.baby_basics.child_id == "abc-123"
    assert cfg.device.brightness == 80  # default
    assert cfg.device.led_idle_color == (0, 0, 0)  # default (off — nursery dark)
    assert cfg.home_assistant.enabled is False
    assert cfg.buttons == {}
    assert cfg.dashboard.poll_interval_seconds == 60


def test_load_full_config(full_yaml: Path):
    cfg = load_config(full_yaml)
    assert cfg.device.brightness == 60
    assert cfg.device.led_idle_color == (10, 20, 30)
    assert cfg.home_assistant.enabled is True
    assert cfg.home_assistant.token == "ha_token"
    assert 1 in cfg.buttons
    assert cfg.buttons[1].label == "Breast L"
    assert cfg.buttons[1].action == "baby_basics.log_feeding"
    assert cfg.buttons[1].params == {"type": "breast", "started_side": "left"}
    assert cfg.buttons[1].feedback.success_led == (0, 255, 0)
    assert 9 in cfg.buttons
    assert cfg.buttons[9].label == "Sleep"
    assert cfg.dashboard.poll_interval_seconds == 30
    assert cfg.dashboard.show_clock is False


def test_env_var_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BB_API_TOKEN", "bb_from_env")
    config = tmp_path / "config.yaml"
    config.write_text(textwrap.dedent("""\
        baby_basics:
          api_url: "https://example.com/api/v1"
          token: "${BB_API_TOKEN}"
          child_id: "abc-123"
    """))
    cfg = load_config(config)
    assert cfg.baby_basics.token == "bb_from_env"


def test_missing_env_var_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
    config = tmp_path / "config.yaml"
    config.write_text(textwrap.dedent("""\
        baby_basics:
          api_url: "https://example.com/api/v1"
          token: "${NONEXISTENT_VAR}"
          child_id: "abc-123"
    """))
    with pytest.raises(ValueError, match="NONEXISTENT_VAR is not set"):
        load_config(config)


def test_invalid_button_key_raises(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(textwrap.dedent("""\
        baby_basics:
          api_url: "https://example.com/api/v1"
          token: "bb_test"
          child_id: "abc-123"
        buttons:
          16:
            label: "Invalid"
            action: "test"
    """))
    with pytest.raises(Exception):
        load_config(config)


def test_invalid_brightness_raises(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(textwrap.dedent("""\
        device:
          brightness: 150
        baby_basics:
          api_url: "https://example.com/api/v1"
          token: "bb_test"
          child_id: "abc-123"
    """))
    with pytest.raises(Exception):
        load_config(config)


def test_invalid_led_color_raises(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(textwrap.dedent("""\
        device:
          led_idle_color: [300, 0, 0]
        baby_basics:
          api_url: "https://example.com/api/v1"
          token: "bb_test"
          child_id: "abc-123"
    """))
    with pytest.raises(Exception):
        load_config(config)


def test_missing_config_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/config.yaml")


def test_config_path_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path / "env_config.yaml"
    config.write_text(textwrap.dedent("""\
        baby_basics:
          api_url: "https://example.com/api/v1"
          token: "bb_env_config"
          child_id: "abc-123"
    """))
    monkeypatch.setenv("MACROPAD_CONFIG", str(config))
    cfg = load_config()
    assert cfg.baby_basics.token == "bb_env_config"
