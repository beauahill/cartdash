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

The 9 pin colors look like the usual car radio power colors: yellow constant 12V, black ground, orange illumination, pink reverse, with red/blue probably ACC and green/yellow perhaps a speed mode line. That is most of the manual's "16 pin" list without its speakers. If so, the 16 pin plug carries the cart signals from the manual's "9 pin" list (beams, blinkers, brakes, speed pulse, and CAN if there is one), with the two plugs' labels swapped in the manual. On the 16 pin, look for two wires twisted together as the CAN pair; a solid color with its striped partner (blue and blue/white, green and green/yellow) is a common way to code one. The meter decides.

**The manual's pin table does not match this cart.** The manual puts illumination (orange), reverse camera (pink), 12V constant (yellow), and high speed (gray) on the 16 pin plug; on this cart those colors are on the 9 pin plug. Treat the manual's functions as a list of what might be there, not where.

There are 14 wires in all. The manual lists 17 functions apart from speakers (8 on the 16 pin, 9 on the 9 pin), so at least 3 of them are not wired on this cart. One of the missing ones could be the CAN pair, so check for it before planning the capture.

## Wire identification worksheet

Fill in at the cart with a multimeter, with the factory screen plugged in. Black meter lead on 12V ground for every voltage reading. Probing through the rubber seals is hard and can tear them; with the screen's back open, it is easier to touch each wire where it enters the small connectors on the screen's board. One probe at a time, and do not bridge neighboring pins.

1. **Ground first.** Key off, meter on ohms: a wire with about 0 ohms to 12V negative is ground. There may be two (one black on each plug).
2. **Key off, volts:** 12 V now is the constant 12V feed (powers the ESP32 and the head unit memory).
3. **Key on, nothing touched:** a wire that jumps to 12 V is ACC. Two wires sitting around 2 to 3 V are probably the CAN pair; confirm with key off, ohms between them: about 60 or 120 ohms.
4. **Work the controls one at a time** and watch for a wire that changes: low beam, high beam, left blinker, right blinker (flashes between 0 and 12 V), brake pedal, parking brake, speed mode switch, shift to R.
5. **Note which way it switches.** Some lines go from 0 to 12 V when active, others drop from 12 V to 0 (switched to ground). The opto wiring differs, so record both.
6. **Speed pulse:** push the cart slowly or spin a drive wheel with it jacked up. The pulse wire flickers on a DC range and shows a changing frequency on Hz mode.
7. A wire that never changes stays unused until it is understood.

| Plug | Wire color | Hole number | Key off (V) | Key on (V) | Changes when | Switches 12V or GND | Function | Date |
|---|---|---|---|---|---|---|---|---|
| 9 pin | orange | | | | | | | |
| 9 pin | green/yellow | | | | | | | |
| 9 pin | pink | | | | | | | |
| 9 pin | yellow | | | | | | | |
| 9 pin | red/blue | | | | | | | |
| 9 pin | black | | | | | | | |
| 16 pin | red | | | | | | | |
| 16 pin | blue | | | | | | | |
| 16 pin | blue/white | | | | | | | |
| 16 pin | green | | | | | | | |
| 16 pin | green/yellow | | | | | | | |
| 16 pin | light blue | | | | | | | |
| 16 pin | black | | | | | | | |
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
