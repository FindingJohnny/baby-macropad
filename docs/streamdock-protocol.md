# StreamDock M18 CRT Protocol Reference

Reverse-engineered protocol documentation for the VSD Inside / HOTSPOTEKUSB
Stream Dock M18 (VID=0x5548, PID=0x1000).

**Sources**: Bitfocus Companion `streamdock.ts`, MiraboxSpace Python SDK,
`strace` of the SDK's C library (`libtransport.so`).

## Hardware Overview

| Property          | Value                                          |
|-------------------|------------------------------------------------|
| Vendor            | VSD Inside / HOTSPOTEKUSB                      |
| Model             | Stream Dock M18 (N1EN variant)                 |
| USB VID           | `0x5548`                                       |
| USB PID           | `0x1000`                                       |
| Display           | 480x272 LCD (single panel behind 5x3 key grid) |
| Keys              | 15 screen keys + 3 physical buttons            |
| LEDs              | 24 RGB LEDs (ring around dial)                 |
| HID Interface 0   | Control + button events (`usage_page=0xFF60`)  |
| HID Interface 1   | Standard keyboard HID (`usage_page=1`)         |

**Important**: Interface 0 (`input0`) is the control interface. Interface 1 is
a standard keyboard HID. All CRT commands and button event reads go through
interface 0. Using the wrong interface silently fails.

## Transport Layer

All communication uses Linux hidraw (`/dev/hidrawN`). The device enumerates two
hidraw nodes — one per HID interface. Use sysfs uevent matching to find the
correct one (see `_find_hidraw()` in `device.py`).

### Why Not the SDK?

The MiraboxSpace Python SDK wraps a proprietary C library (`libtransport.so`)
which uses `libhidapi-hidraw.so.0` internally. The C library spawns its own
reader thread that conflicts with the firmware, causing **USB disconnects after
~60 seconds**. Raw hidraw avoids this entirely and has been verified stable for
70+ minutes.

The C library's hidapi backend was confirmed via `strace`:
```
openat(AT_FDCWD, "/usr/lib/aarch64-linux-gnu/libhidapi-hidraw.so.0", ...)
```

### Packet Format

Every HID write is exactly **1025 bytes** (1024 payload + 1 report ID byte):

```
[0x00] [payload...] [0x00 padding to 1025 bytes]
```

- Byte 0: HID report ID (`0x00`). Linux hidraw strips this before sending to
  the device. It is mandatory.
- Bytes 1-1024: Payload, zero-padded.

### CRT Prefix

All command packets start with the CRT prefix after the report ID:

```
[0x00] [0x43, 0x52, 0x54, 0x00, 0x00] [command bytes...] [0x00 padding]
         C     R     T    \0    \0
```

The prefix is ASCII "CRT" followed by two null bytes.

## Commands

### CONNECT (Heartbeat)

Prevents the firmware from reverting to demo mode (rainbow LED animation +
cycling display). Must be sent every **10 seconds** (proven stable; 30s was
also stable in isolation but 10s provides more margin in a multi-threaded
service).

```
CRT + [0x43, 0x4F, 0x4E, 0x4E, 0x45, 0x43, 0x54]
       C     O     N     N     E     C     T
```

Full packet: `[0x00, 0x43, 0x52, 0x54, 0x00, 0x00, 0x43, 0x4F, 0x4E, 0x4E, 0x45, 0x43, 0x54, 0x00...]`

### DIS (Wake Screen)

Wakes the LCD from sleep/power-save mode. Send once during initialization.

```
CRT + [0x44, 0x49, 0x53]
       D     I     S
```

### LIG (Screen Brightness)

Sets the LCD backlight brightness. Level 0-100.

```
CRT + [0x4C, 0x49, 0x47, 0x00, 0x00, level]
       L     I     G    \0    \0    0-100
```

The Bitfocus Companion applies a gamma curve: `brightness = round(pow(level/100, 0.75) * 100)`.

### LOG (Background Image)

Sends a full 480x272 JPEG to the LCD panel. This is a multi-packet transfer.

**Step 1 — Header packet (CRT command)**:
```
CRT + [0x4C, 0x4F, 0x47, size_b3, size_b2, size_b1, size_b0, 0x01]
       L     O     G     ----size (big-endian 32-bit)----   layer
```

- `size`: JPEG data length in bytes, big-endian uint32
- `layer`: Always `0x01` for background image

**Step 2 — JPEG data chunks (raw, no CRT prefix)**:
```
[0x00] [jpeg_data[0:1024]]     padded to 1025 bytes
[0x00] [jpeg_data[1024:2048]]  padded to 1025 bytes
...
[0x00] [jpeg_data[last_chunk]] padded to 1025 bytes
```

Each chunk is prefixed with report ID `0x00` but does **NOT** include the CRT
prefix. Only the header uses CRT.

**Step 3 — STP refresh (CRT command)**:
```
CRT + [0x53, 0x54, 0x50]
       S     T     P
```

**The STP refresh is mandatory.** Without it, the image data is received by the
firmware but not committed to the display — the screen stays blank or shows the
previous image. This was the root cause of the "blank screen in service" bug.

**Thread safety**: The entire LOG sequence (header + chunks + STP) must be
atomic. If another thread sends a heartbeat or LED command between chunks, the
image transfer is corrupted. Use a write lock.

### BAT (Per-Key Image)

Sends a JPEG to a single key position. Used by Bitfocus Companion but not used
in our implementation (we use LOG for the full background).

```
CRT + [0x42, 0x41, 0x54, size_b3, size_b2, size_b1, size_b0, key_id]
       B     A     T     ----size (big-endian 32-bit)----   key
```

