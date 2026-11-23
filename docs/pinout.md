# Pinout

Confirmed pins and wiring. Do not wire to anything until its row is filled in from a meter reading.

## Factory screen connectors, as found (2026-11-23)

Both are sealed connectors (a yellow rubber seal on each wire). Checked by the owner with the factory screen out. The colors below are the wires of the **screen's pigtail**: the screen-side half of each plug, whose wires run to small connectors on the screen's circuit board. The cart harness side may use other colors; what carries over is the hole each function sits in.

| Connector | Holes | Wires | Wire colors (screen side) |
|---|---|---|---|
| DJ7161Y (16 pin) | 16 | 8 | red, blue, blue/white, green, green/yellow, light blue, black, white |
| DJ7091Y (9 pin) | 9 | 6 | orange, green/yellow, pink, yellow, red/blue, black |

**Which half the new plugs must be.** The screen-side half is the one with a deep square shroud, terminals recessed inside, and a yellow comb across the face (`photos/factory-screen-9pin-face.jpg`, `photos/factory-screen-16pin-face.jpg`). The harness-side half has a flat yellow face. The plugs replacing the screen must be the screen-side kind, or they will not mate with the harness.

### Hole layout, screen side, seen from the wire side

The empty holes make each pattern lopsided, so turn the plug until its empty holes match the table. The face side is the mirror image (left and right swap). Photos: `photos/factory-screen-9pin-wire-side.jpg`, `photos/factory-screen-16pin-wire-side.jpg`, `photos/factory-screen-16pin-wire-side-2.jpg`.

9 pin:

| | Left | Middle | Right |
|---|---|---|---|
| Top | yellow | red/blue | black |
| Middle | pink | empty | empty |
| Bottom | empty | green/yellow | orange |

16 pin, latch on the right:

| | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| Top | red | empty | empty | blue |
| 2 | empty | white | empty | blue/white |
| 3 | black | empty | empty | green |
| Bottom | light blue | empty | empty | green/yellow |

When wiring a new plug, put each function's wire in the same hole the screen's wire for that function uses.

### Likely grouping (a guess from the colors, not yet measured)

The 9 pin colors look like the usual car radio power colors: yellow constant 12V, black ground, orange illumination, pink reverse, with green/yellow perhaps a speed mode line. (Red/blue turned out to be pack voltage, not ACC, and no constant 12V has been found yet, so treat this guess with care.) That is most of the manual's "16 pin" list without its speakers. If so, the 16 pin plug carries the cart signals from the manual's "9 pin" list (beams, blinkers, brakes, speed pulse, and CAN if there is one), with the two plugs' labels swapped in the manual. On the 16 pin, look for two wires twisted together as the CAN pair; a solid color with its striped partner (blue and blue/white, green and green/yellow) is a common way to code one. The meter decides.

**The manual's pin table does not match this cart.** The manual puts illumination (orange), reverse camera (pink), 12V constant (yellow), and high speed (gray) on the 16 pin plug; on this cart those colors are on the 9 pin plug. Treat the manual's functions as a list of what might be there, not where.

There are 14 wires in all. The manual lists 17 functions apart from speakers (8 on the 16 pin, 9 on the 9 pin), so at least 3 of them are not wired on this cart. One of the missing ones could be the CAN pair, so check for it before planning the capture.

## Wire identification worksheet

> **High voltage in the screen plugs.** The 9 pin red/blue wire reads 68 V with the key on (2026-11-23): that is traction pack voltage. Keep it taped and away from everything, and never connect it to the head unit, the ESP32, or anything on the 12V side.
>
> **Shared negative (likely).** Both blacks are the same ground (0 V between them), and both the 68 V and the 12 V wires measure against it, so the cart's 12V negative is very likely the pack negative. Two checks, each in one place: (1) at the 12V converter, key off, ohms between its input negative and output negative (about 0 ohms means shared, open means an isolated converter); (2) at the dash with the screen unplugged, key on, volts between the harness red/blue and black (still 68 V means the harness ties them; 0 V means the screen's board was doing it, and the bond leaves with the screen).

**What this is:** you find what each wire does by watching its voltage while you work the cart's controls.

