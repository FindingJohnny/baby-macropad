# Macropad UI Framework

Version: 0.1.0
Last Reviewed: 2026-02-27
Status: Draft

---

## 1. Overview

### Problem Statement

The current `main.py` is a 1231-line God Object that manages device I/O, threading, API
calls, screen rendering dispatch, LED control, and settings — all in one class. This causes:

1. **4x duplicated drawing primitives**: `_get_font()`, `_draw_centered_text()`, and
   `_darken()` are copy-pasted into `detail.py`, `notes.py`, `settings.py`, and
   `confirmation.py`. Changes must be made 4 times or diverge silently.

2. **Zero text overflow handling**: All renderers assume text fits in its allocated cell.
   Long labels (e.g., "LEFT BREAST", "WAKE UP", note category names from YAML config) can
   overflow cell boundaries with no truncation or size-fallback logic.

3. **No reusable screen or widget abstractions**: Every screen is a hand-rolled pixel
   routine. Adding a new screen or changing a design token requires editing multiple files
   with no shared contract.

4. **Race conditions causing button misfires**: The tick thread and key handler run
   concurrently and read/write `DisplayState.mode` without a lock. A `time.monotonic()`
   check in the tick thread can change mode while the key handler is mid-execution,
   causing actions to route to the wrong screen handler.

5. **Settings state scattered**: Runtime settings (`timer_seconds`, `skip_breast_detail`,
   `celebration_style`) live on `DisplayState` as flat fields with no persistence contract,
   no cycle-values metadata, and no separation from transient display state.

### Goals

1. **Declarative screens**: Screen content is described as a data structure (`ScreenDef`)
   and rendered by a generic `ScreenRenderer`. Screen factories return `ScreenDef`s, not
   `bytes`. Rendering is always deterministic from data.

2. **Smart text handling**: A single `fit_text()` function tries progressively smaller font
   sizes and truncates to ellipsis as a last resort. Every text draw call goes through this
   path.

3. **Consistent interactions**: A `CellDef` carries both the visual widget and the
   `on_press` action string. Key routing is a data lookup, not a switch statement. The same
   pattern applies to every screen.

4. **Thread safety**: A `StateMachine` wraps `DisplayState` with `threading.RLock`.
   `try_handle_key(key)` acquires the lock before reading mode and state. The tick thread
   calls `advance_tick()` which also acquires the lock. The tick and key handler can never
   interleave.

5. **Incremental migration**: Each phase produces a working, testable system. The old
   renderers coexist behind a config flag until Phase 5. No "big bang" switchover.

---

## 2. Architecture

### Layer Cake

```
┌─────────────────────────────────────────────────────────┐
│  Screen Factories  (ui/screens/*.py)                    │
│  build_home_grid, build_detail_screen, build_sleep, ... │
│  Return: ScreenDef                                      │
├─────────────────────────────────────────────────────────┤
│  Widget System  (ui/framework/widgets.py)               │
│  Card, Text, TwoLineText, Icon, IconLabel, Spacer       │
│  Protocol: render(img, draw, rect: Rect) → None         │
├─────────────────────────────────────────────────────────┤
│  Framework  (ui/framework/)                             │
│  primitives.py  text_engine.py  icon_cache.py           │
│  screen.py  (CellDef, ScreenDef, ScreenRenderer)        │
├─────────────────────────────────────────────────────────┤
│  State Machine  (ui/state_machine.py)                   │
│  StateMachine wrapping DisplayState with RLock          │
│  try_handle_key() → atomic snapshot                     │
├─────────────────────────────────────────────────────────┤
│  Key Router  (ui/key_router.py)                         │
│  Routes key number → CellDef.on_press action string     │
│  Registered action handlers called by Controller        │
├─────────────────────────────────────────────────────────┤
│  Controller  (main.py)                                  │
│  Device I/O, threads, action dispatch, API calls        │
│  Target: < 250 lines after Phase 4                      │
├─────────────────────────────────────────────────────────┤
│  Device  (device.py)                                    │
│  StreamDockDevice / StubDevice — unchanged              │
└─────────────────────────────────────────────────────────┘
```

### File Structure

```
src/baby_macropad/
├── main.py                         # Controller (< 250 lines after Phase 4)
├── state.py                        # DisplayState dataclass — unchanged in Phase 1-2
├── config.py                       # MacropadConfig — unchanged
├── device.py                       # StreamDockDevice — unchanged
├── settings.py                     # NEW: SettingsModel with cycle_field() + persistence
│
├── ui/
│   ├── __init__.py
│   │
│   ├── framework/
│   │   ├── __init__.py
│   │   ├── primitives.py           # Rect, grid constants, darken, BG_COLOR, etc.
│   │   ├── text_engine.py          # get_font, fit_text, draw_centered_text
│   │   ├── icon_cache.py           # load_and_tint, load_composite (LRU cached)
│   │   ├── widgets.py              # Widget protocol + Card, Text, Icon, etc.
│   │   └── screen.py               # CellDef, ScreenDef, ScreenRenderer
│   │
│   ├── screens/
│   │   ├── __init__.py
│   │   ├── home.py                 # build_home_grid()
│   │   ├── detail.py               # build_detail_screen()
│   │   ├── confirmation.py         # build_confirmation_screen()
│   │   ├── selection.py            # build_selection_screen() (notes, submenu)
│   │   ├── settings_screen.py      # build_settings_screen()
│   │   ├── sleep_screen.py         # build_sleep_screen()
│   │   ├── dashboard_screen.py     # build_dashboard_screen()
│   │   └── tutorial.py             # build_tutorial_screen() (Phase 6)
│   │
│   ├── state_machine.py            # NEW: StateMachine + RLock
│   ├── key_router.py               # NEW: KeyRouter
│   ├── led.py                      # NEW: LedController (extracted from main.py)
│   │
│   │   # Legacy renderers (kept until Phase 5 cleanup)
│   ├── icons.py
│   ├── detail.py
│   ├── confirmation.py
│   ├── sleep.py
│   ├── notes.py
│   ├── settings.py
│   └── dashboard.py
```

