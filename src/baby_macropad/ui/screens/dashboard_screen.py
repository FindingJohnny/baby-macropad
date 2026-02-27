"""Dashboard screen factory — wraps the existing dashboard renderer."""

from __future__ import annotations

from typing import Any

from ..dashboard import render_dashboard
from ..framework.screen import CellDef, ScreenDef


def build_dashboard_screen(
    dashboard_data: dict[str, Any] | None = None,
    connected: bool = True,
    queued_count: int = 0,
) -> ScreenDef:
    """Build the touchscreen dashboard panel.

    The dashboard is entirely pre_render content — the full render_dashboard()
    output is drawn onto the image. No grid cells are used for interaction.
    """

    def _pre_render(img, draw):
        # Render the existing dashboard into a separate image and paste it
        dashboard_img = render_dashboard(dashboard_data, connected, queued_count)
        img.paste(dashboard_img, (0, 0))

    return ScreenDef(name="dashboard", cells={}, pre_render=_pre_render)
