"""The firmware's simulated stream, built for the laptop, checked like fake_esp.

`pio run -e host` in firmware/ builds the program. This test is skipped when
it is not built. The firmware CI job builds it first.
"""

import json
import subprocess
from pathlib import Path

import jsonschema
import pytest

import cartdash_proto as proto

ROOT = Path(__file__).resolve().parents[2]
PROGRAM = ROOT / "firmware" / ".pio" / "build" / "host" / "program"
VALIDATOR = jsonschema.Draft202012Validator(json.loads((ROOT / "protocol" / "schema" / "cartdash.schema.json").read_text()))

pytestmark = pytest.mark.skipif(not PROGRAM.exists(), reason="firmware host build missing: cd firmware && pio run -e host")


@pytest.fixture(scope="module")
def stream():
    out = subprocess.run([str(PROGRAM), "120"], check=True, capture_output=True, timeout=60).stdout
    raw = out.split(b"\n")
    assert raw[-1] == b""
    return raw[:-1]


def test_every_line_parses_and_validates(stream):
    for line in stream:
        assert len(line) <= proto.MAX_LINE_BYTES
        msg = proto.parse_line(line)
        assert msg is not None, line
        VALIDATOR.validate(msg)


def test_rates_and_sequence(stream):
    msgs = [proto.parse_line(l) for l in stream]
    states = [m for m in msgs if m["type"] == "state"]
    hellos = [m for m in msgs if m["type"] == "hello"]
    assert len(states) == 1200
    assert [s["seq"] for s in states] == list(range(1200))
    assert [s["t"] for s in states] == list(range(100, 120001, 100))
    assert 119 <= len(hellos) <= 121
    assert all(h["proto"] == 1 and h["sim"] is True for h in hellos)
    assert msgs[0]["type"] == "hello"


def test_covers_the_dash_and_the_dash_path(stream):
    states = [m for m in map(proto.parse_line, stream) if m["type"] == "state"]
    assert "soc_pct" not in states[0]  # BMS still connecting
    assert "soc_pct" in states[-1]
    assert max(s["speed_mph"] for s in states) > 14
    assert any(s["turn_left"] for s in states) and any(s["turn_right"] for s in states)
    assert any(s["reverse"] and s["gear"] == "R" for s in states)
    assert any(s["illum"] for s in states) and any(not s["illum"] for s in states)
    assert any(s.get("pack_a", 0) > 0 for s in states), "no regen"
    stale = [s for s in states if "motor_temp_f" in s["stale"]]
    assert stale, "Kelly dropout never went stale"
    first = stale[0]["t"]
    assert first == 72000  # last Kelly reading at 69.9 s, more than 2 s old at 72.0 s
    assert all("soc_pct" not in s["stale"] for s in stale)
