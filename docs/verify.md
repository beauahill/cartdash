# VERIFY checklist

Every fact the brief marks **VERIFY**, plus a few the plan depends on. When an item is confirmed on hardware, record the answer where the last column says, in the same commit, and tick it here.

Status: `open`, `partial`, or `done`.

## Head unit (check on arrival, inside the dispute window)

| Item | How to check | Status | Record in |
|---|---|---|---|
| Chip is UIS7862S | CPU-Z | done 2026-11-23: UIS7862S, 2x Cortex-A75 and 6x Cortex-A55 at 2.0 GHz, Mali-G52 | this file |
| 8 GB RAM, 128 GB storage | CPU-Z | done: 7556 MB RAM, 106 GB usable storage | this file |
| Android version is 12 | Settings or CPU-Z. If older, lower `minSdk`. | done: reports "13", but API level 32 and build SP1A.210812.016, so it is Android 12L. `minSdk` 31 is fine; do not rely on Android 13 (API 33) behavior | this file, `android/app/build.gradle.kts` |
| Screen resolution about 2000x1200 | CPU-Z, or `adb shell wm size` | done: 2000 x 1200 | this file |
| Screen density | `adb shell wm density`, or a debug readout in the app of `densityDpi` and width and height in dp | partial: CPU-Z says 358 dpi, from which it computes a 6.52 inch screen, so it may not be the density the layout uses. At 358 the dash gets about 894 x 536 dp; at 240, about 1333 x 800 dp | this file |
| Sleeps or shuts down on ACC off | Key off, wait, key on. Does `BOOT_COMPLETED` fire? | open | this file |
| Broadcast sent on wake | `adb logcat` across a key off and on cycle | open | this file |
| CarPlay app package name | `adb shell pm list packages` | open | this file |
| Own "default desktop" setting | Head unit settings | open | this file |
| USB host sees the ESP32 with VBUS cut | Bench test with the cut cable | open | `docs/pinout.md` |
| Has a GPS receiver and an external antenna | Box contents, GPS test app | open | this file |
| Google Play services present (not required, the app uses `LocationManager`) | CPU-Z | done: present (21.30.16) | this file |
| Developer options code (needed for ADB over Wi-Fi) | Seller, manual, or common codes | open: the Factory settings code is 8888; the developer options code is not 7890, 3368, 1617, 8888, 1234, 0000, or 123456. Look for a USB debugging switch in Factory settings, or ask the seller. Not blocking: see `docs/dev_setup.md` | this file |

## Course GPS

| Item | How to check | Status | Record in |
|---|---|---|---|
| Bell Nob is on OpenStreetMap with greens and hole numbers | `tools/course_from_osm.py` report | open | `courses/README.md` |
| Gillette Golf Club, same | Same | open | `courses/README.md` |
| Casper Country Club, same | Same | open | `courses/README.md` |
| Newcastle Golf Course, same | Same | open | `courses/README.md` |
| Green outlines line up with the real greens | Stand on a green edge, compare to the drawn view | partial (they line up with the USGS photos) | this file |
| USGS aerial photos are sharp enough for the photo view | Look at each course in the photo view | open | this file |
| Gillette Golf Club: 9 or 18 holes? | Owner | done: 9 holes, the eastern expansion was abandoned | `courses/gillette-golf-club.overrides.json` |
| Bell Nob short course: wanted in the app? | Owner | done: yes | `courses/bell-nob-golf-course.overrides.json` |
| Bell Nob short course: hole numbers and name | Owner, against the routing preview | done: order as inferred, starting from the inferred hole 5; name Bell Nob Short Course | `courses/bell-nob-golf-course.overrides.json` (`numbering`, `name`) |
| Bell Nob short course: all par 3? | Owner | done: yes | same file |
| Pars for Bell Nob, Gillette Golf Club, Casper | Scorecards | done | `courses/<course>.overrides.json` |
| Bell Nob hole 1 tees south of the clubhouse | Owner | done: correct, the front 9 is south of the clubhouse | `courses/README.md` |
| Time to first fix after key on | Key on, time until accuracy is under 10 yards | open | this file |
| Yardage accuracy in open sky | Park at about 20 sprinkler heads or 150 markers, compare to their yardage | open | this file |
| Yardage accuracy under trees | Same, on tree lined holes | open | this file |
| Whether the ESP32 GNSS upgrade is needed | Decide from the two accuracy checks | open | `docs/plan.md` (G3) |