---

## 3. Primitives (`ui/framework/primitives.py`)

Extracted from `ui/icons.py`. Zero behavior changes — just centralized.

### `Rect` dataclass

```python
@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def center_x(self) -> int:
        return self.x + self.w // 2

    @property
    def center_y(self) -> int:
        return self.y + self.h // 2

    def inset(self, margin: int) -> "Rect":
        return Rect(self.x + margin, self.y + margin, self.w - margin * 2, self.h - margin * 2)
```

### Grid Constants

Extracted verbatim from `ui/icons.py`. All other modules import from here.

```python
# M18 screen dimensions
SCREEN_W: int = 480
SCREEN_H: int = 272
COLS: int = 5
ROWS: int = 3
CELL_W: int = 96   # SCREEN_W // COLS

# Visible area per button — measured via calibration patterns.
# Physical bezels obscure ~12px/side horizontally, ~15-20px/side vertically.
VIS_COL_X: list[int] = [11, 107, 203, 299, 395]   # left edge per column
VIS_COL_W: list[int] = [72, 72, 72, 72, 72]        # visible width per column
VIS_ROW_Y: list[int] = [10, 110, 200]              # top edge per row
VIS_ROW_H: list[int] = [60, 60, 70]                # visible height per row
```

### `cell_rect(col, row)` helper

```python
def cell_rect(col: int, row: int) -> Rect:
    """Return the visible Rect for a given (col, row) grid position."""
    return Rect(VIS_COL_X[col], VIS_ROW_Y[row], VIS_COL_W[col], VIS_ROW_H[row])
```

### `key_to_grid(key_num)` mapping

```python
def key_to_grid(key_num: int) -> tuple[int, int] | None:
    """Key number (1-15) to (col, row).

    M18 physical-to-key mapping (verified by hardware testing):
      Top row:    KEY_11  KEY_12  KEY_13  KEY_14  KEY_15
      Middle row: KEY_6   KEY_7   KEY_8   KEY_9   KEY_10
      Bottom row: KEY_1   KEY_2   KEY_3   KEY_4   KEY_5
    """
    if key_num < 1 or key_num > 15:
        return None
    if 1 <= key_num <= 5:
        return (key_num - 1, 2)
    if 6 <= key_num <= 10:
        return (key_num - 6, 1)
    return (key_num - 11, 0)
```

### Design Tokens

```python
BG_COLOR: tuple[int, int, int] = (28, 28, 30)        # Near-black — matches iOS bbBackground dark
SECONDARY_TEXT: tuple[int, int, int] = (142, 142, 147)
CARD_RADIUS: int = 6
CARD_MARGIN: int = 2
BACK_BUTTON_BG: tuple[int, int, int] = (38, 38, 40)

# Category accent colors (align with iOS design system)
CATEGORY_COLORS: dict[str, tuple[int, int, int]] = {
    "feeding":  (102, 204, 102),  # Soft green
    "diaper":   (204, 170, 68),   # Warm amber
    "sleep":    (102, 153, 204),  # Soft blue
    "note":     (153, 153, 153),  # Neutral gray
    "settings": (200, 200, 200),  # Light gray
}
```

### `darken(color, factor)` utility

```python
def darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))
```

---

## 4. Text Engine (`ui/framework/text_engine.py`)

Replaces three duplicate `_get_font()` implementations in `icons.py`, `detail.py`,
`notes.py`, `settings.py`, and the separate `_get_bold_font()` in `dashboard.py`.

### `get_font(size, bold=False)` with cache

```python
_font_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}

def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font at the given size with an in-process cache.

    Search order: DejaVu (Raspberry Pi), Helvetica (macOS dev), PIL default.
    The bold=True path prefers the Bold variant; falls back to regular if absent.
    """
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]
    # ... load and cache
    _font_cache[key] = font
    return font
```

The font search paths must handle both Raspberry Pi (DejaVu) and macOS dev (Helvetica).
Bold paths are tried first when `bold=True`, with graceful fallback to regular.

### `fit_text(draw, text, max_width, max_height, font_sizes=(14, 12, 10))` — text overflow

```python
def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    font_sizes: tuple[int, ...] = (14, 12, 10),
    bold: bool = False,
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, str]:
    """Find the largest font size at which `text` fits within (max_width, max_height).

    Tries each size in order. If no size fits, uses the smallest size and truncates
    with an ellipsis until it fits. Returns (font, display_text).

    This is the single canonical path for any text that might overflow a cell.
    Never call draw.text() directly in screen factories — call fit_text() first.
    """
```

