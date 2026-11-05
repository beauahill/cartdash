import gzip

import can
import pytest

import canlog


FRAMES = [
    canlog.Frame(t=1.5, can_id=0x123, ext=False, data=bytes([1, 2, 3])),
    canlog.Frame(t=2.25, can_id=0x18FF50E5, ext=True, data=bytes(range(8))),
    canlog.Frame(t=3.0, can_id=0x7FF, ext=False, data=b""),
    canlog.Frame(t=4.0, can_id=0x456, ext=False, rtr=True, dlc=4),
    canlog.Frame(t=5.0, can_id=0x00000004, ext=True, data=bytes(8), err=True, dlc=8),
    canlog.Frame(t=6.0, can_id=0x00000001, ext=True, data=bytes([0xAA])),
]


@pytest.mark.parametrize("frame", FRAMES)
def test_candump_round_trip(frame):
    line = canlog.format_candump(frame, "can0")
    back = canlog.parse_candump(line)
    assert back is not None
    assert (back.t, back.can_id, back.ext, back.data, back.err, back.rtr) == (
        frame.t,
        frame.can_id,
        frame.ext,
        frame.data,
        frame.err,
        frame.rtr,
    )


def test_candump_formatting_matches_candump():
    assert canlog.format_candump(FRAMES[0]) == "(1.500000) can0 123#010203"
    assert canlog.format_candump(FRAMES[1]) == "(2.250000) can0 18FF50E5#0001020304050607"
    assert canlog.format_candump(FRAMES[3]) == "(4.000000) can0 456#R4"
    assert canlog.format_candump(FRAMES[4]).startswith("(5.000000) can0 20000004#")
    # A small extended ID keeps 8 digits so it is not mistaken for a standard ID.
    assert canlog.format_candump(FRAMES[5]) == "(6.000000) can0 00000001#AA"


def test_parse_skips_junk():
    assert canlog.parse_candump("") is None
    assert canlog.parse_candump("hello") is None
    assert canlog.parse_candump("(1.0) can0 123#XYZ") is None


def test_reads_python_can_writer_output(tmp_path):
    path = tmp_path / "pc.log"
    with can.CanutilsLogWriter(str(path), channel="can0") as w:
        w.on_message_received(can.Message(timestamp=10.0, arbitration_id=0x18FF50E5, is_extended_id=True, data=[1, 2]))
        w.on_message_received(can.Message(timestamp=10.1, arbitration_id=0x123, is_extended_id=False, data=[3]))
    frames = list(canlog.iter_frames(path))
    assert [(f.ident, f.data) for f in frames] == [("18FF50E5", b"\x01\x02"), ("123", b"\x03")]


def test_gzip_round_trip(tmp_path):
    path = tmp_path / "x.log.gz"
    canlog.write_frames(path, FRAMES)
    with gzip.open(path, "rt") as f:
        assert len(f.read().splitlines()) == len(FRAMES)
    assert len(list(canlog.iter_frames(path))) == len(FRAMES)


def test_parse_kv():
    assert canlog.parse_kv("v=66.4 a=-48.5") == {"v": 66.4, "a": -48.5}
    assert canlog.parse_kv("shift to R now") == {}
    assert canlog.parse_kv("brake on, A = 12") == {"a": 12.0}


def test_markers_round_trip(tmp_path):
    w = canlog.MarkerWriter(tmp_path / "markers.csv", t0=100.0)
    w.add(canlog.Marker(101.5, "D"))
    w.add(canlog.Marker(103.0, "label, with comma"))
    w.close()
    ms = canlog.read_markers(tmp_path / "markers.csv")
    assert [(m.t, m.label) for m in ms] == [(101.5, "D"), (103.0, "label, with comma")]


def test_load_session_folder_and_bare_log(tmp_path):
    folder = tmp_path / "s"
    folder.mkdir()
    canlog.write_frames(folder / "can.log.gz", FRAMES)
    s = canlog.load_session(folder)
    assert len(s.frames) == len(FRAMES)
    assert len(s.error_frames) == 1
    assert len(s.data_frames) == 4
    s2 = canlog.load_session(folder / "can.log.gz")
    assert len(s2.frames) == len(FRAMES)
