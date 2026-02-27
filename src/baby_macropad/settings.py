"""Pydantic settings model with YAML persistence.

Provides typed, validated settings with cycle-through support for
macropad button-driven configuration changes.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_SETTINGS_DIR = Path.home() / ".baby-macropad"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.yaml"


class SettingsModel(BaseModel):
    timer_duration_seconds: int = Field(
        default=7,
        json_schema_extra={
            "display_label": "Timer",
            "cycle_values": [5, 7, 10, 15],
            "format": "{value}s",
        },
    )
    skip_breast_detail: bool = Field(
        default=False,
        json_schema_extra={"display_label": "Quick Log"},
    )
    celebration_style: str = Field(
        default="color_fill",
        json_schema_extra={
            "display_label": "Celebrate",
            "cycle_values": ["color_fill", "none"],
        },
    )
    brightness: int = Field(
        default=80,
        json_schema_extra={
            "display_label": "Bright",
            "cycle_values": [20, 40, 60, 80, 100],
        },
    )
    tutorial_completed: bool = Field(
        default=False,
        json_schema_extra={"hidden": True},
    )

    def cycle_field(self, field_name: str) -> None:
        """Advance a field to its next cycle value and auto-save."""
        field_info = type(self).model_fields[field_name]
        extra = field_info.json_schema_extra or {}
        cycle_values = extra.get("cycle_values")
        if not cycle_values:
            # Boolean toggle
            current = getattr(self, field_name)
            setattr(self, field_name, not current)
        else:
            current = getattr(self, field_name)
            try:
                idx = cycle_values.index(current)
                new_val = cycle_values[(idx + 1) % len(cycle_values)]
            except ValueError:
                new_val = cycle_values[0]
            setattr(self, field_name, new_val)
        self.save()

    def save(self) -> None:
        """Persist settings to YAML."""
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(_SETTINGS_FILE, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)

    @classmethod
    def load(cls) -> SettingsModel:
        """Load settings from YAML, or return defaults."""
        if _SETTINGS_FILE.exists():
            with open(_SETTINGS_FILE) as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()