**Truncation algorithm**:
1. Try each `font_size` in order. Measure `draw.textbbox((0,0), text, font=font)`.
2. If `text_w <= max_width and text_h <= max_height`, return `(font, text)`.
3. After exhausting all sizes: use smallest font, progressively strip characters from the
   right and append `"…"` until it fits.
4. If a single character + ellipsis still does not fit, return `(font, "…")`.

### `draw_centered_text(draw, text, rect, fill, font)` — replaces 4 duplicates

```python
def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    rect: Rect,
    fill: tuple[int, int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """Draw text centered within rect."""
    tb = draw.textbbox((0, 0), text, font=font)
    tw = tb[2] - tb[0]
    th = tb[3] - tb[1]
    tx = rect.x + (rect.w - tw) // 2
    ty = rect.y + (rect.h - th) // 2
    draw.text((tx, ty), text, fill=fill, font=font)
```

---

## 5. Icon Cache (`ui/framework/icon_cache.py`)

Wraps the existing `_load_and_tint` and `_load_two_icon_composite` logic with a proper
LRU cache using `functools.lru_cache`. The current dict-based cache in `icons.py` is
module-level global state — the LRU cache is cleaner and respects memory bounds.

### `load_and_tint(asset_name, color, size) -> Image.Image | None`

```python
@lru_cache(maxsize=128)
def load_and_tint(
    asset_name: str,
    color: tuple[int, int, int],
    size: int,
) -> Image.Image | None:
    """Load a white PNG asset, tint with color, resize to size×size.

    Uses the Tabler icon assets in assets/icons/. Returns None if the asset
    is not found (callers should handle gracefully with a text fallback).
    """
```

The tinting algorithm is preserved exactly: multiply white pixel RGB channels by the
target color channels, preserve alpha.

### `load_composite(asset_a, asset_b, color, size) -> Image.Image | None`

```python
@lru_cache(maxsize=32)
def load_composite(
    asset_a: str,
    asset_b: str,
    color: tuple[int, int, int],
    size: int,
) -> Image.Image | None:
    """Render two icons as a 2×2 quadrant composite (a top-left, b bottom-right).

    Used for the diaper_both button: poo icon top-left, diaper icon bottom-right.
    """
```

### Asset registry

```python
ICON_ASSETS: dict[str, str | tuple[str, str]] = {
    "breast_left":  "letter_l",
    "breast_right": "letter_r",
    "bottle":       "bottle",
    "pump":         "pump",
    "diaper_pee":   "diaper",
    "diaper_poop":  "poo",
    "diaper_both":  ("poo", "diaper"),   # tuple → composite
    "sleep":        "moon",
    "note":         "note",
    "settings":     "gear",
}
```

This dict is the single source of truth for asset resolution. Screen factories use it;
they do not reference asset filenames directly.

---

## 6. Widget System (`ui/framework/widgets.py`)

Widgets are the building blocks for cell content. They are stateless: constructed with
data, rendered immutably into a `Rect`.

### Widget protocol

```python
from typing import Protocol

class Widget(Protocol):
    def render(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        rect: Rect,
    ) -> None:
        """Render this widget into rect. Must not mutate state."""
        ...
```

### Widget types

**`Card(fill, outline, radius)`** — rounded rectangle background. Usually the first widget
rendered in a cell, establishing the visual card.

```python
@dataclass
class Card:
    fill: tuple[int, int, int] | None = None
    outline: tuple[int, int, int] | None = None
    radius: int = CARD_RADIUS

    def render(self, img, draw, rect: Rect) -> None: ...
```

**`Text(text, font_sizes, color, bold)`** — single line of text centered in the cell. Uses
`fit_text` internally.

**`TwoLineText(line1, line2, color1, color2, sizes1, sizes2)`** — two lines vertically
centered as a group (as in settings cards: label on top, value below).

**`Icon(asset_name, color, size)`** — renders a tinted Tabler icon centered in the cell.
Falls back to a 4-character text abbreviation if the asset is missing.

**`IconLabel(asset_name, color, label, icon_size, badge)`** — the standard home grid cell:
icon centered above label text, optional badge string below. This is the most-used widget.

```python
@dataclass
class IconLabel:
    asset_name: str | tuple[str, str]   # str → single, tuple → composite
    color: tuple[int, int, int]
    label: str
    icon_size: int = 36
    badge: str | None = None            # e.g. "▶ NEXT" for suggested breast

    def render(self, img, draw, rect: Rect) -> None: ...
```

**`Spacer()`** — renders nothing. Used for empty cells (reserved columns, etc.).

### Composing widgets

A cell may have a list of widgets rendered in order. The typical pattern is:

```python
# A selected option card:
[Card(fill=category_color), Text("One Side", color=(255,255,255))]

# An unselected option card:
[Card(fill=darken(color, 0.1), outline=color), Text("Both Sides", color=color)]

# A home grid button:
[Card(fill=darken(color, 0.12)), IconLabel("moon", color, "SLEEP")]
```

---

