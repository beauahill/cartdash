"""JBD BMS decoder and the probe tool's offline replay.

Synthetic frames follow docs/protocols.md. Once real captures exist in
captures/bms/, add a test that replays one and checks it against the JBD
app's readings taken at the same time.
"""

import json
import struct
from pathlib import Path

import jsonschema
import pytest

import bms_probe
import cartdash_proto
import jbd

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "protocol" / "schema" / "cartdash.schema.json").read_text())


def basic_data(pack_v=66.42, pack_a=-48.5, remaining=106.6, nominal=130.0, cycles=12, balancing=0,
               protection=0, sw=0x10, soc=82, fet=0x03, cells=20, temps_c=(25.6, 26.7), extra=b""):
    data = struct.pack(
        ">HhHHHHHHHBBBBB",
        round(pack_v * 100), round(pack_a * 100), round(remaining * 100), round(nominal * 100),
        cycles, 0x2B4F, balancing & 0xFFFF, balancing >> 16, protection, sw, soc, fet, cells, len(temps_c),
    )
    data += b"".join(struct.pack(">H", round(t * 10) + 2731) for t in temps_c)
    return data + extra


def cell_data(volts):
    return b"".join(struct.pack(">H", round(v * 1000)) for v in volts)


CELLS = [(3311 + i) / 1000 for i in range(20)]  # the BMS reports whole mV


def test_requests_match_the_documented_bytes():
    assert jbd.request(jbd.CMD_BASIC).hex() == "dda50300fffd77"
    assert jbd.request(jbd.CMD_CELLS).hex() == "dda50400fffc77"
    assert jbd.request(jbd.CMD_VERSION).hex() == "dda50500fffb77"


def test_whole_basic_frame():
    frames = jbd.FrameAssembler().feed(jbd.build_response(jbd.CMD_BASIC, basic_data()))
    assert len(frames) == 1 and frames[0].ok and frames[0].cmd == jbd.CMD_BASIC
    b = jbd.parse_basic(frames[0].data)
    assert b.pack_v == pytest.approx(66.42)
    assert b.pack_a == pytest.approx(-48.5)  # discharging is negative, as on the USB link
    assert b.remaining_ah == pytest.approx(106.6) and b.nominal_ah == pytest.approx(130.0)
    assert (b.cycles, b.soc_pct, b.cell_count) == (12, 82, 20)
    assert b.temps_c == [25.6, 26.7]
    assert b.charge_fet and b.discharge_fet
    assert b.faults == []


@pytest.mark.parametrize("size", [1, 7, 20])
def test_frame_split_across_notifications(size):
    raw = jbd.build_response(jbd.CMD_BASIC, basic_data()) + jbd.build_response(jbd.CMD_CELLS, cell_data(CELLS))
    asm = jbd.FrameAssembler()
    frames = []
    for i in range(0, len(raw), size):
        frames += asm.feed(raw[i:i + size])
    assert [f.cmd for f in frames] == [jbd.CMD_BASIC, jbd.CMD_CELLS]
    assert jbd.parse_cells(frames[1].data) == pytest.approx(CELLS)
    assert asm.dropped == 0


def test_garbage_and_a_corrupt_frame_are_skipped():
    good = jbd.build_response(jbd.CMD_CELLS, cell_data(CELLS))
    bad = bytearray(jbd.build_response(jbd.CMD_BASIC, basic_data()))
    bad[10] ^= 0xFF  # breaks the checksum
    asm = jbd.FrameAssembler()
    frames = asm.feed(b"\x00\x13garbage" + bytes(bad) + good)
    assert [f.cmd for f in frames] == [jbd.CMD_CELLS]
    assert asm.dropped > 0


def test_frame_waits_for_its_last_byte():
    raw = jbd.build_response(jbd.CMD_CELLS, cell_data(CELLS))
    asm = jbd.FrameAssembler()
    assert asm.feed(raw[:-1]) == []
    assert len(asm.feed(raw[-1:])) == 1


