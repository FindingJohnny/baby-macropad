# Baby Basics Macropad — UX Interaction Design

> Version: 2.0.0
> Last Reviewed: 2026-02-27
> Status: Approved for Implementation

## Changelog

- v2.0.0 (2026-02-27): Major revision. Column-based layout, detail screens, sleep full-screen
  mode, UNDO on confirmation, settings menu, notes submenu, LED color now working (SETLB/DELED).
- v1.0.0 (2026-02-27): Initial draft.

---

## Overview

This document defines the complete interaction design for the StreamDock M18 macropad as a
companion to the Nuroots iOS app. The macropad is a physical, always-on logging device in
the nursery. It must work reliably at 3 AM with one hand and zero friction.

**Design principle**: The macropad is not a miniature tablet. It is a dedicated physical control
surface. Every interaction must be faster than unlocking a phone.

---

## Hardware Constraints (Interaction Budget)

```
Device: StreamDock M18
  Display:     480x272 LCD — single JPEG image behind 5x3 button grid
  Buttons:     15 screen keys + 3 physical side buttons
  Visible/btn: ~72x60 pixels (top/mid rows), ~72x70px (bottom row)
  LED ring:    24 RGB LEDs — SETLB per-LED RGB control confirmed working
  Refresh:     ~50ms for full JPEG + STP commit (one display update per frame)
  Connectivity: USB to Raspberry Pi, Pi on WiFi to home network
```

**Frame budget**: Each screen update costs ~50ms. Animation at 10fps is feasible; 20fps is
the practical maximum. 60fps is not achievable. Every frame is intentional.

**LED status**: LED color is now confirmed working via `SETLB` (per-LED RGB) and `DELED`
(reset to firmware default). All color designs in this document are implementable.

**Thread model**: Screen writes and LED commands share a write lock. Animation must run in a
background thread and yield the lock between frames.

---

## Button Layout

Physical-to-logical key mapping (verified by hardware testing).

The M18 numbers keys bottom-to-top within each column pair:

```
TOP ROW:    KEY_11  KEY_12  KEY_13  KEY_14  KEY_15
MID ROW:    KEY_6   KEY_7   KEY_8   KEY_9   KEY_10
BOT ROW:    KEY_1   KEY_2   KEY_3   KEY_4   KEY_5
```

### Home Screen — Column = Category

```
         COL 0      COL 1      COL 2      COL 3      COL 4
TOP:   [Breast L] [  Pee   ] [ Sleep  ] [  ----  ] [  Gear  ]
MID:   [Breast R] [  Poop  ] [  Pump  ] [  ----  ] [  ----  ]
BOT:   [ Bottle ] [  Both  ] [ Notes  ] [  ----  ] [  ----  ]

Keys:    1/6/11     2/7/12     3/8/13    4/9/14     5/10/15
```

- **Column 0 (Feeding)**: Breast Left (top), Breast Right (mid), Bottle (bot)
- **Column 1 (Diaper)**: Pee (top), Poop (mid), Both (bot)
- **Column 2 (Sleep + Pump + Notes)**: Sleep toggle (top), Pump (mid), Notes submenu (bot)
- **Column 3**: Reserved for future Home Assistant integration (Phase 2). Show empty/dim cells.
- **Column 4**: Settings gear (top key 15). Remaining keys in col 4 are empty/dim.

Each button visible area: 72px wide x 60px tall (top/mid), 72px x 70px (bottom row).
Content centered within the visible window, not the full cell.

---

## Screen Modes

The display operates in one of these modes at any time:

| Mode | Trigger | Exits via |
|------|---------|-----------|
| `home_grid` | Startup, confirmation auto-dismiss, cancel | Always the default |
| `detail` | Pressing a button that requires a parameter choice | Option tap, timer expiry, or cancel |
| `confirmation` | Successful log, UNDO tap during window | 2s timer, or UNDO tap |
| `sleep_mode` | Sleep button pressed (sleep starts) | WAKE UP button, or any press (wake only) |
| `notes_submenu` | Notes button pressed | Category tap, or back |
| `settings` | Settings gear pressed | Any selection or back |

---

## Interaction Flows

### Breast Left / Breast Right

