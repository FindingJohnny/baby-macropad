"""Declarative key-to-action routing based on the active ScreenDef.

Routes physical key presses to action strings. Physical side buttons
bypass the ScreenDef and map directly to global actions.
"""

from __future__ import annotations

from .framework.screen import ScreenDef

# Physical side buttons (TBD — placeholder key numbers, verify on hardware)
PHYSICAL_BUTTONS: dict[int, str] = {
    16: "back",
    17: "home",
    18: "settings",
}


class KeyRouter:
    """Routes key presses to action strings based on the active ScreenDef."""

    def __init__(self) -> None:
        self._active_screen: ScreenDef | None = None

    def set_screen(self, screen_def: ScreenDef) -> None:
        self._active_screen = screen_def

    def route(self, key_num: int) -> str | None:
        """Resolve a key press to an action string.

        1. Check physical button map (side buttons bypass ScreenDef).
        2. Look up CellDef in active screen.
        3. Return on_press if set, else None.
        """
        # Physical side buttons
        if key_num in PHYSICAL_BUTTONS:
            return PHYSICAL_BUTTONS[key_num]

        # Screen cell lookup
        if self._active_screen is None:
            return None

        cell = self._active_screen.cells.get(key_num)
        if cell is None:
            return None

        return cell.on_press