**Setup, once**
1. Meter on DC volts. Clip the black meter lead to either black wire (they are the same ground). An alligator clip frees your hands.
2. Park brake on, a wheel chocked, foot off the accelerator the whole time.
3. Touch the red lead to one wire at a time where it enters the small connectors on the screen's board (easier than probing through the rubber seals, which can tear). One probe at a time; do not bridge neighboring pins.
4. Skip red/blue (68 V). The blacks and the 16 pin red are done.

**For each remaining wire (about a minute each)**
1. Key off: write the number.
2. Key on: write the number.
3. Watching the meter, work each control for about 2 seconds: left blinker on and off, right blinker on and off, headlights low, high, off, brake pedal press and release, park brake release and set, shift F, N, R, back to N, and the speed or mode switch if there is one.
4. If the number jumps, write which control did it and whether it went **up** (0 to 12) or **down** (12 to 0). Flashing on and off is a blinker.
5. If nothing moves it, write "nothing".

**Special cases**
- About 2 to 3 V with the key on, and nothing moves it: probably a CAN wire; note the exact number. Two of those is the CAN pair. Confirm with the key off: about 60 or 120 ohms between them.
- Last, for wires still at "nothing": roll the cart a few feet with the key on (or have someone push). A wire that flickers as the wheels turn is the speed pulse.

**Reporting:** one line per wire is plenty, for example `orange: off 0, on 0, headlights -> up to 12` or `blue: off 0, on 2.6, nothing`. A helper makes it twice as fast: one watches the meter, one works the controls.

| Plug | Wire color | Hole number | Key off (V) | Key on (V) | What makes it move | Up or down | Function | Date |
|---|---|---|---|---|---|---|---|---|
| 9 pin | orange | | | | | | | |
| 9 pin | green/yellow | | | | | | | |
| 9 pin | pink | | | | | | | |
| 9 pin | yellow | | | | | | | |
| 9 pin | red/blue | | | 68 | | | Pack voltage, key switched (likely the screen's power or "voltage detect"). **High voltage, do not use.** | 2026-11-23 |
| 9 pin | black | | | 0 to the 16 pin black | | | Ground, same as the 16 pin black (meter reference for these readings) | 2026-11-23 |
| 16 pin | red | | 0 | 12 | Key | | Switched 12V (ACC for the head unit) | 2026-11-23 |
| 16 pin | blue | | | | | | | |
| 16 pin | blue/white | | | | | | | |
| 16 pin | green | | | | | | | |
| 16 pin | green/yellow | | | | | | | |
| 16 pin | light blue | | | | | | | |
| 16 pin | black | | | 0 to the 9 pin black | | | Ground, same as the 9 pin black | 2026-11-23 |
| 16 pin | white | | | | | | | |

Hole numbers are molded, very small, into the face of each housing.

## Factory CAN bus wire check

| Check | Expected | Measured | Date |
|---|---|---|---|
| CANH to CANL resistance, cart off | about 60 ohms (both ends terminated) or 120 ohms (one end) | | |
| CANH to 12V ground, key on, idle | about 2.5 V, a bit higher with traffic | | |
| CANL to 12V ground, key on, idle | about 2.5 V, a bit lower with traffic | | |

## What the manual claims (manual p.58, reference only)

16 pin: 1 ground (black), 2 ACC (red), 3 rear camera control (pink), 4 low speed 12V active (green), 5/6 front right speaker (gray-black/gray), 7/8 front left speaker (white-black/white), 9 battery +12V constant (yellow), 10 illumination (orange), 11 high speed 12V active or voltage detect (gray), 12 camera power (blue), 13/14 rear left speaker (green-black/green), 15/16 rear right speaker (purple/purple-black).

9 pin: low beam, high beam, left turn, right turn, CANH, CANL, parking brake, pulse signal (speed), brake signal. No pin numbers or colors given.

What the ESP32 wants from these, wherever they turn out to be: ground, 12V constant, ACC, illumination, reverse, speed mode, low beam, high beam, left turn, right turn, brake, parking brake, speed pulse, and CANH/CANL for the capture.

## ESP32-S3 pin map

Lives in `firmware/include/config.h` once Phase 0 starts. Pins to avoid on an N16R8 board: GPIO 35 to 37 (octal PSRAM), 19 and 20 (USB), 26 to 32 (flash and PSRAM), and strapping pins 0, 3, 45, 46.