```
Press key →
  Show DETAIL SCREEN (breast detail):
    Title: "LEFT BREAST" (or "RIGHT BREAST")
    Row 1 options: [One Side]  [Both Sides]   ← "One Side" pre-selected
    Row 2: [Cancel/Back]       [timer: 7s]
  →
  Option tap OR timer expiry with default (One Side):
    API call: log_feeding(type="breast", started_side="left", both_sides=False)
    Show CONFIRMATION SCREEN
```

**Both Sides** option changes the API call to `both_sides=True`.

**Skip option**: A setting ("Skip breast detail screen") bypasses the detail screen and
logs directly with the last-used or suggested configuration.

### Bottle

```
Press key →
  Show DETAIL SCREEN (bottle detail):
    Title: "BOTTLE"
    Row 1 options: [Formula]  [Breast Milk]   ← no pre-selection (user must choose)
    Row 2: [Skip / No type]   [Cancel/Back]   [timer: 7s]
  →
  Option tap OR timer expiry (defaults to no type — logs bottle only):
    API call: log_feeding(type="bottle", source=<chosen or None>)
    Show CONFIRMATION SCREEN
```

### Pee

```
Press key →
  Instant log: log_diaper(type="pee")
  Show CONFIRMATION SCREEN
```

No detail screen. Pee is the simplest event — pure one-press logging.

### Poop

```
Press key →
  Show DETAIL SCREEN (consistency):
    Title: "POOP"
    Row 1 options: [Watery]  [Loose]  [Formed]  [Hard]   ← "Formed" pre-selected
    Row 2: [Cancel/Back]              [timer: 7s]
  →
  Option tap OR timer expiry with default (Formed):
    API call: log_diaper(type="poop", consistency=<chosen>)
    Show CONFIRMATION SCREEN
```

### Both (Poop + Pee)

```
Press key →
  Show DETAIL SCREEN (consistency, same as poop):
    Title: "PEE + POOP"
    Row 1: [Watery]  [Loose]  [Formed]  [Hard]   ← "Formed" pre-selected
    Row 2: [Cancel/Back]                [timer: 7s]
  →
    API call: log_diaper(type="both", consistency=<chosen>)
    Show CONFIRMATION SCREEN
```

### Pump

```
Press key →
  Instant log: log_note(content="Pumping session")
  Show CONFIRMATION SCREEN
```

Pump is a quick-action like Pee — no parameters needed. Uses note endpoint with a
fixed content string (configurable in YAML).

### Notes Submenu

```
Press key →
  Show NOTES SUBMENU (fills the button grid area):
    Row 1: [Meds]  [Temp]  [Milestone]  [Custom 1]  [Custom 2]
    Row 2: [Custom 3] ... (configurable in YAML)
    Row 3: [Back]
  →
  Category tap:
    API call: log_note(content=<category label or configured text>)
    Show CONFIRMATION SCREEN
```

The notes submenu repurposes the full 15-button grid for category selection. "Back"
returns to home grid without logging.

**Configuration** (config/default.yaml):
```yaml
notes_categories:
  - label: "Meds"
    content: "Medication given"
    icon: "pill"
  - label: "Temp"
    content: "Temperature taken"
    icon: "thermometer"
  - label: "Milestone"
    content: "Milestone logged"
    icon: "star"
```

Up to 14 categories fit (leaving one button for Back). Unused slots render as empty/dim.

### Sleep Toggle

Two very different flows depending on current state:

**Sleep START (no active sleep)**:
```
Press Sleep key →
  API call: start_sleep()
  Enter SLEEP MODE (full-screen)
```

**Sleep END (active sleep exists)**:
```
Press WAKE UP key (same physical key) →
  API call: end_sleep(sleep_id)
  Show WAKE-UP CONFIRMATION SCREEN (special variant, 2s)
  Return to HOME GRID
```

---

## Detail Screen Design

The detail screen is a reusable pattern used for breast side, bottle source, and poop
consistency. It takes over the full 480x272 display.

```
┌──────────────────────────────────────────────────────┐
│  LEFT BREAST                              [7]        │
│  ─────────────────────────────────────────           │
│                                                      │
│  [  One Side  ]  [  Both Sides  ]                    │
│   ← pre-selected                                     │
│                                                      │
│  [  Back  ]                                          │
└──────────────────────────────────────────────────────┘
```

