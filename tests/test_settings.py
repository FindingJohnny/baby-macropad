"""Tests for the Pydantic settings model."""

from pathlib import Path
from unittest.mock import patch

from baby_macropad.settings import SettingsModel


class TestSettingsDefaults:
    def test_default_values(self):
        s = SettingsModel()
        assert s.timer_duration_seconds == 7
        assert s.skip_breast_detail is False
        assert s.celebration_style == "color_fill"
        assert s.brightness == 80
        assert s.tutorial_completed is False


class TestCycleField:
    """Test cycle_field by pointing save() at a temp dir so it doesn't write to $HOME."""

    def test_cycle_timer_advances(self, tmp_path: Path):
        with (
            patch("baby_macropad.settings._SETTINGS_FILE", tmp_path / "s.yaml"),
            patch("baby_macropad.settings._SETTINGS_DIR", tmp_path),
        ):
            s = SettingsModel()
            assert s.timer_duration_seconds == 7
            s.cycle_field("timer_duration_seconds")
            assert s.timer_duration_seconds == 10

    def test_cycle_timer_wraps_around(self, tmp_path: Path):
        with (
            patch("baby_macropad.settings._SETTINGS_FILE", tmp_path / "s.yaml"),
            patch("baby_macropad.settings._SETTINGS_DIR", tmp_path),
        ):
            s = SettingsModel(timer_duration_seconds=15)
            s.cycle_field("timer_duration_seconds")
            assert s.timer_duration_seconds == 5

    def test_cycle_boolean_toggles(self, tmp_path: Path):
        with (
            patch("baby_macropad.settings._SETTINGS_FILE", tmp_path / "s.yaml"),
            patch("baby_macropad.settings._SETTINGS_DIR", tmp_path),
        ):
            s = SettingsModel(skip_breast_detail=False)
            s.cycle_field("skip_breast_detail")
            assert s.skip_breast_detail is True
            s.cycle_field("skip_breast_detail")
            assert s.skip_breast_detail is False

    def test_cycle_celebration_style(self, tmp_path: Path):
        with (
            patch("baby_macropad.settings._SETTINGS_FILE", tmp_path / "s.yaml"),
            patch("baby_macropad.settings._SETTINGS_DIR", tmp_path),
        ):
            s = SettingsModel(celebration_style="color_fill")
            s.cycle_field("celebration_style")
            assert s.celebration_style == "none"
            s.cycle_field("celebration_style")
            assert s.celebration_style == "color_fill"

    def test_cycle_brightness(self, tmp_path: Path):
        with (
            patch("baby_macropad.settings._SETTINGS_FILE", tmp_path / "s.yaml"),
            patch("baby_macropad.settings._SETTINGS_DIR", tmp_path),
        ):
            s = SettingsModel(brightness=80)
            s.cycle_field("brightness")
            assert s.brightness == 100
            s.cycle_field("brightness")
            assert s.brightness == 20

    def test_cycle_unknown_value_resets_to_first(self, tmp_path: Path):
        """If the current value isn't in cycle_values, reset to first."""
        with (
            patch("baby_macropad.settings._SETTINGS_FILE", tmp_path / "s.yaml"),
            patch("baby_macropad.settings._SETTINGS_DIR", tmp_path),
        ):
            s = SettingsModel(timer_duration_seconds=99)
            s.cycle_field("timer_duration_seconds")
            assert s.timer_duration_seconds == 5


class TestSaveLoad:
    def test_roundtrip(self, tmp_path: Path):
        settings_file = tmp_path / "settings.yaml"
        settings_dir = tmp_path

        with (
            patch("baby_macropad.settings._SETTINGS_FILE", settings_file),
            patch("baby_macropad.settings._SETTINGS_DIR", settings_dir),
        ):
            s = SettingsModel(timer_duration_seconds=10, brightness=40)
            s.save()

            assert settings_file.exists()

            loaded = SettingsModel.load()
            assert loaded.timer_duration_seconds == 10
            assert loaded.brightness == 40
            assert loaded.skip_breast_detail is False  # default preserved

    def test_load_returns_defaults_when_no_file(self, tmp_path: Path):
        missing_file = tmp_path / "nonexistent" / "settings.yaml"
        with patch("baby_macropad.settings._SETTINGS_FILE", missing_file):
            loaded = SettingsModel.load()
            assert loaded.timer_duration_seconds == 7
            assert loaded.brightness == 80

    def test_load_handles_empty_file(self, tmp_path: Path):
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text("")

        with (
            patch("baby_macropad.settings._SETTINGS_FILE", settings_file),
            patch("baby_macropad.settings._SETTINGS_DIR", tmp_path),
        ):
            loaded = SettingsModel.load()
            assert loaded.timer_duration_seconds == 7