## 7. Screen Definitions (`ui/framework/screen.py`)

### `CellDef`

```python
@dataclass
class CellDef:
    widgets: list[Widget]       # rendered in order into the cell rect
    key_num: int                # physical key number (1-15)
    on_press: str | None = None # action string, e.g. "select_option:0", "back", "home"
    span_cols: int = 1          # future: allow a cell to span columns
```

### `ScreenDef`

```python
@dataclass
class ScreenDef:
    name: str                               # debug identifier
    cells: dict[int, CellDef]              # key_num → CellDef
    background_color: tuple[int, int, int] = BG_COLOR
    pre_render: Callable[[Image.Image, ImageDraw.ImageDraw], None] | None = None
    # pre_render: optional callback for non-cell content (e.g. the sleep mode
    # central layout, the detail screen title bar). Called before cells are rendered.
```

Cells not in the `cells` dict render as empty (background color only).

### `ScreenRenderer`

```python
class ScreenRenderer:
    """Renders a ScreenDef to 480x272 JPEG bytes."""

    def render(self, screen_def: ScreenDef) -> bytes:
        """Produce JPEG bytes for the given ScreenDef.

        Steps:
        1. Create 480x272 RGB image with background_color.
        2. If pre_render is set, call it (handles non-cell content like title bars).
        3. For each CellDef in cells: resolve cell_rect(col, row), render each widget.
        4. Encode as JPEG quality=90 and return bytes.
        """
```

**Key property**: `ScreenRenderer.render()` is pure. Same `ScreenDef` input always
produces identical output. It holds no state.

---

## 8. Screen Factories (`ui/screens/`)

Screen factories are functions that take runtime data and return a `ScreenDef`. They never
call `ScreenRenderer` directly — the controller calls `renderer.render(factory(data))`.

### `build_home_grid(buttons, runtime_state)` — `ui/screens/home.py`

```python
def build_home_grid(
    buttons: dict[int, ButtonConfig],
    runtime_state: dict[int, str] | None = None,
) -> ScreenDef:
    """Build the main 15-button home grid.

    runtime_state maps key_num → state string:
      sleep key (13): "active:1h 32m" or "idle"
      breast keys (11, 6): "suggested" or "idle"
    """
```

Replaces `render_key_grid()` in `ui/icons.py`. The sleep button active state and
suggested breast badge are handled by selecting different widget configurations, not by
special-casing inside a monolithic render loop.

### `build_detail_screen(title, options, timer_seconds, color)` — `ui/screens/detail.py`

```python
def build_detail_screen(
    title: str,
    options: list[dict],       # {label, key_num, selected: bool}
    timer_seconds: int,
    category_color: tuple[int, int, int],
) -> ScreenDef:
    """Build a parameter selection screen.

    Layout:
      Top row cells (keys 11-14): option cards (selected=filled, unselected=outlined)
      Key 15 (top-right): timer countdown card
      Key 1 (bottom-left): BACK card
      All other cells: empty
    pre_render callback: draws the title text centered in the middle row title area.
    """
```

Replaces `render_detail_screen()` in `ui/detail.py`.

### `build_confirmation_screen(label, context, icon, color, style, col)` — `ui/screens/confirmation.py`

```python
def build_confirmation_screen(
    action_label: str,
    context_line: str,
    icon_name: str,
    category_color: tuple[int, int, int],
    celebration_style: str = "color_fill",
    column_index: int = 0,
) -> ScreenDef:
    """Build the post-log celebration screen.

    celebration_style:
      "color_fill": fills the action's column cells at ~40% brightness (single frame)
      "none": plain background, icon + text only
    The column fill is implemented via pre_render (draws the column background before cells).
    Key 1 is always the UNDO cell. All other cells are Spacer().
    """
```

Replaces `render_confirmation()` in `ui/confirmation.py`.

### `build_selection_screen(items, accent_color)` — `ui/screens/selection.py`

```python
def build_selection_screen(
    items: list[dict],         # {label, icon (optional), key_num}
    accent_color: tuple[int, int, int],
    title: str | None = None,
) -> ScreenDef:
    """Generic grid selection screen. Up to 14 items (key 1 reserved for BACK).

    Used for notes submenu. Can replace any screen that is "pick one of N things".
    Items are laid out in key order: 11, 12, 13, 14, 15, 6, 7, 8, 9, 10, 2, 3, 4, 5.
    """
```

Replaces `render_notes_submenu()` in `ui/notes.py`. More general — can be reused for
any category picker.

### `build_settings_screen(settings_model)` — `ui/screens/settings_screen.py`

```python
def build_settings_screen(settings: SettingsModel) -> ScreenDef:
    """Auto-generate the settings screen from SettingsModel field metadata.

    Each field with cycle_values in json_schema_extra becomes a TwoLineText card:
      Line 1: field display_name (label font, secondary color)
      Line 2: current value formatted via display_fn (value font, accent color)
    Key 15 (top-right, row 0): BACK card.
    """
```

Replaces `render_settings_screen()` in `ui/settings.py`. Settings cards are generated
from the `SettingsModel` schema rather than hard-coded in the renderer.

### `build_sleep_screen(elapsed_minutes, start_time_str)` — `ui/screens/sleep_screen.py`