### Timer

- Shown in top-right corner, counts down from the configured value (default 7s)
- Visual: decreasing arc or number, category color
- Timer expiry = auto-commit with currently highlighted default
- Timer resets on any button interaction (touching any option resets to 0 and commits)

### Layout (480x272, respecting button grid positions)

The detail screen renders into the same 480x272 JPEG, but the button positions must
align with the physical key grid so presses hit the right option.

```
Physical key grid → detail option mapping:

TOP ROW    (keys 11, 12, 13, 14, 15):  [Option A]  [Option B]  [Option C]  [Option D]  [  ----  ]
MID ROW    (keys  6,  7,  8,  9, 10):  (empty)     (empty)     (empty)     (empty)     (empty)
BOT ROW    (keys  1,  2,  3,  4,  5):  [  Back  ]  (empty)     (empty)     (empty)     (  ----  )
```

For poop consistency (4 options):
- Key 11: Watery
- Key 12: Loose
- Key 13: Formed (default, highlighted)
- Key 14: Hard
- Key 1: Back / Cancel

For breast detail (2 options):
- Key 11: One Side (default)
- Key 12: Both Sides
- Key 1: Back / Cancel

For bottle source (3 options):
- Key 11: Formula
- Key 12: Breast Milk
- Key 13: Skip (no type)
- Key 1: Back / Cancel

### Visual Treatment

- Selected/default option: bright filled card, category color background, white text
- Unselected options: dark card, category color border, category color text
- Back button: near-black card, secondary text color "BACK"
- Timer countdown rendered in top-right corner of the full display (not per-button)

---

## Confirmation Screen Design

Shown for 2 seconds after every successful log. The only active key during this window
is UNDO (one designated key). All other key presses are ignored.

### Layout

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│         [TABLER ICON — 64px, category color]         │
│                                                      │
│           Left breast logged                         │  ← 24px bold
│           Next: Right breast                         │  ← 16px secondary color
│                                                      │
│  [  UNDO  ]                                          │  ← bottom-left key position
│                                                      │
└──────────────────────────────────────────────────────┘
```

The UNDO button position maps to a specific physical key — recommended key 1 (bottom-left),
as it is the most naturally reachable position with one hand.

### Grid-Aware Celebration Rendering

The confirmation screen uses the button grid structure creatively. Rather than a flat
panel, the 15 button cells are used as a visual canvas:

**Option A — Color Fill Pattern** (simple, reliable):
- The confirmed action's category color fills the action's column cells
- Other column cells show a dimmer version or complementary accent
- Example: after logging Poop, column 1 cells all show amber, other columns dim

**Option B — Radiating Highlight** (moderate complexity):
- The pressed button cell pulses bright, then the pattern radiates outward
- Rendered as a series of JPEG frames (3-5 frames at 10fps = 300-500ms)
- Returns to static confirmation layout after animation

**Configurable celebration style** (settings menu):
- `celebration_style: color_fill` — Option A (default)
- `celebration_style: radiate` — Option B
- `celebration_style: randomize` — random between A and B each time
- `celebration_style: none` — simple icon + text only

### Context Line (second line below action label)

| Action | Context |
|--------|---------|
| Breast left/right | `"Next: Right breast"` (from dashboard `suggested_side`) |
| Bottle | `"14 feeds today"` (from `today_counts.feedings`) |
| Pee | `"4 diapers today"` |
| Poop | `"2 poops today"` |
| Both | `"5 diapers today"` |
| Pump | `"Pumping session logged"` |
| Note | Category name + `"logged"` |
| Sleep start | `"Awake for 2h 15m"` (from last sleep end time) |

**Offline mode**: Replace context line with `"Queued — will sync when connected"` in
warning amber color.

### Auto-dismiss

After 2 seconds, confirmation screen auto-dismisses to home grid. If user is sleeping
and a press accidentally triggered a log, the 2s UNDO window gives them a chance to
correct without unlocking the phone.

---

## Sleep Mode

Sleep mode is a distinct full-screen experience. It is not a button overlay — it takes
over the entire display and changes the interaction model.

### Entering Sleep Mode

Triggered when Sleep button is pressed and the API confirms sleep has started.

```
Transition:
  1. Sleep button pressed → LED acknowledgment flash (blue)
  2. API call: start_sleep() → success
  3. Display transitions to sleep mode JPEG
  4. Screen dims to minimum brightness (LIG level 10)
  5. After 30s idle: screen turns off (LIG level 0)
