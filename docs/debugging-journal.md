# StreamDock M18 Debugging Journal

A chronological record of the demo mode / USB disconnect debugging effort.
This took 15+ experiments across two sessions before reaching stability.

## The Problem

The StreamDock M18 firmware reverts to a built-in demo mode (rainbow LED
animation, cycling promotional display) after ~60 seconds. The device becomes
unresponsive to commands. This made the macropad unusable — it would start up
fine, display icons, then lose everything within a minute.

## Timeline of Attempts

### Phase 1: Keepalive Strategies (all failed)

These approaches all used the MiraboxSpace Python SDK, which wraps a
proprietary C library (`libtransport.so`).

| Commit   | Approach                              | Result              |
|----------|---------------------------------------|---------------------|
| `d7c8198`| Screen refresh every 2 min            | Demo mode at ~60s   |
| `b0dbff0`| Reduced keepalive traffic             | Demo mode at ~60s   |
| `a8b7746`| wakeScreen() + refresh() keepalive    | Demo mode at ~60s   |
| `104ff08`| Proactive device reinit every 60s     | USB disconnect       |
| `1edf07b`| Revert to screen image keepalive      | Demo mode at ~60s   |
| `6d64abd`| Disable keepalive (baseline test)     | Demo mode at ~60s   |

**Lesson**: The problem wasn't the keepalive strategy. The SDK itself was
causing the disconnects.

### Phase 2: Raw Heartbeat (partial success)

| Commit   | Approach                              | Result              |
|----------|---------------------------------------|---------------------|
| `716cb70`| Raw CONNECT via hidraw + disable autosuspend | Some stability |
| `270b3b2`| Fix: add HID report ID byte           | Heartbeat works     |
| `ab719e7`| Add N1EN switchMode(2) after init     | No improvement      |

**Discovery**: The `CONNECT` heartbeat command prevents demo mode when sent via
raw hidraw. But the SDK was still loaded for image transport, and its C library
caused USB disconnects even when we only called `transport.open()`.

### Phase 3: Pure Raw Hidraw (breakthrough)

| Commit   | Approach                              | Result              |
|----------|---------------------------------------|---------------------|
| `183a775`| Replace SDK reader with raw hidraw    | Still disconnecting |
| `bb9a3e4`| Set up image transport before hidraw  | Still disconnecting |
| `e1eedc2`| Prefer input0 (control interface)     | Still disconnecting |
| `d0e4b30`| **Full SDK removal — 100% raw hidraw**| Screen blank but stable |
| `29c2573`| Add brightness to init + 10s heartbeat| Stable but screen blank |

**The turning point**: When we removed the SDK entirely (commit `d0e4b30`), the
USB disconnects stopped completely. But the screen was blank because our raw
image send was missing a critical protocol step.

### Phase 4: Systematic Debugging (solution found)

After user feedback to "stop guessing and start problem solving," we switched
to methodical experiment-based debugging with explicit pass/fail tracking.

#### Research: Reverse Engineering the Protocol

1. **Bitfocus Companion source** (`streamdock.ts`): Revealed the BAT command
   for per-key images and STP for refresh. But Companion's VID/PID tables don't
   include our device (0x5548:0x1000).

2. **strace on the C library**: We ran `strace` on a test script that called
   `set_background_image_stream()` through the SDK. This captured the exact
   byte sequences the C library sends:

   - Background image uses **LOG** command (not BAT)
   - LOG header: `CRT + [0x4C, 0x4F, 0x47, size_be32, 0x01]`
   - JPEG data in 1024-byte chunks: `[0x00] + chunk`, padded to 1025
   - **No STP refresh** sent by the C library for background images

   The "no STP" observation from strace turned out to be misleading — see below.

3. **strace on LED commands**: Revealed LBLIG command for LED brightness:
   `CRT + [0x4C, 0x42, 0x4C, 0x49, 0x47, 0x00, 0x00, level]`

#### Controlled Experiments

Each experiment was run on the Pi with the user reporting device state:

| Experiment | Setup                              | Duration | Result        |
|------------|-------------------------------------|----------|---------------|
| EXP1       | Heartbeat only (no image)          | 30s      | PASS (blank, stable) |
| EXP2       | Heartbeat + LOG image + **STP**    | 30s      | PASS (image visible!) |
| EXP3 (try 1)| LOG image + 90s heartbeat        | 1s       | FAIL (stale USB) |
| EXP3 (try 2)| Same, after 10s USB settle        | 90s      | **PASS** (stable!) |
| EXP4       | Full service                       | ~35s     | FAIL (blank screen) |

**Critical finding from EXP2**: Adding STP refresh after LOG image made the
image actually appear on screen. The standalone test scripts included STP and
worked. The service's `set_screen_image()` did NOT send STP — explaining why
the screen was blank.

**Why strace was misleading**: The C library may handle STP internally via a
different code path, or the firmware may auto-commit for the C library's
specific write pattern. Regardless, raw hidraw requires explicit STP.

#### Root Cause Analysis of EXP4 (Service)

Even though EXP3 proved the protocol works, the full service still had a blank
screen. Examining the service logs revealed additional issues:

1. **Missing STP refresh**: `set_screen_image()` sent LOG header + chunks but
   no STP. The image data was received but never committed to the display.