def test_error_status_is_not_ok():
    frames = jbd.FrameAssembler().feed(jbd.build_response(jbd.CMD_BASIC, b"", status=0x80))
    assert len(frames) == 1 and not frames[0].ok


def test_protection_flags_and_discharge_fet():
    b = jbd.parse_basic(basic_data(protection=(1 << 1) | (1 << 6) | (1 << 10), fet=0x01))
    assert b.faults == ["cell_uv", "dsg_ot", "short", jbd.DSG_FET_OFF]
    assert jbd.parse_basic(basic_data(fet=0x02)).faults == []  # charge FET off alone is normal when full


def test_extra_bytes_after_temperatures_are_ignored():
    b = jbd.parse_basic(basic_data(extra=b"\x00\x01\x02\x03\x04\x05\x06\x07"))
    assert b.temps_c == [25.6, 26.7] and b.soc_pct == 82


def test_short_or_inconsistent_basic_info_is_rejected():
    with pytest.raises(ValueError):
        jbd.parse_basic(basic_data()[:20])
    with pytest.raises(ValueError):
        jbd.parse_basic(basic_data()[:-1])  # says 2 temperatures, carries 1.5
    with pytest.raises(ValueError):
        jbd.parse_cells(b"\x0c\xef\x0c")


def test_negative_temperature():
    assert jbd.parse_basic(basic_data(temps_c=(-5.3,))).temps_c == [-5.3]


def test_state_fields_follow_the_usb_protocol():
    basic = jbd.parse_basic(basic_data())
    fields = jbd.state_fields(basic, CELLS)
    assert fields == {
        "soc_pct": 82,
        "pack_v": 66.42,
        "pack_a": -48.5,
        "power_kw": -3.22,
        "bms_temp_f": [78.1, 80.1],
        "bms_faults": [],
        "cell_v_min": pytest.approx(3.311),
        "cell_v_max": pytest.approx(3.330),
    }
    line = json.dumps({"type": "state", "seq": 1, "t": 1000, **fields})
    msg = cartdash_proto.parse_line(line)
    assert msg is not None
    jsonschema.Draft202012Validator(SCHEMA).validate(msg)


def test_state_fields_leave_out_what_was_not_read():
    assert jbd.state_fields(None, None) == {}
    assert set(jbd.state_fields(None, CELLS)) == {"cell_v_min", "cell_v_max"}


def test_replay_of_a_saved_capture(tmp_path, capsys):
    raw = (jbd.build_response(jbd.CMD_VERSION, b"JBD-SP20S\x00")
           + jbd.build_response(jbd.CMD_CELLS, cell_data(CELLS))
           + jbd.build_response(jbd.CMD_BASIC, basic_data()))
    lines = [json.dumps({"type": "meta", "address": "AA:BB:CC:DD:EE:FF", "date": "2026-11-24T10:00:00"}),
             json.dumps({"t": 0.0, "dir": "tx", "hex": jbd.request(jbd.CMD_BASIC).hex()})]
    lines += [json.dumps({"t": 0.1 + i / 100, "dir": "rx", "hex": raw[i:i + 20].hex()}) for i in range(0, len(raw), 20)]
    path = tmp_path / "cap.jsonl"
    path.write_text("\n".join(lines) + "\n")

    assert bms_probe.main(["--replay", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Hardware version: JBD-SP20S" in out
    assert "66.42 V" in out and "-48.50 A" in out and "SOC 82%" in out
    assert "cells 3.311 to 3.330 V" in out
    assert "bytes skipped: 0" in out


def test_capture_writes_meta_then_chunks(tmp_path):
    cap = bms_probe.Capture(tmp_path / "c.jsonl", {"address": "x"})
    cap.chunk("tx", b"\xdd\xa5")
    cap.chunk("rx", b"\xdd\x03")
    cap.close()
    recs = [json.loads(s) for s in (tmp_path / "c.jsonl").read_text().splitlines()]
    assert recs[0] == {"type": "meta", "address": "x"}
    assert [(r["dir"], r["hex"]) for r in recs[1:]] == [("tx", "dda5"), ("rx", "dd03")]
