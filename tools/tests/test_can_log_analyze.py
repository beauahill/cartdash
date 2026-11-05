import pytest

import can_log_analyze as ana
import canlog
import synth


@pytest.fixture
def gear(tmp_path):
    return canlog.load_session(synth.gear_session(tmp_path / "gear"))


@pytest.fixture
def lights(tmp_path):
    return canlog.load_session(synth.lights_session(tmp_path / "lights"))


def _prep(session):
    ids = ana.group_by_id(session.data_frames)
    stats = {k: ana.id_stats(v) for k, v in ids.items()}
    return ids, stats


def test_id_stats(gear):
    ids, stats = _prep(gear)
    assert set(stats) == {"18FF50E5", "0CF11E05", "123"}
    s = stats["18FF50E5"]
    assert s.period_ms == pytest.approx(100, abs=1)
    assert s.bytes[1].const == 0x12
    assert s.bytes[2].counter == "ct"
    assert s.bytes[0].unique == 3
    assert stats["123"].period_ms == pytest.approx(200, abs=1)
    assert [b.token() for b in stats["123"].bytes] == ["01", "02", "03", "04"]


def test_counter_detection():
    assert ana.detect_counter([i % 256 for i in range(300)]) == "ct"
    assert ana.detect_counter([0xA0 | (i % 16) for i in range(40)]) == "ct lo"
    assert ana.detect_counter([0, 0, 1, 1, 2, 2, 3, 3, 4, 4]) is None
    assert ana.detect_counter([5] * 20) is None


def test_gear_byte_steps_at_markers(gear):
    ids, stats = _prep(gear)
    steps = ana.marker_steps(ids, stats, gear.markers)
    best = {}
    for s in steps:
        best.setdefault(s.marker.label + str(s.marker_index), s)
    found = [(s.marker.label, s.ident, s.byte, s.before, s.after) for s in best.values()]
    assert ("D", "18FF50E5", 0, 0, 1) in found
    assert ("N", "18FF50E5", 0, 1, 0) in found
    assert ("R", "18FF50E5", 0, 0, 2) in found
    # The drifting temperature byte must not be mistaken for a step at the R marker.
    r_steps = [s for s in steps if s.marker.label == "R"]
    assert (r_steps[0].ident, r_steps[0].byte) == ("18FF50E5", 0)


def test_gear_byte_tops_segment_table(gear):
    ids, stats = _prep(gear)
    segs = ana.segments(gear.start, gear.end, gear.markers)
    assert [label for label, _, _ in segs] == ["(start)", "D", "N", "R", "D"]
    rows = ana.segment_rows(ids, stats, segs, gear.markers)
    top = rows[0]
    assert (top.ident, top.byte) == ("18FF50E5", 0)
    assert [top.cell(i) for i in range(5)] == ["00", "01", "00", "02", "01"]
    assert top.labels_agree


def test_blinker_bit_and_brake_bit(lights):
    ids, stats = _prep(lights)
    segs = ana.segments(lights.start, lights.end, lights.markers)
    labels = [label for label, _, _ in segs]
    toggles = ana.toggle_rows(ids, stats, segs)
    blink = [t for t in toggles if (t.ident, t.byte, t.bit) == ("18FF50E5", 5, 0)]
    assert blink, "left blinker bit not found"
    rates = dict(zip(labels, blink[0].rates))
    assert rates["left on"] > 2.0
    assert rates["(start)"] == 0 and rates["brake on"] == 0

    rows = ana.segment_rows(ids, stats, segs, lights.markers)
    assert (rows[0].ident, rows[0].byte) == ("18FF50E5", 5)
    b5 = [r for r in rows if (r.ident, r.byte) == ("18FF50E5", 5)]
    assert b5, "brake byte not found even though the blinker shares it"
    cells = dict(zip(labels, [b5[0].cell(i) for i in range(len(labels))]))
    assert cells["brake on"] == "08" and cells["brake off"] == "00" and cells["left on"] == "~"
    # The blinker toggling in the same byte must not hide the brake step.
    brake_steps = [s for s in ana.marker_steps(ids, stats, lights.markers) if s.marker.label == "brake on"]
    assert (brake_steps[0].ident, brake_steps[0].byte, brake_steps[0].after) == ("18FF50E5", 5, 0x08)
    assert brake_steps[0].score > 0.9


