# Cart Dash execution plan

The brief is `README.md`. This file tracks the order of work, status, and decisions made along the way. Hardware unknowns are tracked in `docs/verify.md`. Ideas that are out of scope for now go in `docs/wishlist.md`.

## Decisions

| Date | Decision |
|---|---|
| 2026-11-05 | The BMS is managed with the JBD app, so its Bluetooth protocol is expected to be JBD. Still confirm the service UUIDs on the real BMS before relying on it. |
| 2026-11-05 | ACC sleep stays as the brief says: light sleep 60 s after ACC off. Reporting charge state to Home Assistant while parked moves to the wish list. |
| 2026-11-05 | The Kelly is on hand. The swap happens once the factory CAN captures are done and checked (see the gate in Track A). There is no fixed date. |
| 2026-11-05 | Factory CAN captures run on a Linux laptop with SocketCAN, so listen-only mode is enforced by the kernel driver. |
| 2026-11-05 | Raw CAN captures are committed under `captures/` as gzip files. The factory bus captures cannot be redone after the swap, so git is their backup. |
| 2026-11-05 | The USB protocol has one written spec (`docs/usb_protocol.md`), a JSON schema, and sample lines in `protocol/`. The tools, the firmware tests, and the app tests all check against the same samples. |
| 2026-11-05 | Course maps with front, center, and back yardage are a primary feature (Track G). It is app only: GPS from the head unit's receiver, course data from OpenStreetMap stored on the head unit. |
| 2026-11-05 | Courses: Bell Nob (Gillette), Gillette Golf Club (Gillette), Casper Country Club (Casper), Newcastle Golf Course (Newcastle). |
| 2026-11-05 | The course screen has two views: holes drawn as shapes, and an aerial photo view. Photos are USGS NAIP aerial imagery, which is public domain and so can be stored on the head unit with no account or license terms. |
| 2026-11-05 | 3 to 5 yards of accuracy is good enough. The head unit's GPS is the plan; a GNSS module on the ESP32 only if on-course checks come out worse than that. |

## Hardware status

- [ ] Head unit (ordered). On arrival, run the checks in `docs/verify.md` while it can still be disputed.
- [ ] Mating connectors: DJ7161Y-2.3-11 (16 pin), DJ7091Y-2.3-11 (9 pin), DJ613-2.3A terminals. Order now, they usually ship from China. Not needed for the CAN capture (back-probing), needed for Phase 2.
- [ ] Isolated CANable 2.0 or other candleLight adapter, flashed with candleLight firmware so Linux sees it as `can0` through the `gs_usb` driver.
- [ ] ESP32-S3 N16R8 board, PC817 and 6N137 optos, small 12V to 5V buck.
- [ ] Isolated CAN transceiver for the ESP32 to Kelly link. An ADM3053 module is simplest because it makes its own isolated supply. An ISO1050 needs a separate isolated 5V on the bus side.
- [x] Kelly KAC7250ND on hand.

## Build environment

Cloud sessions cannot reach the PlatformIO registry, GitHub downloads, or `dl.google.com` (Android SDK and Google Maven), so firmware and Android builds run on the Linux laptop. Two ways to let Claude build:

1. Run a Claude Code session on the laptop (Claude desktop app, or `claude remote-control` in a terminal inside the repo).
2. Or allow these hosts in the cloud environment's network settings: `dl.google.com`, `api.registry.platformio.org`, `dl.registry.platformio.org`, `github.com`, `objects.githubusercontent.com`.

The Python tools need only PyPI, which already works. Course files need the OpenStreetMap Overpass API (`overpass-api.de`) and aerial photos need the USGS imagery services (`basemap.nationalmap.gov`, `imagery.nationalmap.gov`). Cloud sessions cannot reach those either, so run the course tools on the laptop or allow those hosts too.

## Order of work

### Step 0: Repo foundation
- [x] Brief, `.gitignore`, docs skeleton (`pinout.md`, `protocols.md`, `verify.md`, `wishlist.md`, this plan).
- [x] USB protocol spec, schema, and sample lines.
- [x] CI for the Python tools. Firmware and Android jobs get added with Phase 0.