2. **Thread-unsafe writes**: Multiple threads (heartbeat, LED flash, reader)
   all wrote to the same hidraw fd. The image send (header + 14 chunks) could
   be interleaved with a heartbeat write, corrupting the transfer.

3. **Button event flood**: A single physical press generated 12+ rapid-fire
   HID events, each spawning a new LED flash thread and API call thread.
   Multiple concurrent LED flash threads caused further write interleaving.

### Phase 5: Three-Fix Commit (stable)

Commit `50f8fe9` applied all three fixes simultaneously:

1. **STP refresh**: Added `os.write(self._hidraw_fd, _REFRESH_PACKET)` after
   the JPEG chunk loop in `set_screen_image()`.

2. **Write lock**: Added `threading.Lock()` to serialize all hidraw writes.
   The image send holds the lock for the entire LOG+chunks+STP sequence.
   Individual commands (heartbeat, LED brightness) acquire the lock for single
   writes.

3. **Button debounce**: Added 300ms per-key cooldown in `_on_key_press()`.
   Uses `time.monotonic()` for reliable timing. Prevents the event flood from
   spawning dozens of concurrent threads.

**Result**: Service stable for 100+ seconds with zero errors. Past the point
where every previous attempt had failed.

## Key Lessons

### 1. The SDK was the enemy

The MiraboxSpace SDK's C library (`libtransport.so`) causes USB disconnects
regardless of usage pattern. Even `transport.open()` alone was sufficient.
The C library spawns an internal reader thread that appears to conflict with
the firmware. Going 100% raw hidraw was the only solution.

### 2. strace is your best friend

The LOG command, JPEG chunking format, and LBLIG LED command were all
reverse-engineered from `strace` output. Without this, we would have been
guessing at byte sequences indefinitely.

### 3. Don't trust "it works in isolation"

The protocol worked perfectly in single-threaded test scripts. The service
failed because of threading issues that only manifest when heartbeat, image
send, LED flash, and button reading all compete for the same fd.

### 4. STP is non-obvious but critical

The C library's strace didn't clearly show STP after LOG. But without it,
the firmware receives the image data and does nothing with it. This was the
single most impactful fix.

### 5. Debounce raw HID events

The firmware sends multiple HID reports per physical button press. This
isn't a bug — it's standard for HID devices. But without debouncing, a
single button press triggers 12+ action dispatches, each with LED feedback
threads and API calls. The resulting thread explosion causes both write
interleaving and unnecessary API load.

### 6. Track experiments, don't guess

The systematic EXP1-EXP4 approach with explicit pass/fail criteria and
user-reported device state was what finally cracked it. The earlier phase
of making changes, deploying, and hoping led to 10+ failed attempts.

## Architecture (Final)

```
┌─────────────────────────────────────────────────────┐
│                  MacropadController                  │
│                                                     │
│  ┌─────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ API     │  │ Offline   │  │ Dashboard Poll   │  │
│  │ Client  │  │ Queue     │  │ (60s interval)   │  │
│  └────┬────┘  └─────┬─────┘  └──────────────────┘  │
│       │             │                                │
│  ┌────┴─────────────┴────────────────────────────┐  │
│  │              Action Dispatch                   │  │
│  │         (with 300ms debounce)                  │  │
│  └───────────────────┬───────────────────────────┘  │
│                      │                               │
│  ┌───────────────────┴───────────────────────────┐  │
│  │            StreamDockDevice                    │  │
│  │         (100% raw hidraw)                      │  │
│  │                                                │  │
│  │  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │  │
│  │  │ Writer   │  │ Reader   │  │ Heartbeat   │  │  │
│  │  │ (locked) │  │ (select) │  │ (10s loop)  │  │  │
│  │  └────┬─────┘  └────┬─────┘  └──────┬──────┘  │  │
│  │       │             │               │          │  │
│  │       └─────────────┴───────────────┘          │  │
│  │                     │                          │  │
│  │              /dev/hidraw0                       │  │
│  │           (input0, O_RDWR)                     │  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Diagnostic Commands

### Check service status
```bash
ssh nursery@nursery-macropad.local "sudo systemctl status baby-macropad"
```

### Tail live logs
```bash
ssh nursery@nursery-macropad.local "sudo journalctl -u baby-macropad -f"
```

### Check for errors in last N minutes
```bash
ssh nursery@nursery-macropad.local "sudo journalctl -u baby-macropad --priority=warning --since '5 minutes ago' --no-pager"
```

### USB hub reset (when device is stuck)
```bash
ssh nursery@nursery-macropad.local "echo 0 | sudo tee /sys/bus/usb/devices/1-1/authorized && sleep 2 && echo 1 | sudo tee /sys/bus/usb/devices/1-1/authorized && sleep 3 && ls /dev/hidraw*"
```

### Restart service
```bash
ssh nursery@nursery-macropad.local "sudo systemctl restart baby-macropad"
```

### Full recovery (USB reset + restart)
```bash
ssh nursery@nursery-macropad.local "sudo systemctl stop baby-macropad && echo 0 | sudo tee /sys/bus/usb/devices/1-1/authorized && sleep 2 && echo 1 | sudo tee /sys/bus/usb/devices/1-1/authorized && sleep 3 && sudo systemctl start baby-macropad"
```