```python
def build_sleep_screen(
    elapsed_minutes: int,
    start_time_str: str,
) -> ScreenDef:
    """Build the full-screen sleep mode takeover.

    The central content (moon icon, elapsed time, start time) is rendered via
    pre_render as a vertically centered block — not grid-cell-aligned.
    Key 13 (col 2, top): dim "WAKE UP" card with on_press="wake_up".
    All other cells: Spacer() with on_press="wake_screen" (brightens display, no log).
    """
```

Replaces `render_sleep_mode()` in `ui/sleep.py`.

### `build_dashboard_screen(dashboard_data, connected, queued)` — `ui/screens/dashboard_screen.py`

```python
def build_dashboard_screen(
    dashboard_data: dict | None,
    connected: bool,
    queued_count: int,
) -> ScreenDef:
    """Build the touchscreen dashboard panel.

    The dashboard is entirely pre_render content (not grid-cell-aligned).
    cells is empty — no key presses are routed on the dashboard display.
    """
```

Wraps `render_dashboard()` from `ui/dashboard.py`. The dashboard does not use the
button grid for interaction, so all content goes into `pre_render`.

### `build_tutorial_screen(step, step_num, total)` — `ui/screens/tutorial.py` (Phase 6)

```python
def build_tutorial_screen(
    step: TutorialStep,
    step_num: int,
    total: int,
) -> ScreenDef:
    """Build a tutorial/onboarding screen.

    Shows instructional text and a diagram of the physical button being explained.
    Key 15: NEXT. Key 1: BACK. Physical button buttons highlighted in pre_render.
    Requires physical button support (Phase 6 — hardware dependent).
    """
```

---

## 9. State Machine (`ui/state_machine.py`)

### Thread safety rationale

The current `DisplayState` is mutated by two threads:

- **Key handler thread**: reads `mode`, dispatches action, writes new `mode` and state
  fields.
- **Tick thread**: reads `mode`, checks timers (`confirmation_expires`,
  `detail_timer_expires`), can change `mode` to `home_grid` on expiry.

Without a lock, these interleave. Example race: key handler reads `mode == "confirmation"`,
tick fires and sets `mode = "home_grid"`, key handler dispatches UNDO to a
`home_grid`-state system.

### `StateMachine`

```python
class StateMachine:
    """Thread-safe wrapper around DisplayState.

    All reads and writes to DisplayState go through StateMachine methods.
    The RLock allows reentrant acquisition — a method that holds the lock can
    call another method that also acquires it.
    """

    def __init__(self, initial_state: DisplayState) -> None:
        self._state = initial_state
        self._lock = threading.RLock()

    def try_handle_key(self, key_num: int) -> tuple[str, DisplayState]:
        """Acquire lock, return atomic snapshot of (mode, state).

        The caller (KeyRouter) uses the snapshot to decide which action to fire.
        The action handler then calls a transition method (enter_detail, etc.)
        which also acquires the lock (reentrant).

        Returns (mode_at_press_time, state_snapshot).
        """
        with self._lock:
            return (self._state.mode, copy.copy(self._state))

    def advance_tick(self, now: float) -> str | None:
        """Called by tick thread. Checks timers, fires auto-transitions.

        Returns the mode that was auto-transitioned to, or None.
        Acquires lock for the full check-and-maybe-transition operation.
        """
        with self._lock:
            # Check confirmation expiry, detail timer expiry, etc.
            ...

    def enter_detail(self, action, options, default_index, context, timer_expires) -> None:
        with self._lock:
            self._state.enter_detail(...)

    def enter_confirmation(self, ...) -> None:
        with self._lock:
            self._state.enter_confirmation(...)

    # ... all other transition methods delegate to DisplayState under the lock
```

### State variants

The `DisplayState` fields that represent per-mode state are already logically tagged by
`mode`. The state machine does not restructure this — it wraps it. A future refactor
(post-MVP) could make these proper tagged union variants, but the locking is the critical
fix.

### Atomic snapshot for key routing

`try_handle_key()` returns a snapshot. The `KeyRouter` uses the snapshot's `mode` and
state to decide what action to fire. The action handler then calls the appropriate
transition method, which acquires the lock again (reentrant RLock). This ensures:

1. Key handler always sees a consistent `(mode, state)` pair.
2. Tick thread cannot change mode between when the key handler reads it and when the key
   handler acts on it.

---

## 10. Key Router (`ui/key_router.py`)

### Physical button map

Three physical side buttons flank the M18 screen. Their key numbers are TBD pending
hardware test. Placeholder mapping:

```python
PHYSICAL_BUTTONS: dict[int, str] = {
    16: "back",
    17: "home",
    18: "settings",
}
```

Update after physical button testing. These must be verified on the actual device.

### `KeyRouter`

```python
class KeyRouter:
    """Routes physical key presses to action strings based on the active ScreenDef.

    The active ScreenDef is set by the controller whenever the screen changes.
    When a key is pressed:
      1. Check PHYSICAL_BUTTONS map (side buttons bypass the ScreenDef).
      2. Look up CellDef for key_num in active_screen.cells.
      3. If CellDef.on_press is set, call the registered action handler.
      4. If no CellDef or on_press is None: no-op (cell is decorative/empty).
    """

    def __init__(self) -> None:
        self._active_screen: ScreenDef | None = None
        self._handlers: dict[str, Callable[..., None]] = {}

    def set_screen(self, screen_def: ScreenDef) -> None:
        self._active_screen = screen_def

    def register(self, action: str, handler: Callable) -> None:
        """Register a handler for an action string."""
        self._handlers[action] = handler

    def handle_key(self, key_num: int) -> None:
        """Called on every key press. Dispatches to registered handler."""
```

