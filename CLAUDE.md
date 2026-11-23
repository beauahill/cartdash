# Cart Dash: notes for Claude sessions

Read these first:
- `README.md`: the project brief. Read it fully before writing code. Its electrical rules were corrected from measurements on 2026-11-23.
- `docs/plan.md`: order of work, decisions so far, open questions, and status of each phase and track.
- `docs/verify.md`: every hardware fact still to confirm, and what has been confirmed.

Where things are:
- `docs/pinout.md`: the factory screen plugs, measured: hole numbers, wire colors, functions, photos in `docs/photos/`.
- `docs/usb_protocol.md`, `protocol/schema/`, `protocol/fixtures/`: the ESP32 to app protocol. The fixtures are shared test data: the firmware native tests and the Android unit tests must check against them, as `tools/tests/test_protocol.py` does.
- `docs/course_format.md`, `courses/`: course files, aerial photos, and overrides for the five courses. `tools/courselib.py` holds the yardage math the app ports to `course/Yardage.kt`; port its tests too.
- `tools/`: Python tools and their tests (`python3 -m pytest tools/tests -q`). `tools/fake_esp.py` stands in for the ESP32 while building the app.
- `docs/dev_setup.md`: laptop setup for Phase 0.

Rules:
- Plain language in comments and docs. No em dashes.
- When a VERIFY item is confirmed on hardware, update `docs/pinout.md` or `docs/protocols.md` (and `docs/verify.md`) in the same commit.
- Electrical facts that changed the design (details in `README.md` and `docs/pinout.md`): the 12V converter is non-isolated, so 12V negative and pack negative are one conductor; the 12V system is switched by the key, with no constant 12V on the cart; factory screen 9 pin hole 8 carries 68 V pack voltage. There is no CAN bus at the factory screen, so the factory CAN capture was dropped.
- Work so far is on branch `claude/bold-meitner-nkgbyp`, which is also the GitHub default branch.

Where the project stands (late November 2026): Python tools, protocol, and course data are done and tested. Next is Phase 0: firmware scaffold in `firmware/` streaming simulated JSON, and the Android app in `android/` running on `SimSource` and `TcpSource` in the emulator, then the course screen (Track G).
