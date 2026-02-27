"""Tests for the declarative KeyRouter."""

from baby_macropad.ui.framework.screen import CellDef, ScreenDef
from baby_macropad.ui.framework.widgets import Spacer, Text
from baby_macropad.ui.key_router import PHYSICAL_BUTTONS, KeyRouter


def _make_screen(cells: dict[int, CellDef] | None = None) -> ScreenDef:
    return ScreenDef(name="test", cells=cells or {})


class TestKeyRouter:
    def test_physical_buttons_bypass_screen(self):
        router = KeyRouter()
        router.set_screen(_make_screen())
        for key, action in PHYSICAL_BUTTONS.items():
            assert router.route(key) == action

    def test_screen_cell_on_press(self):
        screen = _make_screen({
            1: CellDef(widget=Text(text="BACK"), key_num=1, on_press="back"),
            13: CellDef(widget=Text(text="WAKE"), key_num=13, on_press="wake_up"),
        })
        router = KeyRouter()
        router.set_screen(screen)
        assert router.route(1) == "back"
        assert router.route(13) == "wake_up"

    def test_unknown_key_returns_none(self):
        router = KeyRouter()
        router.set_screen(_make_screen())
        assert router.route(99) is None

    def test_cell_without_on_press_returns_none(self):
        screen = _make_screen({
            5: CellDef(widget=Spacer(), key_num=5, on_press=None),
        })
        router = KeyRouter()
        router.set_screen(screen)
        assert router.route(5) is None

    def test_no_screen_set_returns_none(self):
        router = KeyRouter()
        assert router.route(1) is None

    def test_physical_button_overrides_screen(self):
        """Physical buttons should always win, even if a screen cell maps the same key."""
        screen = _make_screen({
            16: CellDef(widget=Text(text="X"), key_num=16, on_press="screen_action"),
        })
        router = KeyRouter()
        router.set_screen(screen)
        # Physical button map says key 16 = "back"
        assert router.route(16) == "back"

    def test_set_screen_replaces_previous(self):
        router = KeyRouter()
        screen1 = _make_screen({
            1: CellDef(widget=Text(text="A"), key_num=1, on_press="action_a"),
        })
        screen2 = _make_screen({
            1: CellDef(widget=Text(text="B"), key_num=1, on_press="action_b"),
        })
        router.set_screen(screen1)
        assert router.route(1) == "action_a"
        router.set_screen(screen2)
        assert router.route(1) == "action_b"