### Action string conventions

Action strings follow the pattern `"verb"` or `"verb:param"`:

| Action string | Meaning |
|---|---|
| `"back"` | Return to previous screen / home |
| `"home"` | Navigate to home grid unconditionally |
| `"settings"` | Open settings screen |
| `"select_option:N"` | Select option index N on detail screen |
| `"wake_up"` | End active sleep (key 13 during sleep mode) |
| `"wake_screen"` | Brighten display (all other keys during sleep mode) |
| `"undo"` | Undo the last logged action (key 1 during confirmation) |
| `"settings_cycle:field"` | Cycle a settings field by name |
| `"settings_open:subsection"` | Open a settings subsection |
| `"recent_undo:N"` | Undo recent action index N |

---

## 11. Settings Model (`settings.py`)

### `SettingsModel`

A Pydantic `BaseModel` that carries both the values and the UI metadata needed to render
the settings screen automatically. `json_schema_extra` provides the metadata.

```python
class SettingsModel(BaseModel):
    timer_duration_seconds: int = Field(
        default=7,
        json_schema_extra={
            "display_name": "Timer",
            "cycle_values": [0, 3, 5, 7, 10, 15],
            "display_fn": lambda v: "Off" if v == 0 else f"{v}s",
        },
    )
    skip_breast_detail: bool = Field(
        default=False,
        json_schema_extra={
            "display_name": "Quick Log",
            "cycle_values": [False, True],
            "display_fn": lambda v: "ON" if v else "OFF",
        },
    )
    celebration_style: str = Field(
        default="color_fill",
        json_schema_extra={
            "display_name": "Celebr",
            "cycle_values": ["color_fill", "radiate", "randomize", "none"],
            "display_fn": {"color_fill": "Fill", "radiate": "Glow",
                           "randomize": "Fun", "none": "Off"}.get,
        },
    )
    brightness: int = Field(
        default=80,
        ge=0, le=100,
        json_schema_extra={
            "display_name": "Brightness",
            "cycle_values": [20, 40, 60, 80, 100],
            "display_fn": lambda v: f"{v}%",
        },
    )
    tutorial_completed: bool = Field(
        default=False,
        json_schema_extra={"display_name": "Tutorial", "hidden": True},
    )
```

### `cycle_field(name)`

```python
def cycle_field(self, name: str) -> "SettingsModel":
    """Return a new SettingsModel with the named field advanced to its next cycle value.

    Does not mutate self. Caller replaces the active settings instance.
    """
    field_info = self.model_fields[name]
    cycle_values = field_info.json_schema_extra["cycle_values"]
    current = getattr(self, name)
    next_idx = (cycle_values.index(current) + 1) % len(cycle_values)
    return self.model_copy(update={name: cycle_values[next_idx]})
```

### Persistence

Settings are persisted to `~/.baby-macropad/settings.yaml` as YAML. This is separate
from `config/local.yaml` (which contains secrets and is not user-editable via the device).

```python
SETTINGS_PATH = Path.home() / ".baby-macropad" / "settings.yaml"

def load_settings() -> SettingsModel:
    if SETTINGS_PATH.exists():
        data = yaml.safe_load(SETTINGS_PATH.read_text())
        return SettingsModel(**data)
    return SettingsModel()

def save_settings(settings: SettingsModel) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(yaml.safe_dump(settings.model_dump()))
```

### Integration with `MacropadConfig`

`SettingsModel` replaces the `settings_menu` section of `MacropadConfig` for runtime
values. `MacropadConfig.settings_menu` (the `SettingsMenuConfig`) provides the initial
defaults if no `settings.yaml` exists. On startup:

```python
settings = load_settings()  # user's persisted prefs
# Fall back to config defaults for any missing fields (handled by Pydantic defaults)
```

---

## 12. LED Controller (`ui/led.py`)

All 8 LED flash methods are extracted from `main.py` into `LedController` with no
behavior changes. The generation-counter pattern that cancels superseded flashes is
preserved exactly.

### `LedController`

