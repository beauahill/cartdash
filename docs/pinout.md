# Pinout

Confirmed pins and wiring. Everything starts as the manual's claim (manual p.58) and gets a date and a measured value once checked with a meter. Do not wire to a pin until its row says verified.

## Factory 16 pin connector (DJ7161Y-2.3-11)

| Pin | Function (manual) | Color (manual) | Use | Switches 12V or GND | Measured | Source | Verified |
|---|---|---|---|---|---|---|---|
| 1 | Ground | Black | 12V ground reference | n/a | | | no |
| 2 | ACC | Red | Wake signal (opto), head unit ACC | | | | no |
| 3 | Rear camera control | Pink | Reverse indicator (opto), head unit reverse trigger | | | | no |
| 4 | Low speed 12V active | Green | Speed mode indicator (opto) | | | | no |
| 5 / 6 | FR- / FR+ | Gray-Black / Gray | Not used | | | | n/a |
| 7 / 8 | FL- / FL+ | White-Black / White | Not used | | | | n/a |
| 9 | Battery +12V constant | Yellow | ESP32 power, head unit constant | n/a | | | no |
| 10 | Illumination | Orange | Headlight on, night theme (opto) | | | | no |
| 11 | High speed 12V active / voltage detect | Gray | Speed mode indicator (opto) | | | | no |
| 12 | Camera power | Blue | Camera, not used by ESP32 | | | | no |
| 13 / 14 | RL- / RL+ | Green-Black / Green | Not used | | | | n/a |
| 15 / 16 | RR+ / RR- | Purple / Purple-Black | Not used | | | | n/a |

## Factory 9 pin connector (DJ7091Y-2.3-11)

The manual lists the functions but not which pin carries each one.

| Pin | Function | Color | Switches 12V or GND | Measured | Source | Verified |
|---|---|---|---|---|---|---|
| ? | Low beam | | | | | no |
| ? | High beam | | | | | no |
| ? | Left turn | | | | | no |
| ? | Right turn | | | | | no |
| ? | CANH | | n/a | | | no |
| ? | CANL | | n/a | | | no |
| ? | Parking brake | | | | | no |
| ? | Pulse signal (speed) | | | | | no |
| ? | Brake signal | | | | | no |

## Factory CAN bus wire check

| Check | Expected | Measured | Date |
|---|---|---|---|
| CANH to CANL resistance, cart off | about 60 ohms (both ends terminated) or 120 ohms (one end) | | |
| CANH to 12V ground, key on, idle | about 2.5 V, a bit higher with traffic | | |
| CANL to 12V ground, key on, idle | about 2.5 V, a bit lower with traffic | | |

## ESP32-S3 pin map

Lives in `firmware/include/config.h` once Phase 0 starts. Pins to avoid on an N16R8 board: GPIO 35 to 37 (octal PSRAM), 19 and 20 (USB), 26 to 32 (flash and PSRAM), and strapping pins 0, 3, 45, 46.
