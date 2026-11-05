import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import jsonschema
import pytest

import cartdash_proto as proto
import fake_esp

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "fake_esp.py"
VALIDATOR = jsonschema.Draft202012Validator(json.loads((ROOT / "protocol" / "schema" / "cartdash.schema.json").read_text()))


def run_sim(scenario, seconds=120.0, rate=10.0):
    """(t, silent, messages) for every tick, without sleeping."""
    sim = fake_esp.Sim(scenario, seed=3, rate_hz=rate)
    ticks = []
    for _ in range(int(seconds * rate)):
        msgs = sim.step(1.0 / rate)
        ticks.append((sim.t, sim.silent(), msgs))
    return ticks


def states(ticks):
    return [m for _, _, ms in ticks for m in ms if m["type"] == "state"]


@pytest.mark.parametrize("scenario", fake_esp.SCENARIOS)
def test_every_message_is_valid(scenario):
    ticks = run_sim(scenario)
    msgs = [m for _, _, ms in ticks for m in ms]
    for m in msgs:
        VALIDATOR.validate(m)
        assert proto.parse_line(proto.encode(m)) == m  # survives the wire
        assert len(proto.encode(m)) <= proto.MAX_LINE_BYTES
    st = states(ticks)
    assert len(st) == 1200
    assert [s["seq"] for s in st] == list(range(1200))
    hellos = [m for m in msgs if m["type"] == "hello"]
    assert 119 <= len(hellos) <= 121
    assert all(h["sim"] is True and h["proto"] == 1 for h in hellos)


def test_bms_fields_absent_until_connected():
    st = states(run_sim("drive", seconds=3))
    assert "soc_pct" not in st[0]
    assert "soc_pct" in st[-1]


def test_drive_covers_the_dash():
    st = states(run_sim("drive", seconds=120))
    assert max(s["speed_mph"] for s in st) > 14
    assert any(s["turn_left"] for s in st) and any(s["turn_right"] for s in st)
    assert any(s["brake"] for s in st) and any(s["park_brake"] for s in st)
    assert any(s["reverse"] and s["gear"] == "R" for s in st)
    assert any(s["illum"] for s in st) and any(not s["illum"] for s in st)
    assert any(s.get("pack_a", 0) > 0 for s in st), "no regen in the drive loop"
    assert all(not s["stale"] for s in st[30:])


def test_stale_scenario_marks_fields_stale_after_two_seconds():
    ticks = run_sim("stale", seconds=60)
    st = states(ticks)
    kelly_stale = [s for s in st if "motor_temp_f" in s["stale"]]
    bms_stale = [s for s in st if "soc_pct" in s["stale"]]
    assert kelly_stale and bms_stale
    first = kelly_stale[0]["t"] / 1000.0
    assert 17.0 <= first <= 17.3  # outage starts at 15 s, stale after 2 s more
    assert "motor_rpm" in kelly_stale[0]["stale"] and "soc_pct" not in kelly_stale[0]["stale"]


def test_regen_scenario_trips_the_warning_condition():
    st = states(run_sim("regen", seconds=30))
    assert any(s.get("pack_v", 0) > 71 and s.get("pack_a", 0) > 0 and s["speed_mph"] > 2 for s in st)


def test_charge_scenario():
    st = states(run_sim("charge", seconds=120))
    later = [s for s in st if "soc_pct" in s]
    assert all(s["speed_mph"] == 0 and s["pack_a"] > 0 for s in later)
    assert later[-1]["pack_v"] > later[0]["pack_v"] - 0.1


def test_faults_scenario():
    st = states(run_sim("faults", seconds=60))
    assert any(s.get("bms_faults") for s in st)
    assert any(s.get("kelly_faults") for s in st)
    assert any(s.get("bms_faults") == [] for s in st)


def test_dropout_scenario_goes_silent():
    ticks = run_sim("dropout", seconds=40)
    silent_t = [t for t, silent, _ in ticks if silent]
    first = [t for t in silent_t if t < 20]
    assert first and min(first) == pytest.approx(10.0, abs=0.01)
    assert max(first) == pytest.approx(12.9, abs=0.01)  # 3 s of silence, every 20 s
    assert min(t for t in silent_t if t >= 20) == pytest.approx(30.0, abs=0.01)


