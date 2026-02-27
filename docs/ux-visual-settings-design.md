# UX Visual, Settings & Home Assistant Design

> Version: 0.2.0
> Status: Approved
> Last Reviewed: 2026-02-27

## Overview

This document is the canonical UX reference for the baby-macropad. It covers:

1. **Button layout** — confirmed column-per-category grid
2. **Screen system** — home grid, detail screens, confirmation, sleep mode, settings
3. **Icon system** — assets, rendering, per-state variants
4. **Settings architecture** — config schema, display management, what syncs with the app
5. **Home Assistant integration** — deferred to Phase 2

All decisions in this document have been confirmed with the user.

---

## 1. Button Layout (Confirmed)

```
         COL 0       COL 1      COL 2       COL 3     COL 4
         FEEDING     DIAPER     SLEEP+      [HA]      SYSTEM
ROW 0: [Left     ] [Pee    ] [Sleep    ] [       ] [Settings]
ROW 1: [Right    ] [Poop   ] [Pump     ] [       ] [        ]
ROW 2: [Bottle   ] [Both   ] [Notes    ] [       ] [        ]
```

**Key assignments** (M18 physical mapping: keys 1-5 = bottom row, 6-10 = middle, 11-15 = top):

| Physical Key | Col | Row | Function |
|---|---|---|---|
| 11 | 0 | 0 | Breast Left |
| 6 | 0 | 1 | Breast Right |
| 1 | 0 | 2 | Bottle |
| 12 | 1 | 0 | Pee |
| 7 | 1 | 1 | Poop |
| 2 | 1 | 2 | Both (poo + pee) |
| 13 | 2 | 0 | Sleep toggle |
| 8 | 2 | 1 | Pump |
| 3 | 2 | 2 | Notes (opens submenu) |
| 15 | 4 | 0 | Settings gear |

Column 3 (keys 14, 9, 4) is reserved for Home Assistant — deferred to Phase 2. These buttons show blank/inactive icons.

---

## 2. Screen System

The M18's single 480x272 panel is always rendering one of these screen modes. All modes use the same `render_key_grid` composite approach — different screen modes swap out the button definitions passed to the renderer.

### 2.1 Home Grid (default)

The standard 15-button layout above. Always returns to this state after:
- Confirmation screen auto-dismiss (2s)
- Settings menu exit
- Back/Cancel on any detail screen

### 2.2 Detail Screen

Triggered by buttons requiring additional input before logging. Uses the same 5x3 grid; specific buttons are repurposed for the flow.

**Universal detail screen pattern:**

```
[  option A  ] [  option B  ] [  option C  ] [  option D  ] [  timer(7s) ]
[            ] [            ] [            ] [            ] [            ]
[ Back/Cancel] [            ] [            ] [            ] [            ]
```

- **Timer** displayed top-right (key 15 area). Counts down from configured default (7s). Expires = auto-commit with pre-selected default.
- **Default option** is pre-highlighted (brighter tint + subtle card outline).
- **Option buttons** fill the top row (options vary by action — see per-action specs below).
- **Back/Cancel** mapped to bottom-left (key 1). Returns to home grid without logging. Key 1 is the consistent "escape" position across all screens (Back on detail, UNDO on confirmation).
- **Tapping any option** = immediate commit + advance to confirmation. No separate confirm step.

**Timer behavior:**
- Timer duration is configurable (Settings > Timer Duration, default 7s).
- Timer can be disabled per-action via Settings (e.g., "Skip breast detail screen").
- When disabled: action logs immediately with default values, no detail screen shown.

### 2.3 Confirmation Screen

Shown after any successful log. Auto-dismisses after 2 seconds.

**Grid usage:**
- Creative use of the full grid for visual celebration (category-colored pattern, animations).
- Celebration style options: pick a fixed style, randomize, or disable (Settings > Celebration Style).
- Exactly **one key is active**: the UNDO button (mapped to key 1, bottom-left — same "escape" position as Back on detail screens).
- All other buttons are decorative during the 2s window.

**UNDO behavior:**
- Tap UNDO within the 2s window = DELETE the just-logged event via API.
- If offline: mark the queued event as cancelled before it syncs.
- After 2s: UNDO is gone, log is permanent (but accessible via Settings > Recent Actions).

