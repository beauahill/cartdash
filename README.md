# Cart Dash: ESP32 data hub + native Android dashboard

Custom dashboard for a Sdlool GC22S electric golf cart. An always-on ESP32 reads every cart signal (motor controller, BMS, lights, brakes, speed) and streams it over USB serial to an Android head unit in the dash. A native Kotlin app on the head unit runs as the home launcher and draws the dashboard, alongside CarPlay. On the golf course the same app shows a map of the current hole and GPS yardage to the front, center, and back of the green. The ESP32 also publishes to Home Assistant over MQTT when the cart is in range of home WiFi.

This file is the project brief. Read it fully before writing code. Facts marked **VERIFY** came from a generic manufacturer manual or seller listing and must be confirmed on the real hardware before code depends on them.

## Goals

1. Show speed, battery state, power, temps, gear, blinkers, lights, and brake status on a 10" 2K screen (about 2000x1200, **VERIFY**) that is readable in direct sun.
2. Work anywhere with no internet, no WiFi, and no Home Assistant.
3. Boot straight into the dashboard. No kiosk apps, no browser, no manual steps after key on.
4. Publish data to Home Assistant over MQTT whenever the cart is home (mainly charge state and SOC).
5. Be buildable in phases. Both the firmware and the app must run on simulated data before any cart hardware is connected.
6. On a golf course, show the current hole and yardage from the cart to the front, center, and back of the green, using GPS and course data stored on the head unit. This is a primary feature, and like the rest of the dash it works with no internet.

## Architecture

```
 Kelly KAC7250ND ──(CAN or serial, isolated)──┐
 BMS (Bluetooth LE) ──────────────────────────┤
 Factory 12V signals ──(PC817 optos)──────────┼──> ESP32-S3 ──USB serial──> Android head unit
 Speed pulse ──(fast opto)────────────────────┘        │                  (Kotlin launcher app)
                                                       │                           ▲
                                                       │      Head unit GPS ───────┘ (course yardage)
                                                       └──WiFi STA──> MQTT ──> Home Assistant
```

Split of responsibilities:

- **ESP32 firmware**: owns all hardware. Reads, decodes, timestamps, and streams cart state. Knows nothing about the UI.
- **Android app**: owns all presentation and user features. Dashboard, course map and yardage, trip data, settings, CarPlay launching, screen dimming, overlay. Treats the ESP32 as a data source behind an interface, and reads GPS from the head unit's own receiver behind a second interface.
- **MQTT**: ESP32 only, best effort, never blocks anything else.

USB is the primary link because wireless CarPlay uses the head unit's WiFi radio. Do not design anything that needs the head unit on WiFi.

## Hardware

| Part | Notes |
|---|---|
| ESP32-S3 dev board (N16R8 or similar) | Native USB (CDC ACM), WiFi, BLE, one TWAI (CAN) controller |
| Isolated CAN transceiver (ISO1050 or ADM3053 module) | Required for the Kelly side. See electrical rules. |
| Isolated USB to CAN adapter (CANable 2.0 or other candleLight/gs_usb, isolated version) | Laptop sniffing tool for the factory bus and later the Kelly. Works with SocketCAN, python-can, and SavvyCAN. |
| PC817 opto isolators | One per 12V digital input |
| 6N137 fast opto | Speed pulse input |
| 12V to 5V buck, small | Powers ESP32 from constant 12V |
| Head unit: Topway TS10s, 10", 2K QLED, 8GB/128GB, Android 12, UIS7862S | **VERIFY** chip, RAM, Android version, and screen resolution with CPU-Z on arrival. Includes RCA outs, reverse camera input, 2 USB cables. **VERIFY** it has a built-in GPS receiver with an external antenna. |

## Electrical rules (do not violate)

- The cart has two separate systems: a 60V LiFePO4 traction pack and a 12V accessory system made by buck converters. Treat them as isolated. Never connect 12V ground to 60V negative, and never bond anything to the cart frame. The frame is not bonded to either system.
- The Kelly controller lives on the 60V side. Any connection to it (CAN or serial) must go through an isolated transceiver or isolator. No shared ground between the ESP32 and the Kelly.
- Every 12V input goes through an opto isolator. No 12V line connects directly to an ESP32 GPIO.
- The ESP32 is powered from its own 12V to 5V buck, not from the head unit. Do not connect the head unit's USB VBUS to the ESP32's 5V rail. Use a USB cable or adapter with VBUS cut, or a board where USB VBUS is diode isolated, so neither side backfeeds the other. Data lines and ground only.
- All inputs default to a safe state (off) if a wire is disconnected.