def test_commands():
    sim = fake_esp.Sim()
    ok = sim.handle({"type": "cmd", "cmd": "set_config", "key": "wheel_dia_in", "value": 20.5})
    assert ok[0]["lvl"] == "info" and sim.config["wheel_dia_in"] == 20.5
    bad = sim.handle({"type": "cmd", "cmd": "set_config", "key": "wheel_dia_in", "value": "big"})
    assert bad[0]["lvl"] == "warn" and sim.config["wheel_dia_in"] == 20.5
    assert sim.handle({"type": "cmd", "cmd": "reboot"})[0]["lvl"] == "warn"
    assert sim.handle({"type": "state", "seq": 1, "t": 1}) == []
    sim.handle({"type": "cmd", "cmd": "can_log", "on": True})
    frames = [m for m in sim.step(0.1) if m.get("tag") == "can"]
    assert frames
    for f in frames:
        VALIDATOR.validate(f)


def test_wheel_size_changes_rpm():
    a, b = fake_esp.Sim(), fake_esp.Sim()
    b.handle({"type": "cmd", "cmd": "set_config", "key": "wheel_dia_in", "value": 11.0})
    for _ in range(80):  # 8 s in, pulling away
        sa = a.step(0.1)[-1]
        sb = b.step(0.1)[-1]
    assert sb["motor_rpm"] == pytest.approx(2 * sa["motor_rpm"], rel=0.01)


def _start(args):
    proc = subprocess.Popen([sys.executable, str(SCRIPT), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc


def test_tcp_end_to_end():
    proc = _start(["--tcp", "127.0.0.1:0", "--duration", "4"])
    try:
        line = proc.stderr.readline().decode()
        port = int(re.search(r":(\d+)$", line.strip()).group(1))
        sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        f = sock.makefile("rb")
        sock.sendall(b'{"type":"cmd","cmd":"set_config","key":"gear_ratio","value":11.5}\n')
        got = []
        deadline = time.time() + 1.5
        while time.time() < deadline:
            raw = f.readline()
            if not raw:
                break
            msg = proto.parse_line(raw)
            assert msg is not None, raw
            got.append(msg)
        sock.close()
    finally:
        proc.wait(timeout=10)
    assert got[0]["type"] == "hello"  # greeting on connect
    assert sum(1 for m in got if m["type"] == "state") >= 10
    acks = [m for m in got if m["type"] == "log" and m.get("tag") == "cmd"]
    assert acks and acks[0]["msg"] == "set_config gear_ratio=11.5 ok"


def test_stdout_mode():
    out = subprocess.run([sys.executable, str(SCRIPT), "--stdout", "--duration", "1.2", "--scenario", "stale"],
                         capture_output=True, timeout=20).stdout
    msgs = [proto.parse_line(r) for r in out.splitlines()]
    assert all(m is not None for m in msgs)
    assert msgs[0]["type"] == "hello"
    assert sum(1 for m in msgs if m["type"] == "state") >= 9


@pytest.mark.skipif(not hasattr(os, "openpty"), reason="needs a pty")
def test_pty_mode(tmp_path):
    link = tmp_path / "ttyCARTDASH"
    proc = _start(["--pty", "--link", str(link), "--duration", "3"])
    try:
        proc.stderr.readline()
        deadline = time.time() + 3
        while not link.exists() and time.time() < deadline:
            time.sleep(0.05)
        fd = os.open(link, os.O_RDWR | os.O_NOCTTY)
        os.write(fd, b'{"type":"cmd","cmd":"can_log","on":true}\n')
        data = b""
        deadline = time.time() + 1.5
        while time.time() < deadline and data.count(b"\n") < 20:
            data += os.read(fd, 4096)
        os.close(fd)
    finally:
        proc.wait(timeout=10)
    msgs = [proto.parse_line(r) for r in data.splitlines()]
    msgs = [m for m in msgs if m]
    assert any(m["type"] == "state" for m in msgs)