**LED behavior:**
- On confirmation: brief flash in category color across the full LED ring.
- Flash duration: ~0.5s. Returns to idle color after flash.

### 2.4 Sleep Mode Screen

Full-screen takeover when baby sleep is active. This is not a standard grid — the panel renders a single large view.

**Layout:**

```
┌─────────────────────────────────────────────────┐
│                                                 │
│              🌙  (moon icon, large)             │
│                                                 │
│              sleeping...                        │
│              2h 14m                             │
│                                                 │
│          [ W A K E   U P ]                      │
│                                                 │
└─────────────────────────────────────────────────┘
```

- Moon icon centered, large (60-72px — full visible height of a button cell, no label needed).
- Elapsed sleep timer displayed below the icon ("2h 14m" style).
- "sleeping..." label in muted category-sleep color.
- WAKE UP hint rendered at key 13 position (col 2, top row — same physical key as Sleep on the home grid).
- **Only key 13 ends sleep.** All other 14 keys wake the screen (brighten + show sleep view + reset 30s idle timer) but do NOT end the sleep. This prevents accidental sleep termination from brushing the device.

**Screen brightness during sleep:**
- Immediately dims to minimum brightness (5-10, not 0 — just barely visible).
- After 30s idle: turns display fully OFF (brightness 0, LED ring off).
- Any button press (including WAKE UP): screen wakes, shows sleep view, 30s timer resets.
- WAKE UP logs the wake event → exits sleep mode → returns to home grid at full brightness.

### 2.5 Settings Menu

Accessed via key 15 (Settings gear, top-right). Full-screen overlay using the grid for navigation.

**Settings items (confirmed):**

| Setting | Options |
|---|---|
| Timer Duration | 3s / 5s / 7s (default) / 10s / Off |
| Skip Breast Detail | On / Off |
| Celebration Style | Pick style / Randomize / Disable |
| Lock / PIN | Enable/disable toddler lock + set PIN |
| Brightness Schedule | Day brightness, night brightness, night start/end times |
| Display Off During Sleep | On (default) / Off |
| Recent Actions / Undo | Shows last 5 logged events with individual undo |

Settings menu is navigated with the physical buttons. Each row of the grid shows one setting group. Back returns to home grid.

---

## 3. Per-Action Flows (Confirmed)

### Breast Left / Breast Right

```
Press button → detail screen
  Top row: [One Side (default)] [Both Sides] [     ] [     ] [timer]
  Bottom-right: [Back]

  Auto-commit after 7s with "One Side"

  → confirmation screen (category: feeding, green)
```

The "Both Sides" option is a modifier, not a separate logging action. Selecting "Both Sides" = feeding with `both_sides: true` in the API payload.

Settings: "Skip breast detail" = log immediately with `one_side` default, skip this screen.

### Bottle

```
Press button → detail screen
  Top row: [Formula (default)] [Breast Milk] [Skip→] [     ] [timer]
  Bottom-right: [Back]

  "Skip" = log bottle with no type specified (neutral)
  Auto-commit after 7s with "Formula"

  → confirmation screen (category: feeding, green)
```

### Pee

```
Press button → instant log (no detail screen)
  → confirmation screen (category: diaper, amber)
```

### Poop

```
Press button → detail screen (consistency)
  Top row: [Watery] [Loose] [Formed (default)] [Hard] [timer]
  Bottom-right: [Back]

  Auto-commit after 7s with "Formed"

  → confirmation screen (category: diaper, amber)
```

### Both (poo + pee)

```
Press button → detail screen (consistency, same as Poop)
  Top row: [Watery] [Loose] [Formed (default)] [Hard] [timer]
  Bottom-right: [Back]

  Auto-commit after 7s with "Formed"
  Logs: diaper type = "both"

  → confirmation screen (category: diaper, amber)
```

### Sleep (toggle)

```
If no active sleep:
  Press button → full-screen SLEEP MODE activated
  Logs: sleep start to API
  LED ring: pulses slow blue

If active sleep:
  WAKE UP press → exits sleep mode → home grid
  Logs: sleep end to API
  → confirmation screen (category: sleep, blue)
```

### Pump

```
Press button → instant log (no detail screen)
  → confirmation screen (category: feeding, green)
```

