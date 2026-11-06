# Tools

| Tool | What it does |
|---|---|
| `can_capture.py` | Listen-only CAN captures with typed markers, on a Linux laptop |
| `can_log_analyze.py` | Finds the bytes that matter in those captures |
| `fake_esp.py` | Pretends to be the ESP32, for building the app without hardware |
| `cartdash_proto.py` | Reference rules for reading the USB link, used by the other tools and tests |
| `course_from_osm.py` | Builds a course file from OpenStreetMap and reports which holes are missing data |
| `course_imagery.py` | Downloads the public domain USGS aerial photo for a course |
| `course_preview.py` | Draws a course file (and its photo) as PNG images, to check it by eye |
| `courselib.py` | Course file format and yardage math, the reference for the app's course code |

Setup, once:

```bash
python3 -m venv .venv
```

```bash
. .venv/bin/activate
```

```bash
pip install -r tools/requirements.txt
```

`matplotlib` (for `--plot`) and `cantools` (for checking the DBC file) are optional extras:

```bash
pip install matplotlib cantools
```

Run the tests with `python3 -m pytest tools/tests`.

---

# Factory CAN capture

This has to happen before the Tianji controller comes out, because the bus goes quiet after the swap and cannot be captured again. The plan and the gate are in `docs/plan.md` (Track A).

## Before going to the cart

1. **Adapter.** Plug in the isolated CANable. It should show up as `can0`:

   ```bash
   ip -details link show can0
   ```

   If there is no `can0`, the adapter is running slcan firmware. Flash candleLight firmware with the CANable web updater (needs Chrome), then plug it in again.

2. **Termination off.** If the adapter has a 120 ohm termination switch or jumper, turn it off. The factory bus is already terminated.

3. **Bench test** with nothing connected. It checks sudo, the tool, and the files. Expect zero frames.

   ```bash
   python3 tools/can_capture.py setup --bitrate 250000
   ```

   ```bash
   python3 tools/can_capture.py check
   ```

   ```bash
   python3 tools/can_capture.py capture --label bench-test --duration 10
   ```

   Delete `captures/factory/*_bench-test` afterward.

4. **Clocks.** The laptop should say `System clock synchronized: yes` in `timedatectl`. Set the phone to automatic time. GPS speed is matched to CAN data by time.

5. **Phone.** Install a GPS logger app that exports GPX (for session 5), and plan to film the factory screen during every session.

## At the cart

1. **Laptop on battery**, not on its charger.
2. **Wire check** from the brief, with a meter. Record results in `docs/pinout.md`. Also measure CANH and CANL against 16 pin connector pin 1 (ground) with the key on.
3. **Connect.** Back-probe CANH and CANL on the 9 pin connector with the factory screen still plugged in. Connect the adapter's CAN ground to pin 1 only if CANH and CANL both read about 2.5 V against pin 1. If they do not, stop and write down the readings before connecting any ground.
4. **Find the bitrate** with the key on. Nothing is transmitted:

   ```bash
   python3 tools/can_capture.py scan
   ```

   It tries 250k, 500k, 125k, and 1M, prints frames and errors for each, and leaves `can0` listening at the best one. No frames at any rate usually means the key is off, a probe is not making contact, or CANH and CANL are swapped.

## Capture sessions

While capturing, **type a note and press Enter at the moment something happens.** Pressing Enter on an empty line stamps the next planned step from `--steps`. Readings typed as `v=66.4 a=-48` become measured values that the analyzer matches to CAN bytes. Type `:s` for live stats and `:q` (or Ctrl-C) to stop.

**Video sync:** at the start of each session, point the phone camera at the laptop and type `clap` then Enter. The video frame where the marker line appears lines up the video with the capture.

One action per session, as the brief says. Each command creates a folder under `captures/factory/`.

**1. Key on, idle.** Start with the key off. Press Enter as you turn the key on, then leave it idle.