## Cart facts

### Battery
- 20S LiFePO4, 130Ah, 64V nominal, about 73V full, 200A discharge BMS
- Separate charge port. Seller doc says 100A max charge.
- The BMS is Bluetooth only. It is not on any CAN bus, so all battery data comes over BLE. **VERIFY** the Bluetooth works and identify the protocol (JBD, JK, Daly, or other). The BMS PIN lives in `secrets.h`, never in tracked files.
- A DROK 200A shunt sits on the main negative. It does not see charge current. Prefer BMS data for SOC.

### Motor
VCTech IM150139BY, AC induction, 60V, 3.5kW rated, 98A rated, 3000 rpm at 102 Hz, 4 pole, 48 ppr A/B quadrature encoder, S2-60min duty.

### Motor controller
Kelly KAC7250ND, 48 to 72V, 360A peak, 190A continuous. Throttle is TPS type 1 (0 to 5V) **VERIFY**. Ships with a Bluetooth adapter and USB-RS232 cable for Kelly's own software.
- Data protocol is undocumented. **VERIFY** whether this unit exposes CAN. If not, the fallback is its serial comm port.
- The Kelly Bluetooth adapter likely accepts only one connection. Neither the ESP32 nor the app should depend on it.
- Regen warning: the BMS has a separate charge port, so regen entering the main leads has no BMS overcharge protection. The app shows a visible warning if regen current is detected while pack voltage is above 71V.

### Factory screen connectors (from manual p.58, **VERIFY** every pin with a meter)

The factory screen (Melis OS) is being removed. It connected through two plugs. Mating connectors are DJ7161Y-2.3-11 (16 pin) and DJ7091Y-2.3-11 (9 pin) with DJ613-2.3A terminals. The build uses mating plugs so nothing in the factory harness is cut.

16 pin:

| Pin | Function | Color (manual) | Use |
|---|---|---|---|
| 1 | Ground | Black | 12V ground reference |
| 2 | ACC | Red | Wake signal (opto), head unit ACC |
| 3 | Rear camera control | Pink | Reverse indicator (opto), head unit reverse trigger |
| 4 | Low speed 12V active | Green | Speed mode indicator (opto) |
| 5 / 6 | FR- / FR+ | Gray-Black / Gray | Not used |
| 7 / 8 | FL- / FL+ | White-Black / White | Not used |
| 9 | Battery +12V constant | Yellow | ESP32 power, head unit constant |
| 10 | Illumination | Orange | Headlight on, triggers night theme (opto) |
| 11 | High speed 12V active / voltage detect | Gray | Speed mode indicator (opto) |
| 12 | Camera power | Blue | Camera, not used by ESP32 |
| 13 / 14 | RL- / RL+ | Green-Black / Green | Not used |
| 15 / 16 | RR+ / RR- | Purple / Purple-Black | Not used |

9 pin: low beam, high beam, left turn, right turn, CANH, CANL, parking brake, pulse signal (speed), brake signal. All digital lines go through optos.

The factory CAN bus most likely carries only the original Tianji controller talking to the factory screen. The new BMS is not on it. Once the Tianji is replaced by the Kelly, this bus will probably go quiet, which is why it gets captured first (see Factory CAN capture below).

Gear D/N is not on either connector. It may be on CAN, readable from the Kelly, or need a tap at the gear rocker. **VERIFY**.

## USB link protocol

ESP32-S3 native USB as CDC ACM. Newline delimited JSON, one object per line, UTF-8.

ESP32 to app, about 10 Hz:

```json
{"type":"state","seq":1042,"t":1234567,
 "speed_mph":14.2,"gear":"D","speed_mode":"high",
 "soc_pct":82,"pack_v":66.4,"pack_a":-48.5,"power_kw":-3.2,
 "cell_v_min":3.311,"cell_v_max":3.324,"bms_temp_f":[78,80],
 "ctrl_temp_f":104,"motor_temp_f":121,"motor_rpm":2210,
 "turn_left":false,"turn_right":true,"low_beam":true,"high_beam":false,
 "brake":false,"park_brake":false,"reverse":false,"illum":true,
 "kelly_faults":[],"bms_faults":[],
 "stale":["motor_temp_f"]}
```

