# VERIFY checklist

Every fact the brief marks **VERIFY**, plus a few the plan depends on. When an item is confirmed on hardware, record the answer where the last column says, in the same commit, and tick it here.

Status: `open`, `partial`, or `done`.

## Head unit (check on arrival, inside the dispute window)

| Item | How to check | Status | Record in |
|---|---|---|---|
| Chip is UIS7862S | CPU-Z | open | this file |
| 8 GB RAM, 128 GB storage | CPU-Z | open | this file |
| Android version is 12 | Settings or CPU-Z. If older, lower `minSdk`. | open | this file, `android/app/build.gradle.kts` |
| Screen resolution about 2000x1200 | CPU-Z, or `adb shell wm size` | open | this file |
| Screen density | `adb shell wm density` (dp layout depends on it) | open | this file |
| Sleeps or shuts down on ACC off | Key off, wait, key on. Does `BOOT_COMPLETED` fire? | open | this file |
| Broadcast sent on wake | `adb logcat` across a key off and on cycle | open | this file |
| CarPlay app package name | `adb shell pm list packages` | open | this file |
| Own "default desktop" setting | Head unit settings | open | this file |
| USB host sees the ESP32 with VBUS cut | Bench test with the cut cable | open | `docs/pinout.md` |
| Has a GPS receiver and an external antenna | Box contents, GPS test app | open | this file |
| Google Play services present (not required, the app uses `LocationManager`) | Settings, apps | open | this file |

## Course GPS

| Item | How to check | Status | Record in |
|---|---|---|---|
| Bell Nob is on OpenStreetMap with greens and hole numbers | `tools/course_from_osm.py` report | open | `courses/README.md` |
| Gillette Golf Club, same | Same | open | `courses/README.md` |
| Casper Country Club, same | Same | open | `courses/README.md` |
| Newcastle Golf Course, same | Same | open | `courses/README.md` |
| Green outlines line up with the real greens | Stand on a green edge, compare to the drawn view | partial (they line up with the USGS photos) | this file |
| USGS aerial photos are sharp enough for the photo view | Look at each course in the photo view | open | this file |
| Gillette Golf Club: 9 or 18 holes? | Scorecard. OpenStreetMap has greens, tees, and fairways east of the 9 holes with no hole lines; the USGS photo shows that ground still being graded | open | `courses/README.md` |
| Bell Nob short course: wanted in the app? | It is mapped as 9 holes with no hole numbers | open | `courses/README.md` |
| Pars for Bell Nob, Gillette Golf Club, Casper | Scorecards | open | OpenStreetMap or a pars file |
| Time to first fix after key on | Key on, time until accuracy is under 10 yards | open | this file |
| Yardage accuracy in open sky | Park at about 20 sprinkler heads or 150 markers, compare to their yardage | open | this file |
| Yardage accuracy under trees | Same, on tree lined holes | open | this file |
| Whether the ESP32 GNSS upgrade is needed | Decide from the two accuracy checks | open | `docs/plan.md` (G3) |

## Factory connectors and signals (meter, back-probing)

For each digital line also record: switches 12V or switches to ground, voltage, PWM or steady, and whether it comes from the Tianji or from a switch.

| Item | How to check | Status | Record in |
|---|---|---|---|
| 16 pin: pins 1, 2, 3, 4, 9, 10, 11, 12 match the manual | Meter | open | `docs/pinout.md` |
| 9 pin: which pin is which (manual gives functions, not positions) | Meter, key on, operate each control | open | `docs/pinout.md` |
| Pin 9 is live with the key off | Meter, key off | open | `docs/pinout.md` |
| CANH to CANL resistance, cart off (60 or 120 ohms) | Meter | open | `docs/pinout.md` |
| CAN idle voltages, key on (about 2.5 V each) | Meter | open | `docs/pinout.md` |
| Speed pulse: amplitude, push-pull or open collector, pulses per wheel turn, source | Scope or meter | open | `docs/pinout.md` |
| Speed mode lines: driven by a switch or by the Tianji | Meter with the Tianji unplugged, if safe | open | `docs/pinout.md` |
| Reverse (pin 3): from the gear rocker or the Tianji | Meter | open | `docs/pinout.md` |
| Where gear D/N/R can be read | Factory CAN capture, Kelly, or gear rocker | open | `docs/protocols.md` |

## Factory CAN bus

| Item | How to check | Status | Record in |
|---|---|---|---|
| Bitrate | `can_capture.py scan` | open | `docs/protocols.md` |
| Standard or extended IDs | Capture | open | `docs/protocols.md` |
| Gear, speed or RPM, throttle, voltage, current, fault fields | Capture sessions and analyzer | open | `docs/protocols.md`, `docs/factory_can.dbc` |

## BMS

| Item | How to check | Status | Record in |
|---|---|---|---|
| Bluetooth works | JBD app connects | partial (JBD app in use) | this file |
| Protocol is JBD | nRF Connect shows service `FF00` with `FF01` and `FF02` | partial (JBD app in use) | `docs/protocols.md` |
| Whether reads need the PIN | Try reading without it | open | `docs/protocols.md` |
| Current sign and scale, temperature sensor count | Compare to the JBD app | open | `docs/protocols.md` |

## Kelly KAC7250ND

| Item | How to check | Status | Record in |
|---|---|---|---|
| Exposes CAN | Manual, connector, sniff | open | `docs/protocols.md` |
| Broadcasts on its own or only answers requests | Sniff with nothing else talking to it | open | `docs/protocols.md` |
| Bitrate and termination | Scan, and meter across CANH and CANL with power off | open | `docs/pinout.md` |
| Throttle is TPS type 1 (0 to 5 V) | Kelly software | open | `docs/protocols.md` |
| Battery current sign during regen | Sniff while coasting downhill | open | `docs/protocols.md` |
| Serial port voltage levels (fallback) | Meter, manual | open | `docs/pinout.md` |

## Drivetrain calibration

| Item | How to check | Status | Record in |
|---|---|---|---|
| Tire diameter | Tape measure, or roll out one turn | open | firmware `config.h` default |
| Gear ratio, motor to wheel | Count turns, or from capture RPM vs GPS | open | firmware `config.h` default |
| Speed source to use (pulse or Kelly RPM) | Compare both to GPS | open | firmware `config.h` default |

## ESP32 board

| Item | How to check | Status | Record in |
|---|---|---|---|
| USB VBUS is isolated from the 5V rail (or cable has VBUS cut) | Board schematic, meter | open | `docs/pinout.md` |
| Opening the port from Android does not reset the chip | Watch `uptime_s` in `hello` | open | this file |
