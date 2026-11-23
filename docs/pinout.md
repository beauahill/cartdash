# Pinout

Confirmed pins and wiring. Do not wire to anything that is not marked measured.

## Factory screen connectors (measured 2026-11-23)

Both are sealed connectors (a yellow rubber seal on each wire). The colors are the wires of the **screen's pigtail**, the screen-side half of each plug; the cart harness side may use other colors, and what carries over is the hole each function sits in. Measured by the owner with a multimeter against the black wires, factory screen plugged in. Worksheet photo: `photos/wire-worksheet-2026-11-23.jpg`.

> **High voltage: 9 pin hole 8 (red/blue) carries traction pack voltage, 68 V with the key on.** Keep it taped and away from everything. Never connect it to the head unit, the ESP32, or anything on the 12V side.
>
> **Shared negative (confirmed, 2026-11-23).** The 12V converter reads 0 ohms between its input and output negatives: it is non-isolated, so the cart's 12V negative and pack negative are the same conductor. Also seen at the harness: With the factory screen unplugged, the harness red/blue still reads 68 V to the black, so the harness itself ties that black to pack negative. The two plug blacks read 0 V apart, and the 12 V reads against the same black, so the cart's 12V system shares the pack negative.

**Which half the new plugs must be.** The screen-side half is the one with a deep square shroud, terminals recessed inside, and a yellow comb across the face (`photos/factory-screen-9pin-face.jpg`, `photos/factory-screen-16pin-face.jpg`). The harness-side half has a flat yellow face. The plugs replacing the screen must be the screen-side kind, or they will not mate with the harness. When wiring one, put each function's wire in the same hole the screen's wire for that function uses.

### 9 pin, holes seen from the back (wire side), bump at the top

| | | |
|---|---|---|
| **1** orange: left turn | **2** gray/yellow: headlights | **3** empty |
| **4** empty | **5** empty | **6** pink: right turn |
| **7** black: ground | **8** red/blue: **PACK VOLTAGE** | **9** yellow: speed pulse |

### 16 pin, holes seen from the back (wire side), bump at the top

| | | | |
|---|---|---|---|
| **1** light blue: no signal found | **2** black: ground | **3** empty | **4** red: switched 12V |
| **5** empty | **6** empty | **7** white: forward gear | **8** empty |
| **9** empty | **10** empty | **11** empty | **12** empty |
| **13** green/yellow: speaker | **14** green: speaker | **15** blue/white: speaker | **16** blue: speaker |

The face side is the mirror image (left and right swap). Photos of both sides: `photos/factory-screen-*.jpg`. These hole numbers agree with the layout worked out from the photos.

### Readings

| Plug | Hole | Wire | Key off (V) | Key on (V) | What made it move | Function |
|---|---|---|---|---|---|---|
| 9 pin | 1 | orange | 0 | 0 | Up to 12 V with the left blinker | Left turn |
| 9 pin | 2 | gray/yellow | 0.4 | 0.4 | Up to 12 V with the headlights | Headlights |
| 9 pin | 6 | pink | 0 | 0 | Up to 12 V with the right blinker | Right turn |
| 9 pin | 9 | yellow | 0 | 0.15 | Rises while the cart moves | Speed pulse (the meter shows its average) |
| 9 pin | 8 | red/blue | 7.8 | 68 | Key | Pack voltage, key switched. **Do not use.** |
| 9 pin | 7 | black | | | | Ground |
| 16 pin | 4 | red | 0 | 12 | Key | Switched 12V |
| 16 pin | 7 | white | about 0 | about 0 | Up to 12 V in Forward | Forward gear |
| 16 pin | 1 | light blue | about 0 | about 0 | Nothing | Unknown |
| 16 pin | 13 | green/yellow | about 0 | about 0 | Nothing | Speaker output, pair with 14 (open circuit: speaker disconnected) |
| 16 pin | 14 | green | about 0 | about 0 | Nothing | Speaker output, pair with 13 |
| 16 pin | 15 | blue/white | about 0 | about 0 | Nothing | Speaker output, pair with 16 (open circuit: speaker disconnected) |
| 16 pin | 16 | blue | about 0 | about 0 | Nothing | Speaker output, pair with 15 |
| 16 pin | 2 | black | | | | Ground (0 V to the 9 pin black) |