```

### Sleep Mode Display

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│                   ))) ☾ (((                          │  ← moon icon, 72px, blue
│                                                      │
│                  sleeping...                         │  ← 20px, secondary color
│                  1h 32m                              │  ← 32px bold, blue accent
│                                                      │
│                  started 10:14 PM                    │  ← 14px, dim secondary
│                                                      │
└──────────────────────────────────────────────────────┘
```

Background: near-black (same as bbBackground dark mode).
Moon icon: Tabler `moon` filled, blue accent color (123, 155, 196).
Timer: updates every 60 seconds via display tick thread.
Start time: shows the wall-clock time sleep began.

### Wake Behavior During Sleep Mode

- **Any button press**: Screen wakes (LIG to full brightness), shows sleep mode view,
  30s idle timer resets
- **WAKE UP button press** (same physical key as Sleep, key 13 col 2 top): Ends sleep

**Key layout during sleep mode**: All 15 keys are effectively "wake" buttons. Only key 13
(Sleep position) actually ends the sleep. All other key presses wake the screen but do
not log anything. This prevents accidental sleep termination from a brush against the device.

**Display text during sleep (key 8 area only)**:
The sleep mode JPEG must visually indicate that key 13 / col 2 top is "WAKE UP". Because the
full display is the sleep panel (not a button grid), render a small "WAKE UP" label at the
position of that key's visible area (centered in the col 2 / top row cell at x=203-275, y=10-70).

```
Sleep mode with wake hint:
┌──────────────────────────────────────────────────────┐
│   [  ][  ][ WAKE ][  ][  ]                          │  ← key positions, subtle
│   [  ][  ][ UP   ][  ][  ]
│
│               ))) ☾ (((
│              sleeping...
│              1h 32m
│
│              started 10:14 PM
└──────────────────────────────────────────────────────┘
```

The WAKE UP hint is rendered dimly (secondary text color) so it is visible but not
jarring in a dark room.

### Exiting Sleep Mode

```
WAKE UP key pressed →
  Screen brightens immediately (LIG 80)
  API call: end_sleep(sleep_id) → success
  Show WAKE-UP CONFIRMATION SCREEN (special, 2s)
  Return to HOME GRID
```

### Wake-Up Confirmation Screen

This is the highest-value moment in the device's UX — the parent just successfully
tracked a nap. Make it feel meaningful.

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│         [SUNRISE ICON — 64px, warm amber]            │
│                                                      │
│           Baby's awake!                              │  ← 24px bold, warm white
│           Slept 2h 14m                               │  ← 20px, sleep blue accent
│           4.5h sleep today                           │  ← 16px, secondary
│                                                      │
└──────────────────────────────────────────────────────┘
```

Duration: 2 seconds (same as standard confirmation). No UNDO on wake-up (intentional
— accidental wake logging is very unlikely, and editing on phone is easy).

**LED**: Warm amber/white burst at full brightness (SETLB all LEDs to warm white
(255, 220, 150)) for 800ms, then off.

---

## UNDO

### UNDO on Confirmation Screen

During the 2-second confirmation window, one designated key acts as UNDO.
Recommended position: key 1 (bottom-left), naturally reachable with thumb.

```
Confirmation screen active:
  Key 1 = "UNDO" (rendered in the key 1 visible area with X icon + "UNDO" label)
  All other keys = ignored
  Timer still counting down

UNDO pressed:
  API call: DELETE /children/:childId/{resource}/:id
  Show brief UNDO confirmation ("Undone" + faded icon)
  Return to HOME GRID
```

If the API call fails (offline): Queue the delete. Show amber queued indicator.

The UNDO button should be visually distinct from celebration content — use a
near-black background with secondary text, so it does not distract from the
celebration but is clearly tappable if needed.

### UNDO in Settings Menu

The settings menu exposes a "Recent Actions" view showing the last 5 logged events.
Each entry has a delete/undo action. This covers the case where the parent notices
the error after the 2s window.

```
Settings → Recent Actions:
  [moon] Sleep — started 10:14 PM  [Undo]
  [diaper] Pee — 10:08 PM          [Undo]
  [bottle] Bottle — 9:45 PM        [Undo]
  ...