### Notes

```
Press button → submenu (note category picker)
  Top row: [General] [Health] [Milestone] [Mood] [timer]
  Bottom-right: [Back]

  Auto-commit after 7s with "General"
  Logs: note with selected category and default content "Quick note logged"

  → confirmation screen (category: note, gray)
```

Note: The macropad logs a note with a default/placeholder content string. Full note text editing is not practical on a macropad — use the iOS app for text entry.

---

## 4. Icon System

### Hardware constraints

| Measurement | Value |
|---|---|
| LCD panel | 480x272 px (single JPEG) |
| Full cell per button | 96x~91 px |
| **Visible area per button** | **~72x60 px** |
| Current icon size in renderer | 36x36 px |
| Label height | 13 px |
| Total content height | ~52 px (fits in 60px visible height) |

At 36px, icons must be high-contrast and filled. Stroke/outline icons disappear after JPEG compression at quality=90.

### Icon set: Tabler filled variants (confirmed)

All icons use Tabler filled variants. Never use outline/stroke variants for macropad rendering.

Source: `https://tabler.io/icons` — free MIT license.
Export process: Download SVG → convert to 64px PNG via `cairosvg` → place in `assets/icons/` → Pillow downscales to 36px with LANCZOS.

```bash
pip install cairosvg
python3 -c "
import cairosvg
cairosvg.svg2png(url='input-filled.svg', write_to='assets/icons/output.png', output_width=64, output_height=64)
"
```

### Breast icons (confirmed: search for proper nursing icon)

**Decision**: Search Tabler for a proper breast/nursing icon, not the teardrop approach. Tabler has `breast` (stroke only as of v3). If Tabler does not have a filled breast/nursing icon at adequate quality for 36px:

- **Fallback**: Use `baby` or `baby-carriage` Tabler icons as a category indicator for breast feeding, and rely exclusively on labels (`LEFT` / `RIGHT`) for side disambiguation.
- The label carries the critical information at this size. The icon's role is category (nursing) vs bottle recognition.
- Both Left and Right use the same nursing icon; the label `LEFT` / `RIGHT` differentiates them.

**Left vs Right visual distinction** (beyond the label):
- Left button: icon at full opacity.
- Right button: icon tinted with a slightly cooler hue (same green family, ~10° hue shift toward blue-green). Subtle but provides a second visual cue for muscle memory.

### Confirmed icon asset inventory

| Asset filename | Tabler source | Used by | State |
|---|---|---|---|
| `breast.png` | Tabler `breast` filled (or best available nursing icon) | Breast Left, Breast Right | static |
| `bottle.png` | Tabler `baby-bottle` filled | Bottle | static |
| `diaper.png` | Tabler `diaper` filled | Pee | static |
| `poo.png` | Tabler `poo` filled | Poop | static |
| `diaper-both.png` | Composite: poo (top-left) + diaper drop (bottom-right) | Both | static (composite) |
| `moon.png` | Tabler `moon` filled | Sleep — idle/home state | static |
| `sunrise.png` | Tabler `sun-rising` filled | Sleep — active (shown in sleep mode header) | static |
| `pump.png` | Tabler `bottle` or `droplet` filled | Pump | static |
| `note.png` | Tabler `note` filled | Notes | static |
| `gear.png` | Tabler `settings` filled | Settings | static |

### Diaper Both composite rendering

The Both button uses a two-icon composite: poo icon top-left, drop (pee) icon bottom-right.

```python
def _load_two_icon_composite(
    asset_a: str,
    asset_b: str,
    color: tuple[int, int, int],
    size: int,
) -> Image.Image | None:
    """Render two icons as a 2x2 quadrant composite (a top-left, b bottom-right)."""
    half = size // 2
    a = _load_and_tint(asset_a, color, half)
    b = _load_and_tint(asset_b, color, half)
    if a is None or b is None:
        return None
    composite = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    composite.paste(a, (0, 0), a)
    composite.paste(b, (half, half), b)
    return composite
```

This goes in `icons.py` alongside `_load_and_tint`. The `ICON_ASSETS` dict maps `"diaper_both"` to a tuple `("poo", "diaper")` to trigger composite rendering.

### Sleep icon: dynamic state