def test_drive_correlations(tmp_path):
    folder, gps = synth.drive_session(tmp_path / "drive")
    session = canlog.load_session(folder)
    ids, stats = _prep(session)
    cands = ana.candidates(ids, stats)

    speed = ana.correlate(cands, gps)
    assert speed[0].name == "0CF11E05 b0-1 u16le"
    assert speed[0].r > 0.99
    assert speed[0].shift == pytest.approx(synth.GPS_CLOCK_LAG, abs=0.25)
    assert 1 / speed[0].factor == pytest.approx(synth.RPM_PER_MPH, rel=0.02)

    series = ana.marker_series(session.markers)
    amps = ana.correlate(cands, series["a"])
    assert amps[0].name == "0CF11E05 b2-3 s16le"
    assert amps[0].factor == pytest.approx(0.1, rel=0.01)
    volts = ana.correlate(cands, series["v"])
    assert volts[0].name == "0CF11E05 b4-5 u16be"
    assert volts[0].factor == pytest.approx(0.1, rel=0.02)


def test_readings_are_not_event_markers():
    assert ana.is_reading("v=66.4 a=-48")
    assert not ana.is_reading("brake on")
    assert not ana.is_reading("brake on v=66")


def test_report_end_to_end(tmp_path):
    g = synth.gear_session(tmp_path / "gear")
    d, gps = synth.drive_session(tmp_path / "drive")
    gps_csv = tmp_path / "gps.csv"
    gps_csv.write_text("time,speed_mph\n" + "".join(f"{t},{v}\n" for t, v in gps))
    out = tmp_path / "report.md"
    rc = ana.main([str(g), str(d), "--gps", str(gps_csv), "--out", str(out)])
    assert rc == 0
    text = out.read_text()
    assert "## IDs across sessions" in text
    assert "## Session: gear-dnr" in text
    assert "### Bytes that step at a marker" in text
    assert "#### gps_mph" in text
    assert "0CF11E05 b0-1 u16le" in text


def test_trace(gear, capsys):
    lines = ana.trace(gear, "0x18ff50e5")
    assert lines[0].startswith("## Trace of 18FF50E5")
    assert any(">> R" in line for line in lines)
    assert ana.trace(gear, "7AB") == ["ID 7AB not found in gear-dnr"]


def test_gpx_loader(tmp_path):
    gpx = tmp_path / "t.gpx"
    gpx.write_text(
        """<?xml version="1.0"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
<trkpt lat="44.0000" lon="-106.0000"><time>2026-11-06T10:00:00Z</time></trkpt>
<trkpt lat="44.0001" lon="-106.0000"><time>2026-11-06T10:00:01Z</time></trkpt>
<trkpt lat="44.0002" lon="-106.0000"><time>2026-11-06T10:00:02Z</time><extensions><speed>5.0</speed></extensions></trkpt>
</trkseg></trk></gpx>"""
    )
    s = ana.load_gpx(gpx)
    assert len(s) == 2
    assert s[0][1] == pytest.approx(11.1195 * 2.23694, rel=0.01)  # 0.0001 deg of latitude is about 11.1 m
    assert s[1][1] == pytest.approx(5.0 * ana.MPS_TO_MPH, rel=1e-9)


def test_gps_csv_units(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("timestamp,speed\n1800000000,10\n1800000001,20\n")
    s = ana.load_gps_csv(p)
    assert s[0] == (1800000000.0, pytest.approx(22.369, rel=1e-3))  # plain speed is m/s
    p.write_text("time,Speed (km/h)\n2026-11-06T10:00:00Z,100\n2026-11-06T10:00:01Z,50\n")
    s = ana.load_gps_csv(p)
    assert s[0][1] == pytest.approx(62.137, rel=1e-3)


def test_parse_time():
    assert ana.parse_time("1800000000.5") == 1800000000.5
    assert ana.parse_time("1800000000500") == 1800000000.5
    assert ana.parse_time("2026-11-06T10:00:00Z") == ana.parse_time("2026-11-06T03:00:00-07:00")