```

Implementation: the macropad stores the last 5 action IDs (returned from API) in memory.
On Pi restart, these are lost (acceptable — phone is the source of truth for editing).

---

## LED Ring Design

LED color is now confirmed working via `SETLB` command (per-LED RGB, 24 LEDs).

### Idle State

```
All LEDs off (brightness 0)
```

The nursery is dark. An always-on LED ring would disturb sleep. Off is the right idle state.

**Exception — sleep mode ambient**: During active sleep, a very dim blue glow is acceptable
as a "device is active" indicator. See Sleep Mode LED below.

### Immediate Acknowledgment (press → API in flight)

```
Color: white (255, 255, 255)
Brightness: 60
Duration: 150ms
Then: off (or transition to success/error color)
```

This is the "I heard you" signal. Happens on every key press regardless of outcome.

### Success Feedback by Category

```
Feeding (breast / bottle):
  Color: green (102, 204, 102)
  Pattern: on 600ms, fade out 200ms
  Brightness: 65

Diaper (pee / poop / both):
  Color: amber (204, 170, 68)
  Pattern: on 600ms, fade out 200ms
  Brightness: 65

Pump / Note:
  Color: gray (153, 153, 153)
  Pattern: on 400ms, off
  Brightness: 50

Sleep START:
  Color: blue (102, 153, 204)
  Pattern: 3 slow pulses (on 300ms, off 200ms each)
  Brightness: 50
  Then: transition to sleep ambient

Sleep END (wake up):
  Color: warm white (255, 220, 150)
  Pattern: burst at brightness 100 for 400ms, fade to 0 over 600ms
  This is the "sunrise" effect
```

### Offline / Queued

```
Color: amber (255, 180, 0)
Pattern: 3 slow beats (on 500ms, off 300ms each)
Brightness: 55
```

Distinct from success amber (diaper) because of the different rhythm — slower, three beats.

### Error (unrecoverable)

```
Color: red (220, 60, 60)
Pattern: 3 quick flashes (on 200ms, off 100ms each)
Brightness: 80
```

Fast staccato = urgent. Different from all other patterns.

### Sleep Mode Ambient LED

```
During active sleep:
  Color: dim blue (30, 60, 90)
  Brightness: 8 (barely visible — just enough to know the device is active)
  Pattern: slow breathing
    → brightness 5 to 12 over 4 seconds
    → brightness 12 to 5 over 4 seconds
    → repeat
```

The breathing pattern is optional — it adds "aliveness" but the duty cycle must be
extremely gentle. If the LED breathing is too visible in a dark room during testing,
reduce brightness to 4-6 max and skip the breathing pattern (static dim).

### LED Fade Implementation

`SETLB` can be called repeatedly with decreasing brightness values to create a fade.
At 50ms per write, a 200ms fade = 4 intermediate brightness steps. That is enough
to read as a smooth fade at this brightness range.

---

## Settings Menu

Settings are accessed via the gear icon (key 15, top-right).

### Settings Layout (uses full button grid)

```
TOP ROW:   [Timer]   [Skip Bst]  [Celebr]  [Lock]   [Back ←]
MID ROW:   [Brt Sch] [Disp Off] [Recent]  [  ---]   [  --- ]
BOT ROW:   (empty)   (empty)    (empty)   (empty)   (empty)
```

Each settings key opens a sub-panel or cycles through options:

| Key | Setting | Behavior |
|-----|---------|---------|
| Timer | Auto-commit duration | Tap cycles: 5s → 7s → 10s → 15s → off |
| Skip Bst | Skip breast detail screen | Toggle on/off |
| Celebr | Celebration style | Cycles: color fill → radiate → randomize → none |
| Lock | PIN lock | Enter 4-key sequence to lock/unlock (toddler guard) |
| Brt Sch | Brightness schedule | Opens sub-panel: day level / night level / night start / night end |
| Disp Off | Display-off during sleep | Toggle: off during active sleep yes/no |
| Recent | Recent actions + undo | Opens recent actions list (last 5) |
| Back | Exit settings | Return to home grid |

Settings changes take effect immediately and persist to disk (JSON sidecar alongside config).

### Brightness Schedule Sub-Panel

```
Brightness schedule:
  Day brightness:   [40] [60] [80] [100]   ← default 80
  Night brightness: [10] [20] [30] [ 40]   ← default 20
  Night starts:     [8PM][9PM][10PM][11PM]
  Night ends:       [5AM][6AM][ 7AM][ 8AM]
  [Save]  [Cancel]