### Track A: Factory CAN capture (before the Kelly swap)
- [x] `tools/can_capture.py` and `tools/can_log_analyze.py`, tested against synthetic captures. Usage is in `tools/README.md`.
- [ ] Bench check: plug in the CANable, run `can_capture.py check` and `can_capture.py setup`.
- [ ] Meter checks from the brief (CANH to CANL resistance, idle voltages). For every digital line on both factory plugs also record: does it switch 12V or switch to ground, its voltage, whether it is PWM, and whether it comes from the Tianji or from a switch. Lines that come from the Tianji (speed pulse, speed mode, maybe reverse) disappear after the swap just like its CAN traffic.
- [ ] Bitrate scan (`can_capture.py scan`).
- [ ] The six capture sessions from the brief. Film the factory screen during each one with a clock in frame. Log phone GPS during session 5. Type DROK readings as markers (`v=66.4 a=-48`) during sessions 3 and 5.
- [ ] **Gate before the swap:** run the analyzer on every session and confirm the bitrate is right, every capture has traffic, and the markers line up with byte changes. Commit the captures.
- [ ] Write findings to `docs/protocols.md` and `docs/factory_can.dbc`.

### Phase 0: Both sides on fake data
Firmware:
- Pin the PlatformIO platform and Arduino core version. The TWAI, PCNT, and sleep APIs differ between core 2.x and 3.x.
- One FreeRTOS task per job: USB send (highest priority), USB commands, simulator, and later BLE, CAN, WiFi/MQTT, and inputs.
- Shared state is one struct behind a mutex with a timestamp per field. The USB task copies it under the lock and builds JSON outside the lock. Staleness is decided at send time, so every data source gets it for free.
- The simulator drops fields now and then so the app's `--` path gets used from day one. It stays selectable at runtime (`set_config sim`) for bench tests.
- Config is stored in NVS and written by `set_config`.
- N16R8 pin map: avoid GPIO 35 to 37 (octal PSRAM), 19 and 20 (USB), and strapping pins 0, 3, 45, 46.
- Native unit tests: JSON output against `protocol/fixtures`, staleness, blinker latch, speed math, and later each decoder.

Android:
- Compose, minSdk 31, kotlinx.serialization with `ignoreUnknownKeys`. Lines that are not JSON objects are skipped (the ESP32 ROM prints plain text at reset).
- Stale and missing fields become `null` in the data layer, so the UI has one way to show `--`.
- Link status comes from a 1 s timer on received lines, not from the connection state.
- `SimSource`, `TcpSource` (10.0.2.2:5555 from the emulator), and `tools/fake_esp.py`.
- Build the dash in an emulator profile with the head unit's real resolution and density (`adb shell wm density`). Heavy font with tabular digits so numbers do not jitter, and a small dead band on displayed speed.

Done when the emulator shows the dash on fake data and the ESP32 streams simulated JSON in a serial monitor.

### Phase 1: Real link on the head unit
- The ESP32-S3 built-in USB port resets the chip on some DTR/RTS changes. The app sets both lines explicitly after opening the port. Watch `uptime_s` in `hello` to catch unexpected resets.
- ESP32 USB writes use a short timeout so a host that stops reading cannot stall the firmware.
- usb-serial-for-android may need a custom probe table entry for VID 0x303A and the PID the firmware reports.
- Confirm the ESP32 still enumerates with VBUS cut, on the bench first.
- The USB attach intent filter goes on a small invisible activity that pokes `LinkService` and closes. If it sits on the dash activity, every replug pulls the dash over CarPlay.
- `LinkService`: foreground service of type `connectedDevice`, sticky, reconnects with backoff. Started on boot, on launch, on USB attach, and on the head unit's wake broadcast.
- Many UIS7862 units sleep on ACC off instead of shutting down, so `BOOT_COMPLETED` only fires on a cold boot. Capture `adb logcat` across a key off and on cycle to find the wake broadcast.
- Launcher activity: `singleTask`, landscape, keeps the screen on, back does nothing.
- Test: replug, ESP32 reset, head unit sleep and cold boot, ESP32 sleep and wake, reconnect while CarPlay is in front. Then an overnight run that counts `seq` gaps.