The sleep button has two rendering states: idle (home grid) vs active (sleep mode screen).

**Runtime state passing**: `render_key_grid` accepts an optional `runtime_state: dict[int, str]` parameter (key number → state string). The sleep button (key 13) gets `"active"` or `"idle"`.

```python
def render_key_grid(
    buttons: dict[int, Any],
    runtime_state: dict[int, str] | None = None,
) -> Image.Image:
    runtime_state = runtime_state or {}
    # ...
    state = runtime_state.get(key_num, "idle")
    # For sleep button: if state == "active", swap asset to sunrise.png + label to "WAKE UP"
```

### Color system

Category colors align with the iOS design system. These are the macropad-specific RGB values:

| Category | RGB | Notes |
|---|---|---|
| Feeding (breast/bottle/pump) | `(102, 204, 102)` | Soft green, aligns with iOS sage green preset |
| Diaper | `(204, 170, 68)` | Warm amber, aligns with iOS diaper token |
| Sleep | `(102, 153, 204)` | Soft blue |
| Note | `(153, 153, 153)` | Neutral gray |
| Settings/System | `(200, 200, 200)` | Light gray |

Column 3 (HA, Phase 2) will use warm yellow `(255, 196, 0)` for lights and soft cyan `(64, 180, 190)` for fan.

### LED ring color assignments

Per-LED control is confirmed available via `SETLB` command (24 LEDs, per-LED RGB). `DELED` resets to firmware default.

| Event / State | LED behavior |
|---|---|
| Idle / home grid | All LEDs off (nursery dark — no light disturbance) |
| Feeding logged | Green flash full ring, ~0.5s |
| Diaper logged | Amber flash full ring, ~0.5s |
| Sleep started | Slow blue pulse, continuous while sleeping |
| Sleep ended / wake logged | Blue flash full ring, then return to idle |
| Note logged | Gray flash full ring, ~0.5s |
| Pump logged | Green flash full ring, ~0.5s |
| Undo | White flash full ring, ~0.3s |
| Error / offline queue | Red pulse, 2s |
| Sleep mode display-off | All LEDs off |

Confirmation flash pattern: full ring at category color for 0.5s, fade to off over 0.5s. Total 1s LED effect.

---

## 5. Settings Architecture

### Decision: Local YAML only (MVP)

Settings live exclusively in `config/local.yaml` for MVP. No iOS app sync in Phase 1.

Rationale:
- The macropad's settings are device-specific (brightness, display-off). The iOS app doesn't need to know about them for MVP.
- Avoids requiring a new API endpoint and iOS Settings UI before the core tracking UX is complete.
- Power users who run a Raspberry Pi can edit a YAML file.

**Phase 2**: Evaluate adding a `macropad_settings` field to the user profile API for app-controlled preferences (animations, quiet hours, brightness schedule). Only if user requests it.

### Extended config schema

New sections added to the YAML schema and corresponding Pydantic models:

```yaml
display:
  auto_sleep_minutes: 10        # LCD off after N minutes idle (0 = never)
  off_during_sleep: true        # Dark display when baby sleep is active
  brightness_schedule:
    enabled: false
    day_brightness: 80          # Brightness during day hours (0-100)
    night_brightness: 20        # Brightness during night hours (0-100)
    night_start: "20:00"        # HH:MM local time, when night begins
    night_end: "06:00"          # HH:MM local time, when day resumes

animations:
  enabled: true
  quiet_hours:
    enabled: false
    start: "21:00"              # No animations during these hours
    end: "06:00"

settings_menu:
  timer_duration_seconds: 7     # Default auto-commit timer on detail screens
  skip_breast_detail: false     # Log breast feedings instantly
  celebration_style: "random"   # "random" | "confetti" | "pulse" | "disabled"
  lock_enabled: false
  lock_pin: ""                  # 4-digit PIN, empty = no PIN required
```

### Pydantic models

```python
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
    celebration_style: str = "random"  # "random"|"confetti"|"pulse"|"disabled"
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
```

### Display state machine