Notes from the owner and the worksheet:
- 16 pin red is joined to a yellow wire going into the screen: the factory screen runs its constant and ACC inputs together on switched 12V.
- 16 pin light blue goes to the underside of the screen. 16 pin white jumps to another connector on the screen's board.
- 9 pin red/blue showing 7.8 V with the key off is most likely leakage into a meter's high input impedance; it is 68 V with the key on.
- Controls worked for every wire: both blinkers, headlights low and high, brake pedal, park brake, shift F, N, R.

### What this means

- **No CAN bus at the screen (confirmed).** A powered CAN bus idles at about 2.5 V on both wires and shows 60 or 120 ohms of termination between them; the candidates read millivolts with the key on and open circuit between pairs. They are the screen's two speaker outputs (blue with blue/white, green with green/yellow), to speakers that are no longer connected. The factory screen gets everything it shows from its own wires: blinkers, headlights, forward gear, speed pulse, and pack voltage for its battery gauge.
- **For the ESP32, from these plugs:** left turn (9 pin 1), right turn (9 pin 6), headlights (9 pin 2), forward gear (16 pin 7), speed pulse (9 pin 9), switched 12V (16 pin 4), ground (9 pin 7, 16 pin 2).
- **Not at these plugs**, to be tapped at their switches in Phase 2: brake, park brake, high beam, reverse, speed mode.
- **Speed pulse source unknown.** If it comes from the Tianji controller it stops after the Kelly swap; Kelly RPM is the fallback.

### How to re-test a wire

Meter on DC volts, black lead on a black wire, red lead on the wire where it enters the small connectors on the screen's board (probing through the rubber seals can tear them; one probe at a time, do not bridge neighboring pins). Park brake on, a wheel chocked, foot off the accelerator. Read key off, then key on, then work each control for about 2 seconds while watching: both blinkers, headlights low, high, off, brake pedal, park brake, shift F, N, R, back to N. Write which control made the number move and whether it went up (0 to 12) or down (12 to 0). A wire still at "nothing" gets a roll of the cart: flickering as the wheels turn is a speed pulse. About 2 to 3 V steady with the key on is a CAN line.

## Factory CAN bus wire check

| Check | Expected if CAN is present | Measured | Date |
|---|---|---|---|
| Candidate pairs (16 pin 13/14, 15/16), key on | about 2.5 V each | millivolts on all four | 2026-11-23 |
| Ohms between 15 and 16, and between 13 and 14, key off | about 60 or 120 ohms | open circuit (0L) on both: speaker outputs, not CAN | 2026-11-23 |

## What the manual claims (manual p.58, reference only)

**The manual's pin table does not match this cart.** Kept only as a list of what might exist.

16 pin: 1 ground (black), 2 ACC (red), 3 rear camera control (pink), 4 low speed 12V active (green), 5/6 front right speaker (gray-black/gray), 7/8 front left speaker (white-black/white), 9 battery +12V constant (yellow), 10 illumination (orange), 11 high speed 12V active or voltage detect (gray), 12 camera power (blue), 13/14 rear left speaker (green-black/green), 15/16 rear right speaker (purple/purple-black).

9 pin: low beam, high beam, left turn, right turn, CANH, CANL, parking brake, pulse signal (speed), brake signal. No pin numbers or colors given.

## ESP32-S3 pin map

Lives in `firmware/include/config.h`. The board is a Waveshare ESP32-S3-Zero (ESP32-S3FH4R2). Pins to avoid: 19 and 20 (USB), 26 to 32 (in-package flash and PSRAM), and strapping pins 0, 3, 45, 46. GPIO 21 drives the onboard RGB LED. Take the broken-out pins from Waveshare's pinout diagram.