```python
class LedController:
    """Manages LED ring state and flash animations.

    The generation counter ensures that if a new flash is requested while a previous
    animation loop is still running, the old loop exits early rather than overwriting
    the new animation's LEDs.
    """

    def __init__(self, device: StreamDockDevice | StubDevice) -> None:
        self._device = device
        self._generation = 0
        self._lock = threading.Lock()

    def flash_success(self, category_color: tuple[int, int, int]) -> None:
        """Category-colored success flash: 600ms on, 200ms fade."""
        self._start_flash_thread(self._run_success_flash, category_color)

    def flash_ack(self) -> None:
        """Immediate acknowledgment (white, 150ms). Called before any API request."""
        self._start_flash_thread(self._run_ack_flash)

    def flash_error(self) -> None:
        """3 rapid red flashes (200ms on / 100ms off)."""
        self._start_flash_thread(self._run_error_flash)

    def flash_offline(self) -> None:
        """3 slow amber beats (500ms on / 300ms off)."""
        self._start_flash_thread(self._run_offline_flash)

    def flash_undo(self) -> None:
        """White flash, 300ms."""
        self._start_flash_thread(self._run_undo_flash)

    def flash_sleep_start(self) -> None:
        """3 slow blue pulses, then transition to sleep ambient."""
        self._start_flash_thread(self._run_sleep_start_flash)

    def flash_wake(self) -> None:
        """Warm white sunrise burst (400ms full, 600ms fade)."""
        self._start_flash_thread(self._run_wake_flash)

    def set_sleep_ambient(self) -> None:
        """Very dim blue glow during active sleep."""
        self._start_flash_thread(self._run_sleep_ambient)

    def clear(self) -> None:
        """Cancel all animations and turn LEDs off."""
        with self._lock:
            self._generation += 1
        self._device.set_led_all((0, 0, 0))
```

### Generation counter pattern (preserved)

```python
def _start_flash_thread(self, fn: Callable, *args) -> None:
    with self._lock:
        self._generation += 1
        gen = self._generation
    t = threading.Thread(target=fn, args=(gen, *args), daemon=True)
    t.start()

def _run_success_flash(
    self,
    gen: int,
    color: tuple[int, int, int],
) -> None:
    # Check gen before each sleep to exit if superseded
    self._device.set_led_all(color)
    time.sleep(0.6)
    if self._generation != gen:
        return
    # ... fade steps
```

---

## 13. Button Misfire Fix

Two independent fixes address the misfire and debounce problems.

### Fix 1: Debounce reduction (300ms → 150ms)

The current 300ms debounce window is too aggressive. A user logging breast left followed
immediately by breast right (a common sequence) fires both within 300ms. The second press
is silently dropped.

**Fix**: Reduce debounce from 300ms to 150ms in the device event loop. This allows genuine
rapid double-presses within 200ms while still filtering hardware bounce (which occurs in
< 10ms).

```python
DEBOUNCE_MS = 150   # was 300
```

Location: wherever key press timestamps are compared in `main.py` (or in `device.py` if
the debounce is implemented there). Verify exact location before changing.

### Fix 2: Race condition — `try_handle_key()` atomicity

See Section 9. The state machine's `try_handle_key()` acquires `RLock` before reading
`mode` and state. The tick thread's `advance_tick()` also acquires the lock. These two
operations are now mutually exclusive.

**Before (broken)**:
```python
# Key handler thread
if self._state.mode == "confirmation":      # reads mode
    # tick thread fires here, sets mode = "home_grid"
    if key_num == 1:
        self._handle_undo()                 # undo in home_grid context — wrong!
```

**After (fixed)**:
```python
# Key handler thread
mode, snapshot = self._sm.try_handle_key(key_num)   # atomic read under lock
if mode == "confirmation":
    if key_num == 1:
        self._handle_undo(snapshot)        # always consistent
```

---

## 14. Migration Strategy

The migration is structured so each phase produces a fully functional, tested system.
The old renderers remain importable until Phase 5. A feature flag controls which path
the controller uses.

### Phase 1: Foundation (zero behavior change)

**Deliverables**: `ui/framework/primitives.py`, `ui/framework/text_engine.py`,
`ui/framework/icon_cache.py`, `settings.py`

**Rules**:
- Extract constants and functions, do not add features.
- All existing tests must pass without modification after this phase.
- `ui/icons.py` and all legacy renderers still work.
- `text_engine.py` is importable but not yet called by anything.

**Verification**: `pytest` green. `from baby_macropad.ui.framework.primitives import Rect`
works.

### Phase 2: Widget system + ScreenRenderer + home screen factory

**Deliverables**: `ui/framework/widgets.py`, `ui/framework/screen.py`,
`ui/screens/home.py`

**Feature flag**: `config.yaml` gets `use_new_renderer: false` (default). When set to
`true`, `main.py` calls `build_home_grid()` + `ScreenRenderer` instead of
`get_key_grid_bytes()`.

**Rules**:
- Home grid output must be visually identical to the legacy renderer (verified by eye
  and by snapshot test comparing JPEG output).
- Legacy renderer still available and still the default.

### Phase 3: Migrate all screen factories

**Deliverables**: `ui/screens/detail.py`, `ui/screens/confirmation.py`,
`ui/screens/selection.py`, `ui/screens/settings_screen.py`, `ui/screens/sleep_screen.py`,
`ui/screens/dashboard_screen.py`

**Rules**:
- Each factory replaces its legacy renderer one at a time, tested independently.
- `use_new_renderer: true` in CI after all factories are migrated.
- Visual regression: run both old and new renderer on the same data, compare JPEG diff.

### Phase 4: State machine + Key router + LED extraction (fixes misfires)

**Deliverables**: `ui/state_machine.py`, `ui/key_router.py`, `ui/led.py`

**Rules**:
- StateMachine replaces bare `DisplayState` in `main.py`.
- LED methods move to `LedController` — no new behavior.
- Debounce reduced from 300ms to 150ms.
- After this phase, `main.py` must be under 250 lines.