```
States: ACTIVE | DIMMED | OFF | SLEEP_MODE

ACTIVE → DIMMED:     idle timer fires (auto_sleep_minutes)
DIMMED → OFF:        additional 30s after DIMMED
OFF → ACTIVE:        any button press
ACTIVE/DIMMED → SLEEP_MODE:  active baby sleep detected AND off_during_sleep=True
SLEEP_MODE → ACTIVE: baby wakes (wake logged)
SLEEP_MODE + button press: wake to ACTIVE for 30s, return to OFF (not SLEEP_MODE end)
```

Brightness per state:

| State | LCD brightness | LED ring |
|---|---|---|
| ACTIVE (day) | `day_brightness` or `device.brightness` | Category color |
| ACTIVE (night schedule) | `night_brightness` | Idle dim color |
| DIMMED | 10 | All off |
| OFF | 0 | All off |
| SLEEP_MODE | 5 for 30s, then 0 | All off |

### Quiet hours / animation suppression

During quiet hours, animations are disabled:
- No LED pulse patterns (replace with instant flash).
- Confirmation screen: no celebration animation, just static colored grid.
- Brightness schedule respects `night_start` / `night_end` independently of quiet hours.

Midnight-wraparound time comparison:

```python
from datetime import time

def in_time_range(now: time, start: time, end: time) -> bool:
    """True if now is within [start, end). Handles midnight wraparound."""
    if start <= end:
        return start <= now < end
    return now >= start or now < end
```

---

## 6. Home Assistant Integration (Phase 2)

**HA is fully deferred to Phase 2.** Column 3 buttons render as blank/inactive for now.

### Phase 2 design (pre-planned)

When implemented:

- **Protocol**: REST API. Simple, stateless, universally supported. WebSocket only if polling lag is unacceptable after testing.
- **Config**: Local YAML only (`home_assistant.url`, `home_assistant.token`, entity IDs per button). Not synced via iOS app.
- **State feedback**: HA entity states polled in the existing 60s dashboard cycle. "Off" entities dimmed at 0.4 opacity on icon.
- **LED ring**: Bottom 8 LEDs (16-23) indicate HA states. Warm yellow = any light on. Cyan = fan on. Off = all HA off.
- **Failure handling**: HA actions are fire-and-forget. Not queued to offline SQLite. Red flash on error.
- **Validation tool**: `tools/check_ha.py` — validates token, lists entity IDs, tests a toggle.

Row 3 HA buttons (when Phase 2 lands):

| Key | Function | Icon | LED segment |
|---|---|---|---|
| 14 | Nursery Light | Tabler `bulb` filled | Segments 20-23 |
| 9 | Night Light | Tabler `bulb` filled (dimmer tint) | Segments 16-19 |
| 4 | Fan | Tabler `propeller` filled | Segments 8-11 |
| (Phase 3) | Sound Machine | Tabler `wave-square` filled | Segments 12-15 |
| (Phase 3) | All Off | Tabler `power` filled | — |

---

## 7. Implementation Priority

| Priority | Item | Complexity | Impact |
|---|---|---|---|
| P1 | Button layout update (col-per-category, add Pump + Notes) | Low | Critical — current layout is wrong |
| P1 | Breast icon (source proper nursing icon) | Low | High — current bottle icon is wrong |
| P1 | Diaper Both composite icon (`_load_two_icon_composite`) | Medium | High |
| P1 | Gear/Settings icon for key 15 | Low | High |
| P1 | Pump icon (Tabler bottle/droplet) | Low | Medium |
| P2 | Detail screen rendering system (option grid + timer) | High | Critical for breast/poop/bottle/notes flows |
| P2 | Confirmation screen (grid-based celebration + UNDO key) | High | Core UX |
| P2 | Sleep mode full-screen rendering + WAKE UP mapping | High | Core UX |
| P2 | Runtime state → render_key_grid (sleep toggle state) | Medium | Required for sleep button |
| P3 | Display config schema (display + animations + settings_menu) | Low | Enables all display management |
| P3 | Display state machine (auto-sleep, brightness schedule) | Medium | 3 AM use case |
| P3 | LED ring per-LED animations via SETLB | Medium | Confirmation feedback |
| P3 | Settings menu screen (navigate with buttons) | High | User-configurable preferences |
| P4 | Recent actions / undo (last 5) in settings | Medium | Nice to have |
| P5 | Home Assistant Phase 2 (all HA) | High | Deferred |
