"""Shared protocol samples: schema validity and the receiver rules."""

import json
from pathlib import Path

import jsonschema
import pytest

import cartdash_proto as proto

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "protocol" / "fixtures"
SCHEMA = json.loads((ROOT / "protocol" / "schema" / "cartdash.schema.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def lines(name):
    return (FIXTURES / name).read_bytes().split(b"\n")[:-1]  # every file ends with a newline


def test_schema_is_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize(
    "name", ["state_full.jsonl", "state_minimal.jsonl", "state_stale.jsonl", "hello.jsonl", "log.jsonl", "unknown.jsonl", "cmd.jsonl"]
)
def test_clean_fixtures_parse_and_validate(name):
    for raw in lines(name):
        msg = proto.parse_line(raw)
        assert msg is not None, raw
        VALIDATOR.validate(msg)


def test_garbage_fixture():
    raw = lines("garbage.jsonl")
    assert len(raw) == 12
    parsed = [proto.parse_line(r) for r in raw]
    kept = [(i + 1, m["type"], m.get("seq")) for i, m in enumerate(parsed) if m is not None]
    assert kept == [(1, "hello", None), (8, "state", 2), (12, "state", 3)]
    assert raw[11].endswith(b"\r")
    assert len(raw[10]) > proto.MAX_LINE_BYTES


def test_stale_and_null_fields_show_dashes():
    full = proto.parse_line(lines("state_full.jsonl")[0])
    assert proto.shown_value(full, "motor_temp_f") is None
    assert proto.shown_value(full, "speed_mph") == 14.2
    stale = proto.parse_line(lines("state_stale.jsonl")[0])
    for field in ("soc_pct", "pack_v", "pack_a", "power_kw", "motor_temp_f", "ctrl_temp_f"):
        assert proto.shown_value(stale, field) is None, field
    assert proto.shown_value(stale, "speed_mph") == 0.0
    assert proto.shown_value(stale, "bms_faults") == ["cell_uv"]
    minimal = proto.parse_line(lines("state_minimal.jsonl")[0])
    assert proto.shown_value(minimal, "soc_pct") is None


def test_unknown_type_is_returned_for_callers_to_ignore():
    msgs = [proto.parse_line(r) for r in lines("unknown.jsonl")]
    assert [m["type"] for m in msgs] == ["state", "telemetry2", "hello"]
    assert msgs[0]["speed_mph"] == 3.5 and msgs[0]["gear"] == "D"


def test_schema_rejects_bad_messages():
    bad = [
        {"type": "state", "seq": 1},
        {"type": "state", "seq": 1, "t": 2, "gear": "P"},
        {"type": "state", "seq": 1, "t": 2, "soc_pct": 140},
        {"type": "hello", "fw": "x", "uptime_s": 1},
        {"type": "log", "lvl": "info"},
        {"type": "log", "frame": "18ff50e5#01"},
        {"type": "cmd", "cmd": "set_config", "key": "wheel_dia_in"},
        {"type": "cmd", "cmd": "can_log", "on": "yes"},
    ]
    for msg in bad:
        assert not VALIDATOR.is_valid(msg), msg


def test_bool_is_not_an_int():
    assert proto.parse_line(b'{"type":"state","seq":true,"t":1}') is None


def test_check_config():
    assert proto.check_config("wheel_dia_in", 22.0) is None
    assert proto.check_config("wheel_dia_in", 22) is None
    assert proto.check_config("wheel_dia_in", True)
    assert proto.check_config("wheel_dia_in", -1)
    assert proto.check_config("speed_src", "gps")
    assert proto.check_config("sim", 1)
    assert proto.check_config("nope", 1)