Followed by JPEG data chunks (same format as LOG) and STP refresh.

### LBLIG (LED Ring Brightness)

Controls the brightness of the 24 RGB LEDs around the dial.

```
CRT + [0x4C, 0x42, 0x4C, 0x49, 0x47, 0x00, 0x00, level]
       L     B     L     I     G    \0    \0    0-100
```

Level 0 turns off the LED ring entirely.

### SETLB (LED Ring Color)

Sets the color of the 24 RGB LEDs around the dial. Each LED gets an individual
R, G, B triplet, allowing per-LED color control. To set all LEDs to the same
color, repeat the same triplet 24 times.

```
CRT + [0x53, 0x45, 0x54, 0x4C, 0x42, R0, G0, B0, R1, G1, B1, ..., R23, G23, B23]
       S     E     T     L     B     ---  LED 0 ---  --- LED 1 --- ... --- LED 23 ---
```

- Each R, G, B value is 0-255.
- Total RGB data: 24 LEDs x 3 bytes = 72 bytes after the SETLB command.
- The entire payload (CRT prefix + SETLB + 72 bytes RGB) is zero-padded to 1024
  bytes, plus the 0x00 report ID prefix = 1025 bytes total.

**Reverse-engineered** via `strace` of `libtransport.so`'s
`transport_set_led_color(handle, count=24, r, g, b)`. The C library repeats the
same (R, G, B) triplet `count` times. Per-LED addressing could be achieved by
constructing the packet manually with different triplets per LED.

### DELED (LED Ring Reset)

Resets the LED ring to its default state (firmware-controlled rainbow animation
or off, depending on firmware version).

```
CRT + [0x44, 0x45, 0x4C, 0x45, 0x44]
       D     E     L     E     D
```

Reverse-engineered via `strace` of `transport_reset_led_color()`.

## Button Events (Reading)

Button press/release events are read from the same hidraw file descriptor using
`os.read()` or `select()` + `os.read()`.

Each HID report is up to 1024 bytes. Button data is at fixed offsets:

| Offset | Meaning                                      |
|--------|----------------------------------------------|
| 9      | Key code (0x01-0x0F for screen keys, etc.)   |
| 10     | State: `0x01` = pressed, `0x02` = released   |

Special values:
- `key_code == 0xFF`: Write confirmation echo (not a real button event, skip)

**Debounce required**: A single physical button press generates multiple HID
events in rapid succession (12+ events observed within 2 seconds). The
application layer must debounce — we use a 300ms per-key cooldown.

## Initialization Sequence

The device requires a specific initialization order to work reliably:

```
1. Open /dev/hidrawN (O_RDWR)
2. Send DIS (wake screen)
3. Send LIG (set brightness to 80)
4. Send CONNECT (initial heartbeat)
5. Send LOG + chunks + STP (background image)
6. Start heartbeat loop (every 10s)
7. Start button reader loop (select + read)
```

**Order matters**. Wake must come before brightness. The initial heartbeat must
come before image send. Skipping brightness in the init sequence causes
instability in some firmware states.

## USB Reset

If the device enters a bad state (USB I/O errors, firmware stuck in demo mode),
a USB hub reset is required:

```bash
# Reset the entire USB hub (not just the device port)
echo 0 | sudo tee /sys/bus/usb/devices/1-1/authorized
sleep 2
echo 1 | sudo tee /sys/bus/usb/devices/1-1/authorized
sleep 3
# Verify hidraw devices reappeared
ls /dev/hidraw*
```

Resetting only the device's port (e.g., `1-1.2`) often fails with
`can't set config #1, error -32`. Resetting the parent hub (`1-1`) is reliable.

## Thread Safety Model

The service runs multiple threads that access the hidraw fd:

| Thread            | Operations                          | Frequency    |
|-------------------|-------------------------------------|--------------|
| Main              | Image send (LOG+chunks+STP)         | On startup   |
| heartbeat         | CONNECT write                       | Every 10s    |
| hidraw-reader     | Button event reads (select+read)    | 100ms poll   |
| LED flash (N)     | LBLIG brightness write              | On key press |
| dashboard-poll    | (no device I/O)                     | Every 60s    |

A single `threading.Lock` (`_write_lock`) serializes all writes:

- **Single-packet commands** (heartbeat, brightness, LED): Lock acquired in
  `_raw_write()` or directly around `os.write()`.
- **Multi-packet sequences** (image send): Lock held for the entire sequence
  (header + all chunks + STP) to prevent interleaving.
- **Reads**: Not locked. `select()` + `os.read()` operates on the same fd but
  Linux hidraw handles concurrent read/write safely.

## Known Firmware Quirks

1. **Demo mode timeout**: Without periodic CONNECT heartbeats, the firmware
   reverts to a built-in demo (rainbow LEDs, cycling display) after ~30-60s.

2. **Write confirmation echoes**: Every write to the device generates a read
   event with `key_code == 0xFF`. These must be filtered out in the reader loop.

3. **USB disconnect on SDK use**: The MiraboxSpace SDK's C library
   (`libtransport.so`) causes firmware-level USB disconnects after ~60s,
   regardless of which SDK functions are called. Even just calling
   `transport.open()` is sufficient to trigger the disconnect. This appears to
   be caused by the C library's internal reader thread conflicting with the
   firmware.

4. **Stale USB state**: After a USB disconnect or strace session, the device
   may need a full USB hub reset and 3-10 second settle time before the next
   program can open it reliably.

5. **Multiple HID events per press**: Physical button presses generate 12+
   rapid-fire HID events. Application-level debouncing is required.