```bash
python3 tools/can_capture.py capture --label 01-key-on-idle --steps "key on" --duration 45
```

**2. Gear.** Foot on the brake, no throttle. Press Enter as you shift and hold each gear about 10 s.

```bash
python3 tools/can_capture.py capture --label 02-gear --steps "D,N,R,N,D,N"
```

**3. Throttle ramp.** Drive wheels off the ground on jack stands, the other wheels chocked, in D. Ramp the throttle slowly to full, then release. Type the DROK voltage and current as `v=... a=...` every few seconds.

```bash
python3 tools/can_capture.py capture --label 03-throttle-ramp --steps "ramp start,full,release,stopped"
```

**4. Controls, one capture each.** Hold each state about 5 s. Doing each on and off twice helps: the analyzer trusts a byte more when repeated labels agree.

```bash
python3 tools/can_capture.py capture --label 04a-brake --steps "brake on,brake off,brake on,brake off"
```

```bash
python3 tools/can_capture.py capture --label 04b-park-brake --steps "park on,park off,park on,park off"
```

```bash
python3 tools/can_capture.py capture --label 04c-low-beam --steps "low on,low off,low on,low off"
```

```bash
python3 tools/can_capture.py capture --label 04d-high-beam --steps "high on,high off,high on,high off"
```

```bash
python3 tools/can_capture.py capture --label 04e-left-blinker --steps "left on,left off,left on,left off"
```

```bash
python3 tools/can_capture.py capture --label 04f-right-blinker --steps "right on,right off,right on,right off"
```

If the cart has a speed mode switch, capture that too:

```bash
python3 tools/can_capture.py capture --label 04g-speed-mode --steps "low,high,low,high"
```

**5. Short drive.** Start the phone GPS logger first. Drive a few minutes with a mix of speeds, including a stop. Type DROK readings now and then. Export the GPX afterward.

```bash
python3 tools/can_capture.py capture --label 05-drive --steps "go,stop"
```

**6. Key off.** Press Enter as you turn the key off.

```bash
python3 tools/can_capture.py capture --label 06-key-off --steps "key off" --duration 60
```

## Analysis

One session:

```bash
python3 tools/can_log_analyze.py captures/factory/*_02-gear
```

The drive, matched against GPS speed, with plots saved into the session folder:

```bash
python3 tools/can_log_analyze.py captures/factory/*_05-drive --gps ~/Downloads/drive.gpx --plot
```

Every change of one ID over time, with markers in between (counter bytes hidden):

```bash
python3 tools/can_log_analyze.py captures/factory/*_02-gear --trace 18FF50E5
```

Everything into one report:

```bash
python3 tools/can_log_analyze.py captures/factory/* --out captures/factory/report.md
```

How to read the report:

- **IDs**: each byte shows its value if it never changes, `~N` if it takes N values, or `ct` if it is a rolling counter.
- **Bytes that step at a marker**: steady value before and after each marker. Score 1.00 means the bits only ever change near markers.
- **Bytes that hold a different value in each segment**: best for gear (D, N, R) and on/off controls. `~` means the byte kept moving in that segment.
- **Bits that toggle**: blinkers show up here as bit flips per second.
- **Correlation**: 8 and 16 bit fields that track GPS speed or typed readings, with a suggested factor and offset. An r above 0.95 is a strong match; below 0.8 is probably coincidence. The shift column shows how far apart the phone and laptop clocks were.

Write what you find in `docs/protocols.md` and `docs/factory_can.dbc`.

## Gate before the Kelly swap

- [ ] The bitrate scan found clean traffic, with few or no error frames.
- [ ] Every session has frames and its markers.
- [ ] Gear, brake, and blinkers show up clearly in sessions 2 and 4, or you have written down that they are not on the bus.
- [ ] Speed or RPM correlates with GPS in session 5, or you have written down that it is not on the bus.
- [ ] Captures committed and pushed:

  ```bash
  git add captures/factory
  ```

  ```bash
  git commit -m "Add factory CAN captures"
  ```

  ```bash
  git push
  ```