```

The schedule dims the display during configured night hours automatically.

---

## Dynamic Button States (Home Grid)

The home grid is state-aware. These buttons change appearance based on live data:

| Button | Condition | Normal | Active |
|--------|-----------|--------|--------|
| Key 13 (Sleep, col 2 top) | active_sleep is not None | Moon + "SLEEP" | Moon + "WAKE UP" + elapsed |
| Key 11 (Breast L, col 0 top) | suggested_side == "left" | Green card | Bright green + "NEXT" badge |
| Key 6 (Breast R, col 0 mid) | suggested_side == "right" | Green card | Bright green + "NEXT" badge |

### Sleep Button Active Layout (72x60px visible area)

```
  [moon 26px]
  WAKE UP   ← 10px bold
  1h 32m    ← 9px, sleep blue accent
```

### Suggested Breast Badge

```
  Normal key:                    When suggested:
  ┌──────────────┐               ┌──────────────┐
  │  [icon 36px] │               │  [icon 36px] │
  │   LEFT       │               │   LEFT       │  ← 20% brighter card bg
  └──────────────┘               │  ▶ NEXT      │  ← 8px, category color
                                 └──────────────┘
```

Space is tight. "NEXT" must be 8px maximum. Use the category green color at full opacity.

---

## Rendering Architecture

### Screen Modes and State

```python
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
    detail_action: str | None = None       # "log_feeding", "log_diaper", etc.
    detail_context: dict = field(default_factory=dict)   # params so far
    detail_timer_expires: float = 0.0      # monotonic time

    # Confirmation screen
    confirmation_action: str | None = None
    confirmation_result: dict | None = None
    confirmation_expires: float = 0.0     # monotonic time
    confirmation_resource_id: str | None = None  # for UNDO

    # Sleep mode
    sleep_start_time: str | None = None   # ISO timestamp

    # Live data
    dashboard: DashboardData | None = None
    connected: bool = True
    queued_count: int = 0

    # Settings (runtime, persisted separately)
    timer_seconds: int = 7
    skip_breast_detail: bool = False
    celebration_style: str = "color_fill"
    brightness_day: int = 80
    brightness_night: int = 20
```

### Render Dispatch

```python
def refresh_display(self) -> None:
    s = self._display_state
    now = time.monotonic()

    if s.mode == "sleep_mode":
        jpeg = render_sleep_mode(s.sleep_start_time)

    elif s.mode == "confirmation" and now < s.confirmation_expires:
        jpeg = render_confirmation(
            s.confirmation_action,
            s.confirmation_result,
            s.dashboard,
        )

    elif s.mode == "detail" and now < s.detail_timer_expires:
        jpeg = render_detail_screen(
            s.detail_action,
            s.detail_context,
            seconds_remaining=int(s.detail_timer_expires - now),
        )

    elif s.mode == "notes_submenu":
        jpeg = render_notes_submenu(self.config.notes_categories)

    elif s.mode == "settings":
        jpeg = render_settings(s)

    else:
        s.mode = "home_grid"
        jpeg = render_key_grid(
            self.config.buttons,
            suggested_side=s.dashboard.suggested_side if s.dashboard else None,
            active_sleep=s.dashboard.active_sleep if s.dashboard else None,
        )

    self._screen_jpeg = jpeg
    self._device.set_screen_image(jpeg)
```

### Display Tick Thread

A lightweight 30-second tick thread drives the sleep timer update and confirmation
screen auto-dismiss without needing the dashboard poll:

```python
def _display_tick_loop(self) -> None:
    while not self._shutdown.is_set():
        self._shutdown.wait(10)   # 10s tick
        if not self._shutdown.is_set():
            self.refresh_display()