ESP32 to app, on change or once a second: `{"type":"hello","fw":"0.1.0","uptime_s":120}` so the app knows the link is alive even if no data changes.

App to ESP32, rare commands: `{"type":"cmd","cmd":"set_config","key":"wheel_dia_in","value":22.0}`, `{"type":"cmd","cmd":"can_log","on":true}`.

Rules:
- Every field has a source timestamp on the ESP32. A field older than 2 seconds is listed in `stale` and the app shows `--` for it.
- Negative current means discharge. Units are imperial (mph, F).
- The app treats more than 1 second without any line as link lost and shows that clearly.
- Unknown fields are ignored on both sides so firmware and app can be updated independently.
- Debug logging from the ESP32 goes out as `{"type":"log",...}` lines, never raw text, so the stream always parses.

Speed has two possible sources: the factory pulse line and Kelly motor RPM. Keep both, with a config value for which one is used. Gear ratio and tire diameter are unknown, so they are config values with placeholder defaults.

## Repo layout

```
firmware/                     PlatformIO, Arduino framework
  platformio.ini
  include/
    config.h                  pin map, constants, calibration defaults
    secrets.example.h         template, copy to secrets.h (gitignored)
  src/
    main.cpp
    state.h / state.cpp       shared state, timestamps, staleness
    inputs.cpp                optos, debounce, ACC wake, speed pulse (PCNT)
    bms_ble.cpp               BLE client, protocol decoders
    can_bus.cpp               TWAI driver, raw logger, decoders
    usb_link.cpp              JSON stream out, command parser in
    mqtt.cpp                  HA publishing with discovery, STA only
    sim.cpp                   simulated data source
  test/                       decoder unit tests
android/                      Gradle project, Kotlin, Jetpack Compose
  app/src/main/
    AndroidManifest.xml
    java/.../
      data/
        CartState.kt          data model matching the JSON
        DataSource.kt         interface: Flow<CartState>, link status, send(cmd)
        UsbSerialSource.kt    real link via usb-serial-for-android
        TcpSource.kt          dev link to tools/fake_esp.py
        SimSource.kt          in-app simulator
      service/
        LinkService.kt        foreground service holding the connection
      ui/
        DashScreen.kt
        CourseScreen.kt       hole map and front, center, back yardage
        SettingsScreen.kt
        Overlay.kt            mini bar shown over CarPlay
        theme/                day and night themes
      location/
        LocationSource.kt     interface: Flow<Fix> with accuracy
        HeadUnitGps.kt        Android LocationManager, no Google Play dependency
        ReplayLocation.kt     GPX replay and simulated rounds for the emulator
      course/
        Course.kt             course, hole, green, hazard model
        CourseStore.kt        loads course files from local storage
        Yardage.kt            hole detection, front/center/back, smoothing (pure Kotlin)
      trips/                  trip odometer and energy, Room or DataStore
    res/xml/usb_device_filter.xml
courses/                      course files (GeoJSON), one per course
tools/
  fake_esp.py                 emits the same JSON over TCP or a virtual serial port
  course_from_osm.py          builds a course file from OpenStreetMap and reports gaps
  can_capture.py              labeled, listen-only CAN captures with keyboard markers
  can_log_analyze.py          finds changing bytes in raw CAN logs, aligned to markers
docs/
  pinout.md                   verified pinout, updated as pins are confirmed
  protocols.md                decoded BMS, Kelly, and factory CAN notes
  factory_can.dbc             decoded factory bus messages
```

## Android app requirements

- Kotlin, Jetpack Compose, minSdk 31 (head unit should be Android 12, **VERIFY**; lower minSdk if it turns out older). Sideloaded APK, no Play Store.
- Registers as a home launcher (HOME and DEFAULT intent categories) so the unit boots into the dash.
- Starts `LinkService` as a foreground service on boot and on launch. The service owns the data source and exposes state as a StateFlow. Cheap head unit firmware kills background apps aggressively, so the service must survive and reconnect on its own.
- USB: use the usb-serial-for-android library. Register a USB device attached intent filter for the ESP32-S3 (Espressif VID 0x303A) so permission is granted automatically and the link reconnects after unplug or sleep.
- Data source is chosen in settings: USB (default), TCP (emulator dev, host 10.0.2.2), or Sim.
- Dashboard layout: landscape, built in dp so it scales to the real resolution (2K, about 2000x1200, **VERIFY**), touch, no scrolling on the main view. Very large speed and SOC numerals, high contrast, no thin fonts. Big blinker arrows. Banners for regen warning, BMS faults, Kelly faults, and link lost.
- Night theme follows the `illum` signal with a manual override. Screen brightness can be lowered at the window level inside the app. System wide brightness needs WRITE_SETTINGS, which is optional.
- CarPlay button launches the head unit's CarPlay app. The package name differs by firmware, so it is a setting with a picker that lists installed apps.
- Overlay: optional small strip (speed, SOC, blinkers, and center yardage while on a course) drawn over other apps using SYSTEM_ALERT_WINDOW, so it shows on top of CarPlay.
- Trips: odometer, energy used (Wh), Wh per mile, and a simple range estimate, stored locally and resettable.
- Settings: data source, CarPlay package, wheel diameter, gear ratio, speed source, theme override, overlay on or off, location source, installed courses.