### Phase 5: Cleanup

**Deliverables**: Delete legacy renderers, remove feature flag, remove compatibility shims.

**Rules**:
- Only after Phase 4 is confirmed stable in production (Pi running without misfires for
  at least 48 hours).
- Remove: `ui/icons.py` (contents moved to primitives + icon_cache), `ui/detail.py`,
  `ui/confirmation.py`, `ui/sleep.py`, `ui/notes.py`, `ui/settings.py`.
  `ui/dashboard.py` can be kept or removed (it wraps a pre_render, low coupling).

### Phase 6: Tutorial + physical buttons (hardware dependent)

**Deliverables**: `ui/screens/tutorial.py`, physical button map in `key_router.py`

**Prerequisites**: Physical side buttons verified on hardware. Button key numbers
confirmed (currently 16, 17, 18 — placeholder).

---

## 15. Acceptance Criteria

### Phase 1 — Foundation

- [ ] `from baby_macropad.ui.framework.primitives import Rect, cell_rect, key_to_grid`
      works with no import errors.
- [ ] `cell_rect(0, 0)` returns `Rect(x=11, y=10, w=72, h=60)`.
- [ ] `key_to_grid(13)` returns `(2, 0)` (sleep button, col 2, top row).
- [ ] `key_to_grid(0)` returns `None` (out of range).
- [ ] `fit_text(draw, "LEFT BREAST", 68, 56)` returns a `(font, text)` pair where the
      text fits within 68×56 pixels at the returned font size.
- [ ] `fit_text(draw, "AVERYLONGLABELHERE", 40, 20)` returns text ending in `"…"`.
- [ ] `get_font(12)` and `get_font(12)` (called twice) return the same object (cached).
- [ ] `load_and_tint("moon", (102, 153, 204), 36)` returns an `Image.Image` of size 36×36.
- [ ] All existing tests pass without modification.

### Phase 2 — Widget system + home screen factory

- [ ] `ScreenRenderer().render(ScreenDef(...))` returns `bytes` of length > 1000.
- [ ] `ScreenRenderer().render(same_screen_def)` called twice returns byte-identical
      output (deterministic rendering).
- [ ] `build_home_grid(buttons)` returns a `ScreenDef` with 15 `CellDef` entries.
- [ ] The `use_new_renderer: true` home grid is visually identical to the legacy renderer
      (manual pixel-diff verification or snapshot test).
- [ ] `IconLabel` renders correctly when the asset file is missing (falls back to 4-char
      text abbreviation, does not raise).

### Phase 3 — All screen factories

- [ ] `build_detail_screen("LEFT BREAST", options, 7, green_color)` produces a `ScreenDef`
      where key 1's `CellDef.on_press == "back"`.
- [ ] `build_detail_screen(...)` timer card is at key 15 (col 4, row 0).
- [ ] `build_confirmation_screen(..., celebration_style="color_fill", column_index=0)`
      produces a JPEG where column 0 is visually distinct from columns 1-4 (verified
      by sampling pixel colors in each column).
- [ ] `build_selection_screen(items, color)` with 14 items fills keys 11-15, 6-10, 2-5
      and leaves key 1 as BACK.
- [ ] `build_sleep_screen(92, "10:14 PM")` produces a `ScreenDef` where key 13's
      `on_press == "wake_up"` and all other keys have `on_press == "wake_screen"`.
- [ ] `build_settings_screen(SettingsModel())` produces cards for every non-hidden field
      in `SettingsModel`.

### Phase 4 — State machine + key router + LED extraction

- [ ] `StateMachine.try_handle_key()` returns a snapshot consistent with the current mode —
      never returns `mode="confirmation"` when state has already transitioned to
      `"home_grid"` (concurrent thread test with `threading.Barrier`).
- [ ] Under concurrent load (100 key presses from one thread, `advance_tick()` from
      another at 100Hz), no `AttributeError` or `KeyError` occurs (race condition test).
- [ ] Debounce at 150ms allows a rapid double-press within 200ms to register both presses.
      (Simulated: inject two key events 180ms apart, verify both are handled.)
- [ ] `LedController.flash_success()` followed immediately by `LedController.flash_error()`
      results in the error pattern, not the success pattern (generation counter test).
- [ ] `main.py` is under 250 lines after Phase 4.

### Phase 5 — Cleanup

- [ ] Deleting `ui/icons.py`, `ui/detail.py`, `ui/confirmation.py`, `ui/sleep.py`,
      `ui/notes.py`, `ui/settings.py` does not break any test or import.
- [ ] `from baby_macropad.ui.icons import get_key_grid_bytes` raises `ImportError`
      (confirming removal).
- [ ] All existing tests pass (imports updated as needed).

### Phase 6 — Tutorial + physical buttons (hardware dependent)

- [ ] Physical button key numbers confirmed on hardware and documented in
      `ui/key_router.py` `PHYSICAL_BUTTONS`.
- [ ] `build_tutorial_screen(step, 1, 5)` produces a `ScreenDef` with NEXT at key 15 and
      BACK at key 1.
- [ ] `SettingsModel.tutorial_completed` is set to `True` and persisted after the last
      tutorial step.