### Phase 2: Digital inputs
- Wire each opto for how its line switches (12V or ground). Filter PWM lines.
- Inputs are active low with pull-ups, so a cut wire reads as off.
- Scope the speed pulse before picking parts. The 6N137 needs a 5V supply; pull its open collector output up to 3.3V, never 5V. Count with PCNT and its glitch filter. Calibrate against GPS.
- ACC off for 60 s goes to light sleep with ACC as the wake source, after one final MQTT publish.

### Phase 3: BMS over BLE (JBD)
- Confirm with nRF Connect on a phone that the BMS shows the JBD service (`FF00`, notify `FF01`, write `FF02`) before writing firmware. Notes are in `docs/protocols.md`.
- NimBLE-Arduino, which is much lighter than Bluedroid.
- WiFi and BLE share one radio. Back off WiFi reconnect attempts while home WiFi is not in range.
- If no BMS data arrives for a few seconds, drop the connection and reconnect.

### Phase 4: Kelly decode
- Look for Kelly's CAN protocol document for the KAC-N series first. Some Kelly controllers broadcast status frames, others only answer requests. If this one only answers, listen-only sniffing shows a silent bus and the ESP32 has to send requests on the Kelly bus. That is allowed; the no-transmit rule is for the factory bus.
- The isolated side ground of the transceiver goes only to the Kelly CAN ground. Check whether the Kelly already terminates the bus before adding 120 ohms.
- The ESP32 has one CAN controller, so it sits on the Kelly bus only.
- Serial fallback uses RS232 levels and needs an isolated RS232 transceiver. It probably shares the port with the Kelly Bluetooth adapter.
- Gear source: decide from the factory capture. After the swap the gear rocker likely wires to the Kelly direction inputs, so the Kelly may report it.
- Regen warning: Kelly battery current in the charge direction while pack voltage is above 71 V. Until the Kelly is decoded, use BMS charge current while speed is above 2 mph (charge current while parked is the charger).

### Phase 5: Home Assistant
- MQTT discovery, retained state, availability topic, 1 Hz while ACC is on and home WiFi is connected. Final publish before sleep.
- Needs no cart hardware, so it can be built against simulated data whenever convenient.

### Track G: Course GPS (app only, alongside the hardware phases)

Starts once the Phase 0 app exists. Nothing here needs cart hardware until G3.

G1, course data:
- [x] `tools/course_from_osm.py`: query OpenStreetMap for a course, write `courses/<name>.geojson`, and report each hole as ok, NO GREEN, or MISSING, with sanity checks on green depth, green size, and length for the par. First live run on 2026-11-06 (from the laptop; Overpass refuses cloud sessions even with the host allowed).
- [x] Course file format: `docs/course_format.md`. Yardage reference: `tools/courselib.py`.
- [x] Build and check each course (`courses/README.md` tracks them). All 54 mapped holes are ready for yardage:
  - [x] Bell Nob, Gillette: 18 of 18. Mapped lengths match the scorecard's Black tees within 3%, except hole 10.
  - [x] Bell Nob Short Course: 9 of 9, all par 3, built from the unnumbered holes inside Bell Nob's boundary. The inferred routing was right but started at the wrong hole; numbering confirmed by the owner and recorded in the overrides file.
  - [x] Gillette Golf Club, Gillette: 9 of 9. Its abandoned eastern expansion is excluded in the overrides file.
  - [x] Casper Country Club, Casper: 18 of 18.
  - [x] Newcastle Country Club, Newcastle: 9 of 9.