## Course GPS requirements

- **Position** comes from the head unit's GPS through `LocationSource`, using Android `LocationManager` directly so nothing depends on Google Play services. Mount the GPS antenna under the cart roof with a clear view of the sky, not in the dash. If the head unit is not accurate enough on the course (**VERIFY**), the upgrade path is a dual band GNSS module on the ESP32 that sends its position over USB as extra `state` fields.
- **Course data** lives on the head unit as one GeoJSON file per course, so yardage works with no internet. Each hole needs at least a green outline and a hole number. A tee and the hole's line of play (tee to green) improve hole detection and the map. Fairways, bunkers, and water are drawn when present.
- **Where course data comes from**: OpenStreetMap, which maps golf courses with `golf=hole`, `golf=green`, `golf=tee`, `golf=fairway`, `golf=bunker`, and water tags. `tools/course_from_osm.py` builds a course file on a laptop and reports which holes are missing a green or a number. Fix gaps by tracing in the OpenStreetMap editor (its satellite layers are licensed for tracing), then build the file again. Load courses onto the head unit by USB drive or ADB. The course screen shows "© OpenStreetMap contributors".
- **Yardage**: center is the middle of the green outline. Front and back are where the line from the cart through the green center crosses the edge of the green, nearest and farthest, so they stay right when approaching from an angle. If a course file gives fixed front, center, or back points, those win. Show whole yards of horizontal distance.
- **Steady numbers**: smooth the position. While the ESP32 reports the cart stopped, average every fix since it stopped. When GPS accuracy is worse than about 10 yards, dim the numbers and show the accuracy.
- **Current hole**: chosen automatically from position, with large previous and next buttons to override.
- **Course screen**: landscape, touch, no scrolling. The hole is drawn as vector shapes, rotated so the tee is at the bottom and the green at the top, with the cart as a dot. Front, center, and back yardage are the largest numbers on the screen, with hole number and par. A compact strip keeps speed, SOC, blinkers, and warning banners visible.
- **Switching**: the course screen shows automatically while the cart is inside a known course boundary, and the drive dash otherwise, with a manual toggle.
- Yardage math is pure Kotlin with unit tests. On the course, check it against sprinkler head and 150 yard marker distances.

## ESP32 firmware requirements

- Nothing blocks the main loop. BLE, CAN, WiFi, MQTT, and USB run in their own FreeRTOS tasks and write to shared state behind a mutex.
- Task watchdog enabled. A hung BLE stack must not stop the USB stream.
- Every pin, constant, and calibration value lives in `config.h`. No magic numbers in source files.
- Blinkers report a steady "flashing" state (true if toggled within the last 1.2 s), not each flash.
- ACC off for 60 s puts the ESP32 in light sleep with ACC as the wake source. MQTT gets one final state publish before sleep so HA has the last SOC.
- Decoders are pure functions with unit tests where practical.

## Factory CAN capture (time sensitive, do before the Kelly swap)

Goal: learn what the original Tianji controller sent to the factory screen, especially gear (D/N/R), speed, and any fault or mode signals, before the Tianji is removed. This runs on a laptop and is independent of the firmware and app work. It can happen in parallel with Phase 0.

### Wire check (manual, with a meter)
- Cart off: resistance between CANH and CANL should be about 60 ohms (terminated at both ends) or about 120 ohms (one terminator). Record which.
- Key on: both lines idle near 2.5V. With traffic, CANH reads slightly higher and CANL slightly lower on a DC meter.
- Record confirmed pins in `docs/pinout.md`.