## Later: sniffing the Kelly

Same tools, with `--bus kelly` so the captures go to `captures/kelly/`. If `scan` sees no frames at any bitrate with the controller powered, the Kelly may only answer requests. See Phase 4 in `docs/plan.md`.

---

# Course files

`course_from_osm.py` turns a course on OpenStreetMap into a course file (`docs/course_format.md`) and prints a coverage report. It needs internet access to the Overpass API.

See which courses OpenStreetMap knows about in Wyoming, with their IDs:

```bash
python3 tools/course_from_osm.py list --region US-WY
```

Build one by name. If more than one course matches, it lists them and asks for `--osm-id`:

```bash
python3 tools/course_from_osm.py build --name "Bell Nob" --region US-WY
```

```bash
python3 tools/course_from_osm.py build --osm-id way/123456789
```

The report has one row per hole. A hole is **ok** when it has a green outline and a hole number. **NO GREEN** and **MISSING** rows need fixing on OpenStreetMap:

1. Open the **Edit** link from the report (the iD editor, in a browser, free OpenStreetMap account).
2. For each missing green, trace the green outline and tag it `golf=green`.
3. For each hole, draw a line from the back tee to the middle of the green and tag it `golf=hole`, `ref=<hole number>`, `par=<par>`. This links the green to its number and gives the app the line of play.
4. Optionally trace tees (`golf=tee`), fairways (`golf=fairway`), bunkers (`golf=bunker`), and water (`natural=water`).
5. Save, wait a few minutes for Overpass to catch up, and build again.

The report also flags numbers that look wrong: a green depth outside 8 to 60 yards, a tiny green, or a length that does not fit the par. Check those against the scorecard.

Exit code 0 means every hole is ready, 3 means the file was written but some holes are not.

**Scorecards and fixes** go in `courses/<course>.overrides.json`: pars, handicaps, and tee yardages, features to leave out, and a short course made of unnumbered holes. The build picks the file up by course name. The format is in `docs/course_format.md`. With a scorecard, the report gains a column comparing the mapped length of each hole with the card.

Add `--save-osm courses/osm/<name>.json` to keep the raw download. It lets anyone rebuild the course file without internet access, with `build --osm-json`.

## Aerial photos

Download the photo for a course (about a minute per course, longer the first time an area is asked for):

```bash
python3 tools/course_imagery.py courses/bell-nob-golf-course.geojson
```

It writes `<course>.photo.jpg` and `<course>.photo.json` next to the course file. NAIP photos are flown every two to three years, so recent construction may not show yet.

## Checking a course by eye

Draw the whole course and every hole the way the course screen shows it, into `courses/preview/<course>/` (not committed):

```bash
python3 tools/course_preview.py courses/bell-nob-golf-course.geojson
```

The same on the aerial photo:

```bash
python3 tools/course_preview.py courses/bell-nob-golf-course.geojson --photo
```

In the overview, a magenta outline is a green that is not linked to a hole and an orange one is a tee not linked to a hole. Practice greens and range tees normally show up this way; anything else is a hole that needs its line of play on OpenStreetMap. The previews need matplotlib, and the photo tools need Pillow:

```bash
pip install matplotlib pillow
```

---

# fake_esp.py

Streams the same JSON lines as the firmware, so the app can be built and tested with no hardware. Scenarios: `drive` (default), `charge`, `regen`, `faults`, `stale`, `dropout`. Run `python3 tools/fake_esp.py --help` for details.

For the Android emulator (the app's TCP source connects to `10.0.2.2:5555`):

```bash
python3 tools/fake_esp.py --tcp 5555
```

A virtual serial port, for testing serial code on the laptop:

```bash
python3 tools/fake_esp.py --pty --link /tmp/ttyCARTDASH
```

A quick look at the stream:

```bash
python3 tools/fake_esp.py --stdout --duration 3
```