```

The 10s tick also handles:
- Confirmation auto-dismiss (checks `confirmation_expires`)
- Detail screen timer expiry (auto-commits with default)
- Sleep mode timer update (every 60s is fine; the 10s tick will catch the minute boundary)
- Brightness schedule (checks current time vs night schedule)

---

## Animation: Celebration Frames

For `celebration_style: radiate`, the confirmation screen plays a brief multi-frame
animation before settling to the static layout.

### Color Fill (default, single frame)

After logging, immediately render the confirmation screen with the column cells colored:

```
Feeding logged:
  Column 0 cells: bright green fill
  Other columns:  dark, slightly lighter than normal background
  Center panel:   icon + text (as usual)
```

Single JPEG, no animation loop needed.

### Radiate (multi-frame, 300ms total)

```
Frame 1 (0ms):    Pressed cell is bright (category color)
Frame 2 (100ms):  Adjacent cells begin to light up (dimmer)
Frame 3 (200ms):  Outer cells light, pressed cell fades slightly
Frame 4 (300ms):  Static confirmation layout
```

Implementation: render 4 JPEG frames, send in sequence with 100ms sleep between.
Each frame is a full 480x272 JPEG. At 50ms per send + 100ms sleep = ~150ms per frame.
4 frames = ~600ms total animation, then hold the static confirmation for remaining 1.4s.

This is achievable within the 50ms frame budget.

---

## Summary: Implementation Priority

### Phase 1 — Must Have

1. **Column-based home grid layout**: Feeding / Diaper / Sleep+Pump+Notes / empty / Settings.
   Reorganize config/default.yaml and update icon positions in `render_key_grid()`.

2. **DisplayState model**: Central to all subsequent features. Implement first.

3. **Detail screens**: Breast, Bottle, Poop consistency. Reusable pattern, same renderer
   with different option sets. Implement `render_detail_screen()`.

4. **Confirmation screen with UNDO**: `render_confirmation()` + UNDO API call + resource
   ID tracking. Grid-aware color fill (Option A) for celebration.

5. **Sleep mode**: Full-screen sleep panel, `render_sleep_mode()`, brightness management
   (dim → off → wake on press), WAKE UP key handling.

6. **Wake-up confirmation screen**: Special confirmation variant for sleep end. Show
   duration and today's sleep total.

7. **LED color patterns**: Now that SETLB is working, implement category-colored LED
   responses. Remove the brightness-only fallbacks.

8. **Dynamic home grid states**: Sleep button label flip (SLEEP ↔ WAKE UP + timer),
   suggested breast badge.

### Phase 2 — Should Have

9. **Notes submenu**: Full grid repurposed for category selection. Requires `notes_categories`
   config section and `render_notes_submenu()`.

10. **Settings menu**: Timer duration, skip breast detail, celebration style, lock/pin,
    brightness schedule, recent actions/undo. Requires `render_settings()` and settings
    persistence (JSON sidecar).

11. **Radiate celebration animation**: Multi-frame animation for `celebration_style: radiate`.
    Requires animation loop in confirmation flow.

12. **Sleep ambient LED breathing**: Gentle blue breathing during active sleep. Low priority
    due to nursery visibility concerns — test before enabling.

### Phase 3 — Deferred

13. **Home Assistant column**: Column 3 buttons for HA entity control. Requires HA API
    integration and state polling.

14. **PIN/toddler lock**: 4-key sequence to prevent accidental logging.

---

## Design Anti-Patterns to Avoid

**Do not exceed 2 lines of content per button cell**: 72x60px visible = icon (36px) + label
(11px) + one detail line (9px). Hard limit. Anything more is unreadable.

**Do not require more than 2 taps for any primary log**: Home press → (optional detail) →
confirmation. Never 3 taps for a routine action.

**Do not attempt 60fps animation**: 50ms per frame is the minimum. Design for 10fps max.
Three to five frames is enough for any celebration animation.

**Do not lock the device during sleep mode**: All 15 keys must wake the screen. Only the
designated WAKE UP key ends the sleep. Brush-against-device accidental wakes are fine;
accidental sleep termination is not.

**Do not make the UNDO button prominent**: It should be available but not visually competing
with the celebration. Near-black background, secondary text. It is an escape hatch, not a
featured action.

**Do not skip the LED acknowledgment on any key press**: The immediate white flash is the
most important single piece of feedback. It must happen before any API call, before any
screen render. Never remove it.