### Connection rules
- Back-probe the 9 pin connector with the factory screen still plugged in, so the bus stays live and terminated.
- Isolated USB to CAN adapter only. Laptop on battery, not on its charger.
- Listen-only mode always. Nothing in this project transmits on the factory bus.
- Bitrate is unknown. Try 250k first, then 500k, 125k, 1M. A wrong rate shows as error frames or silence.

### Capture sessions
`tools/can_capture.py` (python-can) records to timestamped log files with a session label and lets the operator insert marker notes from the keyboard during a capture (for example "shift to R now"). Capture these, one action per session:

1. Key on, cart idle, 30 s
2. Shift D, N, R, holding each about 10 s, with markers
3. Slow throttle ramp with drive wheels off the ground, then release
4. Brake, parking brake, low beam, high beam, left blinker, right blinker, each separately with markers
5. Short drive with phone GPS speed logged for comparison
6. Key off, to catch shutdown messages

Record pack voltage and current from the DROK monitor during sessions 3 and 5 so voltage and current fields can be matched.

### Analysis
`tools/can_log_analyze.py` lists message IDs, rates, and which bytes change in each session, aligned to the markers. Use it to find gear, speed or motor RPM, throttle, and any voltage, current, or fault fields. Write findings to `docs/protocols.md` and a DBC file at `docs/factory_can.dbc`.

Do not attempt to reverse engineer the factory screen firmware (Melis RTOS). The bus traffic is the source of truth.

The same adapter and scripts are reused later to sniff the Kelly.

## Build phases

Do these in order. Each phase ends with something that runs.

**Phase 0: both sides on fake data.** Firmware scaffold with `sim.cpp` streaming JSON over USB. Android app scaffold with `SimSource` and `TcpSource`, plus `tools/fake_esp.py`. Done when the dashboard runs in the Android emulator on simulated data and the ESP32 streams simulated JSON readable in a serial monitor.

**Phase 1: real link on the real head unit.** `UsbSerialSource`, `LinkService`, launcher registration, boot start, auto reconnect. Done when the head unit boots straight into the dash showing the ESP32's simulated data, and survives unplugging and replugging USB and a key off and on cycle.

**Phase 2: digital inputs.** Optos for ACC, blinkers, beams, brake, parking brake, reverse, illumination, speed mode. Speed pulse on a PCNT counter. ACC sleep and wake.

**Phase 3: BMS over BLE.** Scan and log advertised names and services to identify the BMS. Implement JBD first behind a decoder interface. Auto reconnect.

**Phase 4: Kelly decode.** After the Kelly is installed, sniff it with the laptop adapter and the same capture and analysis tools used for the factory bus, with an isolated connection. Target fields: RPM, phase current, battery current, controller temp, motor temp, fault codes, direction. Fall back to the Kelly serial port if there is no CAN. Then implement the decoder on the ESP32 behind the isolated transceiver, with raw frame logging available as `log` lines when enabled from the app. Anything learned from the factory bus capture (gear especially) informs where gear comes from after the swap: the Kelly, the gear rocker, or both.

**Phase 5: Home Assistant.** MQTT with HA discovery when STA is connected. Publish at 1 Hz. Main use is SOC and charging status while parked at home.

**Phase 6: Android polish.** CarPlay button, overlay, night theme, trips, settings screen, calibration.

**Track G: Course GPS.** App only, so it runs alongside the hardware phases once the Phase 0 app exists. G1: check OpenStreetMap coverage of the courses you play, fill gaps, build course files. G2: yardage engine and course screen, developed on replayed GPS in the emulator. G3: on the real head unit, measure GPS accuracy against known markers on the course and decide whether the ESP32 GNSS upgrade is needed.

## Head unit setup (manual, not code)

1. On arrival, install CPU-Z and confirm UIS7862S, 8GB RAM, Android version, and screen resolution. Dispute right away if it does not match.
2. Enable developer options and USB debugging. Install the APK with ADB or from a USB drive.
3. Set Cart Dash as the default home app. Some TS10 firmware has its own "default desktop" setting that also needs changing.
4. In the head unit's app management or battery settings, exempt Cart Dash from any background killing or "clean on sleep" feature.
5. Grant overlay permission if the overlay is used.
6. Grant Cart Dash location permission. Mount the GPS antenna under the cart roof with a clear view of the sky.
7. Copy course files to the head unit.

## Writing rules

- Comments and docs in plain language. No em dashes.
- When a **VERIFY** item is confirmed on hardware, update `docs/pinout.md` or `docs/protocols.md` in the same commit.
