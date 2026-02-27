"""YAML config loader with Pydantic validation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR_NAME} with environment variable values."""
    pattern = re.compile(r"\$\{(\w+)\}")
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            raise ValueError(f"Environment variable {var_name} is not set")
        return env_val
    return pattern.sub(replacer, value)


def _resolve_env_recursive(data: Any) -> Any:
    """Walk a nested dict/list and resolve env vars in string values."""
    if isinstance(data, str):
        return _resolve_env_vars(data)
    if isinstance(data, dict):
        return {k: _resolve_env_recursive(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_resolve_env_recursive(item) for item in data]
    return data


class DeviceConfig(BaseModel):
    brightness: int = Field(default=80, ge=0, le=100)
    led_idle_color: tuple[int, int, int] = (0, 0, 0)

    @field_validator("led_idle_color", mode="before")
    @classmethod
    def parse_color(cls, v: Any) -> tuple[int, int, int]:
        if isinstance(v, (list, tuple)) and len(v) == 3:
            r, g, b = v
            if all(0 <= c <= 255 for c in (r, g, b)):
                return (r, g, b)
        raise ValueError(f"Invalid RGB color: {v}. Expected [R, G, B] with 0-255 values.")


class BabyBasicsConfig(BaseModel):
    api_url: str
    token: str
    child_id: str


class HomeAssistantConfig(BaseModel):
    url: str = "http://homeassistant.local:8123"
    token: str = ""
    enabled: bool = False


class ButtonFeedback(BaseModel):
    success_led: tuple[int, int, int] = (0, 255, 0)

    @field_validator("success_led", mode="before")
    @classmethod
    def parse_color(cls, v: Any) -> tuple[int, int, int]:
        if isinstance(v, (list, tuple)) and len(v) == 3:
            r, g, b = v
            if all(0 <= c <= 255 for c in (r, g, b)):
                return (r, g, b)
        raise ValueError(f"Invalid RGB color: {v}")


class ButtonConfig(BaseModel):
    label: str
    icon: str = ""
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    feedback: ButtonFeedback = Field(default_factory=ButtonFeedback)


class DashboardConfig(BaseModel):
    poll_interval_seconds: int = Field(default=60, ge=10, le=600)
    show_clock: bool = True


class NoteCategoryConfig(BaseModel):
    label: str
    content: str = ""
    icon: str = ""


class BrightnessScheduleConfig(BaseModel):
    enabled: bool = False
    day_brightness: int = Field(default=80, ge=0, le=100)
    night_brightness: int = Field(default=20, ge=0, le=100)
    night_start: str = "20:00"
    night_end: str = "06:00"


class DisplayConfig(BaseModel):
    auto_sleep_minutes: int = Field(default=10, ge=0, le=60)
    off_during_sleep: bool = True
    brightness_schedule: BrightnessScheduleConfig = Field(
        default_factory=BrightnessScheduleConfig
    )


class QuietHoursConfig(BaseModel):
    enabled: bool = False
    start: str = "21:00"
    end: str = "06:00"


class AnimationsConfig(BaseModel):
    enabled: bool = True
    quiet_hours: QuietHoursConfig = Field(default_factory=QuietHoursConfig)


class SettingsMenuConfig(BaseModel):
    timer_duration_seconds: int = Field(default=7, ge=0, le=30)
    skip_breast_detail: bool = False
    celebration_style: str = "color_fill"
    lock_enabled: bool = False
    lock_pin: str = ""


class MacropadConfig(BaseModel):
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    animations: AnimationsConfig = Field(default_factory=AnimationsConfig)
    settings_menu: SettingsMenuConfig = Field(default_factory=SettingsMenuConfig)
    baby_basics: BabyBasicsConfig
    home_assistant: HomeAssistantConfig = Field(default_factory=HomeAssistantConfig)
    buttons: dict[int, ButtonConfig] = Field(default_factory=dict)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    notes_categories: list[NoteCategoryConfig] = Field(default_factory=list)

    @field_validator("buttons", mode="before")
    @classmethod
    def validate_button_keys(cls, v: Any) -> dict[int, Any]:
        if not isinstance(v, dict):
            return v
        result = {}
        for key, val in v.items():
            k = int(key)
            if k < 1 or k > 15:
                raise ValueError(f"Button key {k} out of range (1-15)")
            result[k] = val
        return result


def load_config(config_path: str | Path | None = None) -> MacropadConfig:
    """Load and validate config from YAML file.

    Resolution order:
    1. Explicit path argument
    2. MACROPAD_CONFIG env var
    3. config/local.yaml (gitignored, has secrets)
    4. config/default.yaml (checked in, no secrets)
    """
    if config_path is None:
        env_path = os.environ.get("MACROPAD_CONFIG")
        if env_path:
            config_path = Path(env_path)
        else:
            project_root = Path(__file__).parent.parent.parent
            local = project_root / "config" / "local.yaml"
            default = project_root / "config" / "default.yaml"
            config_path = local if local.exists() else default

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    resolved = _resolve_env_recursive(raw)
    return MacropadConfig(**resolved)