## Factory connectors and signals (meter, back-probing)

For each digital line also record: switches 12V or switches to ground, voltage, PWM or steady, and whether it comes from the Tianji or from a switch.

| Item | How to check | Status | Record in |
|---|---|---|---|
| 16 pin: hole count and wires | Look | done: 16 holes, 8 wires; colors do not match the manual | `docs/pinout.md` |
| 9 pin: hole count and wires | Look | done: 9 holes, 6 wires | `docs/pinout.md` |
| 9 pin hole 2 color | Look | done: gray/yellow | `docs/pinout.md` |
| Function of each of the 14 wires | Meter, worksheet in `docs/pinout.md` | done 2026-11-23: blinkers, headlights, forward, speed pulse, switched 12V, pack voltage, grounds; 5 wires show no signal | `docs/pinout.md` |
| Which wire is constant 12V, and is it live with the key off | Meter, key off | partial: none found at the screen plugs (2026-11-23) | `docs/pinout.md` |
| Is there constant 12V anywhere on the cart | Meter at the 12V converter output or fuse block, key off | likely none: the converter has a keyed enable (owner); confirm with a meter | `docs/plan.md` |
| Head unit cold boot time vs wake from sleep | Bench, stopwatch | done: cold boot about 30 s (repeated), wake from sleep 3 to 4 s; chose the always-on converter | `docs/plan.md` (power decision) |
| 9 pin black: 12V ground or pack negative | Volts between the two plug blacks, key on | partial: same ground as the 16 pin black (0 V); confirm with ohms, key off | `docs/pinout.md` |
| Is the 12V system isolated from the pack, or does the converter share its negative | Key off, ohms between the converter's input and output negatives; and key on, screen unplugged, volts between harness red/blue and black | done: shared. 0 ohms between the converter's input and output negatives (non-isolated); also seen at the harness with the screen unplugged | `docs/pinout.md` |
| 16 pin red: switched or constant | Meter, key off and on | done: 12 V with the key on only (switched, ACC) | `docs/pinout.md` |
| Is there a CAN pair at the screen at all | Two wires at about 2.5 V key on, 60 or 120 ohms between them key off | done: none. Candidates at millivolts key on, open circuit between pairs; they are speaker outputs | `docs/pinout.md` |
| CANH to CANL resistance, cart off (60 or 120 ohms) | Meter | open | `docs/pinout.md` |
| CAN idle voltages, key on (about 2.5 V each) | Meter | open | `docs/pinout.md` |
| Speed pulse: amplitude, push-pull or open collector, pulses per wheel turn, source | Scope or meter | partial: found on 9 pin hole 9 (yellow); amplitude, pulses per turn, and source (Tianji or sensor) still open | `docs/pinout.md` |
| Speed mode lines: driven by a switch or by the Tianji | Meter | not at the screen plugs; find at the switch in Phase 2 | `docs/pinout.md` |
| Reverse signal | Meter | not at the screen plugs (only forward, 16 pin hole 7); find at the gear rocker in Phase 2 | `docs/pinout.md` |
| Where gear D/N/R can be read | Screen plugs, Kelly, or gear rocker | partial: forward is 16 pin hole 7 (12 V in F); reverse from the rocker or the Kelly | `docs/pinout.md` |

## Factory CAN bus

| Item | How to check | Status | Record in |
|---|---|---|---|
| Factory CAN bus exists | Meter at the screen plugs | done: no, the screen uses discrete wires (2026-11-23); bitrate, IDs, and fields do not apply | `docs/pinout.md` |

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
| Board is N16R8 (16 MB quad flash, 8 MB octal PSRAM) | `pio run -t upload` boot log, or `esptool.py flash_id` | open | this file, `firmware/platformio.ini` |
| Native USB shows up as USB Serial/JTAG, VID 0x303A, PID 0x1001 (the firmware uses the built-in USB Serial/JTAG port, `ARDUINO_USB_MODE=1`) | `lsusb` on the laptop, then the head unit | open | this file, `res/xml/usb_device_filter.xml` (Phase 1) |
| Phase 0 stream: `pio device monitor` shows a `hello` and then about 10 `state` lines a second, no raw text after boot | Serial monitor on the laptop | open | `docs/plan.md` (Phase 0) |