- [x] Scorecards: pars, handicaps, and tee yardages for Bell Nob, Casper, and Gillette Golf Club in `courses/<course>.overrides.json`. Newcastle's pars come from OpenStreetMap. The short course is par 3 throughout.
- [x] `tools/course_preview.py` draws a course and each hole as PNGs, on the drawn shapes or the photo, to check data by eye.
- [ ] Fix gaps by tracing in the OpenStreetMap editor (iD), whose satellite layers are licensed for tracing. Those satellite images cannot be downloaded for the app, which is why the photo view uses USGS imagery.
- [x] `tools/course_imagery.py`: one JPEG per course from the USGS NAIP image service, cut to the course boundary plus 40 m, with a sidecar giving its bounds (`docs/course_format.md`). The USGS basemap tiles stop at zoom 16 (about 1.7 m per pixel here), too coarse, so it uses the NAIP export service at 0.5 m per pixel instead. That service grows any asked area until its pixels are square in degrees, which squashed the first photos by up to 100 m; the tool now asks for square degree pixels, reads back the extent the service really returned, and resamples onto the grid. A test with dots at known spots near chunk edges guards it. A green 25 to 30 m across is about 50 pixels: fine as a background, soft up close. Mapped green outlines line up with the greens in the photos. NAIP is flown every two to three years, so new construction can be missing (Gillette Golf Club's east side). If NAIP looks too soft, sharper commercial imagery needs an account and that vendor's SDK for offline use.

G2, yardage engine and course screen (emulator):
- `Yardage.kt`, pure Kotlin with unit tests:
  - Local flat projection around each green (error is negligible at golf distances). Meters to yards is times 1.09361.
  - Center is the middle of the green outline.
  - Front and back are where the line from the cart through the center crosses the green edge, nearest and farthest. Fixed points in the course file win.
  - Current hole: nearest hole line, plus moving on once the cart leaves a green toward the next tee. Manual previous and next always override.
  - Smoothing, plus averaging every fix while the ESP32 reports speed 0, so numbers hold still when parked by the ball.
  - Accuracy gate: dim the numbers and show the accuracy when it is worse than about 10 yards.
- `LocationSource` with `ReplayLocation`: replays GPX tracks, or drives a simulated round along each hole's line of play, so the emulator shows real course data moving.
- `CourseScreen`: hole drawn tee at the bottom and green at the top, cart dot, huge front, center, back numbers, hole and par, previous and next buttons, a compact strip with speed, SOC, blinkers, and warnings. Readable in sun: thick shapes, high contrast colors, no thin lines.
- Two views with a toggle that is remembered: **Drawn** (shapes from the course file) and **Photo** (the aerial photo, rotated the same way, with the green outline, cart dot, and yardage drawn on top). Photo view falls back to Drawn when a course has no imagery file.
- The course screen appears automatically inside a course boundary. The overlay shows center yardage over CarPlay.

G3, on the real head unit:
- [ ] Confirm the head unit has GPS and where its antenna goes (under the roof, clear sky view; the plastic roof does not block GPS).
- [ ] Time to first fix after key on (the unit sleeps, so it should be a warm start).
- [ ] Accuracy: park at about 20 sprinkler heads or 150 yard markers with known yardage to center and record the error in `docs/verify.md`. Typical head unit GPS is within 3 to 5 yards in open sky; trees make it worse.
- [ ] Target is 3 to 5 yards. Only if it comes out worse: add a dual band (L1 and L5) GNSS module to the ESP32 on a spare UART, send `lat`, `lon`, and `gps_acc_m` as new optional `state` fields (no protocol version change), and add an `EspGnss` location source.

### Phase 6: Android polish
- Overlay: a Compose view in an overlay window needs its lifecycle and saved state owners set by hand. Confirm on the real unit that it draws over the CarPlay app.
- Speed calibration: with GPS available, the app can compare GPS speed to the reported speed on a straight run and suggest the tire diameter or gear ratio.
- CarPlay app picker: Android 11 and later need a `<queries>` entry for launcher intents, or the app list comes back nearly empty.
- Trips are computed in `LinkService`, not the UI. Skip gaps longer than 1 s. Save about every 10 s. Range estimate is SOC times about 8.3 kWh divided by recent Wh per mile.
- Test day and night themes outside in direct sun. A light background often reads better on a glossy screen than a dark one.
