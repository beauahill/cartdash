# Cart Dash: notes for Claude sessions

Read these first:
- `README.md`: the project brief. Read it fully before writing code. Its electrical rules were corrected from measurements on 2026-11-23.
- `docs/plan.md`: order of work, decisions so far, open questions, and status of each phase and track.
- `docs/verify.md`: every hardware fact still to confirm, and what has been confirmed.

Where things are:
- `docs/pinout.md`: the factory screen plugs, measured: hole numbers, wire colors, functions, photos in `docs/photos/`.
- `docs/usb_protocol.md`, `protocol/schema/`, `protocol/fixtures/`: the ESP32 to app protocol. The fixtures are shared test data: the firmware native tests and the Android unit tests must check against them, as `tools/tests/test_protocol.py` does.
- `docs/dash_design.md`, `docs/design/`: the chosen look of the drive dash and course screen (colors, fonts, layout in `u`) and the mockup sources.
- `docs/course_format.md`, `courses/`: course files, aerial photos, and overrides for the five courses. `tools/courselib.py` holds the yardage math the app ports to `course/Yardage.kt`; port its tests too.
- `tools/`: Python tools and their tests (`python3 -m pytest tools/tests -q`). `tools/fake_esp.py` stands in for the ESP32 while building the app.
- `docs/dev_setup.md`: laptop setup for Phase 0.

Rules:
- Plain language in comments and docs. No em dashes.
- When a VERIFY item is confirmed on hardware, update `docs/pinout.md` or `docs/protocols.md` (and `docs/verify.md`) in the same commit.
- Electrical facts that changed the design (details in `README.md` and `docs/pinout.md`): the 12V converter is non-isolated, so 12V negative and pack negative are one conductor; the 12V system is switched by the key, with no constant 12V on the cart; factory screen 9 pin hole 8 carries 68 V pack voltage. There is no CAN bus at the factory screen, so the factory CAN capture was dropped.
- Work so far is on branch `claude/bold-meitner-nkgbyp`, which is also the GitHub default branch.

Where the project stands (2026-11-23): Python tools, protocol, and course data are done and tested. Phase 0 is mostly built: the firmware in `firmware/` (espressif32 8.0.0, Arduino core 3.3.12) streams simulated JSON and passes its native tests, and the Android app in `android/` (AGP 9.5.2, Kotlin 2.4.21, JDK 17) runs `SimSource` and `TcpSource` and passes its unit tests. The dash has been seen in the emulator on every `fake_esp.py` scenario. Still open for Phase 0: flashing a real ESP32-S3 (not on hand yet). See the Phase 0 status in `docs/plan.md`. After that comes Phase 1 and the course screen (Track G).

Laptop notes: the default JDK is newer than 17, so set `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64` for Gradle. Other projects run their own emulator and Gradle daemons on this laptop: address the Cart Dash emulator with `adb -s`, never bare `adb`, and do not stop other daemons. Memory and port notes are in `docs/dev_setup.md`.
