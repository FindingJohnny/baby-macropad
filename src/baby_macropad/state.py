"""Display state model for the macropad controller.

Tracks which screen mode is active and all transient state needed
to render the current display and handle key presses correctly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ScreenMode = Literal[
    "home_grid",
    "detail",
    "confirmation",
    "sleep_mode",
    "notes_submenu",
    "settings",
]


@dataclass
class DisplayState:
    mode: ScreenMode = "home_grid"

    # Detail screen
    detail_action: str | None = None  # e.g. "breast_left", "bottle", "poop", "both"
    detail_context: dict = field(default_factory=dict)  # accumulated API params
    detail_options: list[dict] = field(default_factory=list)  # option definitions
    detail_default_index: int = 0
    detail_timer_expires: float = 0.0  # time.monotonic() deadline

    # Confirmation screen
    confirmation_action: str | None = None  # e.g. "log_feeding", "log_diaper"
    confirmation_label: str = ""  # e.g. "Left breast logged"
    confirmation_context: str = ""  # e.g. "Next: Right breast"
    confirmation_icon: str = ""  # asset name for the icon
    confirmation_category_color: tuple[int, int, int] = (255, 255, 255)
    confirmation_column: int = 0  # column that was pressed (for color fill)
    confirmation_expires: float = 0.0  # time.monotonic() deadline
    confirmation_resource_id: str | None = None  # returned ID for UNDO
    confirmation_resource_type: str | None = None  # "feedings", "diapers", "sleeps", "notes"

    # Sleep mode
    sleep_active: bool = False
    sleep_start_time: str | None = None  # ISO timestamp from API
    sleep_id: str | None = None  # Active sleep resource ID

    # Live data (from dashboard API)
    dashboard: object | None = None
    connected: bool = True
    queued_count: int = 0

    # Runtime settings (can be changed via settings menu, persisted separately)
    timer_seconds: int = 7
    skip_breast_detail: bool = False
    celebration_style: str = "color_fill"

    # Recent actions for undo in settings (last 5)
    recent_actions: list[dict] = field(default_factory=list)

    def enter_detail(
        self,
        action: str,
        options: list[dict],
        default_index: int,
        context: dict,
        timer_expires: float,
    ) -> None:
        """Transition to detail screen mode."""
        self.mode = "detail"
        self.detail_action = action
        self.detail_options = options
        self.detail_default_index = default_index
        self.detail_context = context
        self.detail_timer_expires = timer_expires

    def enter_confirmation(
        self,
        action: str,
        label: str,
        context: str,
        icon: str,
        category_color: tuple[int, int, int],
        column: int,
        expires: float,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> None:
        """Transition to confirmation screen mode."""
        self.mode = "confirmation"
        self.confirmation_action = action
        self.confirmation_label = label
        self.confirmation_context = context
        self.confirmation_icon = icon
        self.confirmation_category_color = category_color
        self.confirmation_column = column
        self.confirmation_expires = expires
        self.confirmation_resource_id = resource_id
        self.confirmation_resource_type = resource_type

    def enter_sleep_mode(self, sleep_id: str, start_time: str) -> None:
        """Transition to sleep mode."""
        self.mode = "sleep_mode"
        self.sleep_active = True
        self.sleep_id = sleep_id
        self.sleep_start_time = start_time

    def exit_sleep_mode(self) -> None:
        """Clear sleep state (caller transitions to confirmation or home)."""
        self.sleep_active = False
        self.sleep_id = None
        self.sleep_start_time = None

    def return_home(self) -> None:
        """Return to home grid, clearing transient screen state."""
        self.mode = "home_grid"
        self.detail_action = None
        self.detail_options = []
        self.detail_context = {}
        self.detail_timer_expires = 0.0
        self.confirmation_action = None
        self.confirmation_expires = 0.0
        self.confirmation_resource_id = None
        self.confirmation_resource_type = None

    def push_recent_action(self, action: dict) -> None:
        """Track a recent action for undo in settings (max 5)."""
        self.recent_actions.insert(0, action)
        if len(self.recent_actions) > 5:
            self.recent_actions.pop()
