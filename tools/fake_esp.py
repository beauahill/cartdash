#!/usr/bin/env python3
"""Pretend to be the Cart Dash ESP32.

Streams the same JSON lines as the firmware (docs/usb_protocol.md): state at
10 Hz, hello once a second, and log lines. Answers cmd lines the way the
firmware does.

Outputs:
    --tcp [HOST:]PORT   TCP server. The Android emulator reaches the host at
                        10.0.2.2, so the app's TcpSource uses 10.0.2.2:5555.
    --pty               a virtual serial port (Linux and macOS). Prints its
                        path; --link makes a stable symlink to it.
    --stdout            print lines, for piping into other tools

Scenarios (--scenario):
    drive    60 s loop: pull away, cruise, blinkers, regen, brake, park, reverse.
             Every other loop is at night (illum and low beam on).
    charge   parked on the charger, SOC climbing
    regen    nearly full pack coasting downhill: regen current above 71 V,
             which must raise the app's regen warning
    faults   drive, plus BMS and Kelly faults coming and going
    stale    drive, plus Kelly and BMS data dropping out long enough to go stale
    dropout  drive, but the whole stream stops for 3 s every 20 s (link lost)

Examples:
    python3 tools/fake_esp.py --tcp 5555
    python3 tools/fake_esp.py --tcp 5555 --scenario regen
    python3 tools/fake_esp.py --pty --link /tmp/ttyCARTDASH
    python3 tools/fake_esp.py --stdout --duration 5 | head
    python3 tools/fake_esp.py --tcp 5555 --replay recorded.jsonl --loop
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cartdash_proto as proto  # noqa: E402

FW_VERSION = "fake-0.1.0"
SCENARIOS = ("drive", "charge", "regen", "faults", "stale", "dropout")

DEFAULT_CONFIG: Dict[str, Any] = {
    "wheel_dia_in": 22.0,  # placeholder, same as the firmware until measured
    "gear_ratio": 12.0,  # placeholder
    "speed_src": "rpm",
    "pulses_per_rev": 1.0,
    "sim": True,
}

BMS_FIELDS = ("soc_pct", "pack_v", "pack_a", "power_kw", "cell_v_min", "cell_v_max", "bms_temp_f", "bms_faults")
KELLY_FIELDS = ("ctrl_temp_f", "motor_temp_f", "motor_rpm", "kelly_faults")
INPUT_FIELDS = (
    "speed_mph",
    "gear",
    "speed_mode",
    "turn_left",
    "turn_right",
    "low_beam",
    "high_beam",
    "brake",
    "park_brake",
    "reverse",
    "illum",
)

# Resting LiFePO4 cell voltage by state of charge.
_OCV = [(0, 2.90), (5, 3.10), (10, 3.20), (20, 3.25), (40, 3.29), (60, 3.31), (80, 3.33), (90, 3.34), (100, 3.40)]
CELLS = 20
PACK_AH = 130.0
PACK_OHMS = 0.015


def cell_ocv(soc: float) -> float:
    soc = min(max(soc, 0.0), 100.0)
    for (s0, v0), (s1, v1) in zip(_OCV, _OCV[1:]):
        if soc <= s1:
            return v0 + (v1 - v0) * (soc - s0) / (s1 - s0)
    return _OCV[-1][1]


def drive_cycle(tc: float) -> Dict[str, Any]:
    """Driver inputs and speed for a 60 s loop. tc is seconds into the loop."""
    d: Dict[str, Any] = {
        "mph": 0.0,
        "amps": -2.0,
        "gear": "D",
        "brake": False,
        "park": False,
        "left": False,
        "right": False,
        "reverse": False,
    }
    if tc < 2:
        d["brake"] = True
    elif tc < 12:  # pull away
        d["mph"] = 15.0 * (tc - 2) / 10
        d["amps"] = -60.0 - 6.0 * d["mph"]
    elif tc < 30:  # cruise, right blinker for a lane change
        d["mph"] = 15.0 + 0.4 * math.sin(tc)
        d["amps"] = -(20.0 + 1.8 * d["mph"])
        d["right"] = 18 <= tc < 23
    elif tc < 36:  # lift off, regen
        d["mph"] = 15.0 - 7.0 * (tc - 30) / 6
        d["amps"] = 18.0
    elif tc < 44:  # slow cruise, left blinker to turn
        d["mph"] = 8.0
        d["amps"] = -(20.0 + 1.8 * 8.0)
        d["left"] = 37 <= tc < 42
    elif tc < 50:  # brake to a stop
        d["mph"] = 8.0 * (50 - tc) / 6
        d["amps"] = 10.0
        d["brake"] = True
    elif tc < 56:  # parked
        d["park"] = tc >= 52
        d["brake"] = tc < 52
    elif tc < 59:  # back up
        d["gear"] = "R"
        d["reverse"] = True
        d["mph"] = 2.0
        d["amps"] = -25.0
    return d


class Sim:
    """Simulated cart. step() advances time and returns the messages for that tick."""

    def __init__(self, scenario: str = "drive", seed: int = 1, rate_hz: float = 10.0):
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}")
        self.scenario = scenario
        self.rng = random.Random(seed)
        self.rate_hz = rate_hz
        self.t_ms = 0  # whole milliseconds since boot, so long runs do not drift
        self.seq = 0
        self.config = dict(DEFAULT_CONFIG)
        self.can_log = False
        self._last_hello_s = -1
        self.soc = {"charge": 41.0, "regen": 99.0}.get(scenario, 82.0)
        self.ctrl_temp = 95.0
        self.motor_temp = 105.0
        self.values: Dict[str, Any] = {}
        self.updated: Dict[str, float] = {}

    @property
    def t(self) -> float:
        """Seconds since boot."""
        return self.t_ms / 1000.0

    # Time based behavior ----------------------------------------------------

    def silent(self) -> bool:
        """True while the dropout scenario holds the whole stream back."""
        return self.scenario == "dropout" and 10.0 <= self.t % 20.0 < 13.0

    def _kelly_online(self) -> bool:
        if self.t < 0.3:
            return False
        return not (self.scenario == "stale" and 15.0 <= self.t % 60.0 < 25.0)

    def _bms_online(self) -> bool:
        if self.t < 1.5:  # BLE still connecting after boot
            return False
        return not (self.scenario == "stale" and 40.0 <= self.t % 60.0 < 48.0)

    # Model -----------------------------------------------------------------

    def _inputs(self) -> Dict[str, Any]:
        if self.scenario == "charge":
            return {"mph": 0.0, "amps": 40.0, "gear": "N", "brake": False, "park": True,
                    "left": False, "right": False, "reverse": False}
        if self.scenario == "regen":
            tc = self.t % 30.0
            downhill = 5.0 <= tc < 25.0
            return {"mph": 12.0 if downhill else 6.0 * min(tc, 5.0) / 5.0, "amps": 30.0 if downhill else -40.0,
                    "gear": "D", "brake": False, "park": False, "left": False, "right": False, "reverse": False}
        return drive_cycle(self.t % 60.0)

    def _set(self, field: str, value: Any) -> None:
        self.values[field] = value
        self.updated[field] = self.t

    def _model(self, dt: float) -> None:
        d = self._inputs()
        night = int(self.t // 60.0) % 2 == 1
        amps = d["amps"] + self.rng.uniform(-0.6, 0.6)
        self.soc = min(100.0, max(0.0, self.soc + amps * dt / 3600.0 / PACK_AH * 100.0))
        if self.scenario == "regen":
            # Surface charge right after a full charge keeps the voltage high; regen pushes it past 71 V.
            pack_v = 70.6 + 0.035 * max(amps, 0.0) + 0.01 * min(amps, 0.0)
        else:
            pack_v = CELLS * cell_ocv(self.soc) + amps * PACK_OHMS
            if amps > 5 and self.scenario == "charge":
                pack_v += 0.06 * CELLS  # charge voltage sits above resting voltage
        load = abs(min(amps, 0.0))
        self.ctrl_temp += (95.0 + load * 0.12 - self.ctrl_temp) * dt / 120.0
        self.motor_temp += (100.0 + load * 0.25 - self.motor_temp) * dt / 300.0

        cfg = self.config
        wheel_rpm = d["mph"] * 63360.0 / 60.0 / (math.pi * float(cfg["wheel_dia_in"]))
        motor_rpm = wheel_rpm * float(cfg["gear_ratio"])

        tc = self.t % 60.0
        self._set("speed_mph", round(d["mph"], 1))
        self._set("gear", d["gear"])
        self._set("speed_mode", "high")
        self._set("turn_left", bool(d["left"]))
        self._set("turn_right", bool(d["right"]))
        self._set("low_beam", night)
        self._set("high_beam", False)
        self._set("brake", bool(d["brake"]))
        self._set("park_brake", bool(d["park"]))
        self._set("reverse", bool(d["reverse"]))
        self._set("illum", night)

        if self._kelly_online():
            self._set("ctrl_temp_f", round(self.ctrl_temp))
            self._set("motor_temp_f", round(self.motor_temp))
            self._set("motor_rpm", round(motor_rpm))
            faulty = self.scenario == "faults" and 40.0 <= tc < 50.0
            self._set("kelly_faults", ["motor_overtemp"] if faulty else [])

        if self._bms_online():
            cell = pack_v / CELLS
            spread = 0.004 + self.rng.uniform(0.0, 0.003)
            self._set("soc_pct", round(self.soc))
            self._set("pack_v", round(pack_v, 2))
            self._set("pack_a", round(amps, 1))
            self._set("power_kw", round(pack_v * amps / 1000.0, 2))
            self._set("cell_v_min", round(cell - spread / 2, 3))
            self._set("cell_v_max", round(cell + spread / 2, 3))
            self._set("bms_temp_f", [78 + round(load / 60), 80 + round(load / 50)])
            faulty = self.scenario == "faults" and 20.0 <= tc < 30.0 and int(self.t // 60.0) % 2 == 0
            self._set("bms_faults", ["cell_ov"] if faulty else [])

    # Messages --------------------------------------------------------------

    def hello(self) -> Dict[str, Any]:
        return {"type": "hello", "proto": proto.PROTO_VERSION, "fw": FW_VERSION,
                "uptime_s": int(self.t), "sim": bool(self.config.get("sim", True))}

    def state(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"type": "state", "seq": self.seq & 0xFFFFFFFF, "t": self.t_ms & 0xFFFFFFFF}
        self.seq += 1
        msg.update(self.values)
        msg["stale"] = sorted(f for f, ts in self.updated.items() if self.t - ts > proto.STALE_AFTER_S)
        return msg

    def can_frames(self) -> List[Dict[str, Any]]:
        rpm = int(self.values.get("motor_rpm", 0)) & 0xFFFF
        amps10 = int(round(float(self.values.get("pack_a", 0.0)) * 10)) & 0xFFFF
        data = bytes([rpm & 0xFF, rpm >> 8, amps10 & 0xFF, amps10 >> 8, 0, 0, self.seq & 0xFF, 0])
        return [{"type": "log", "lvl": "debug", "tag": "can", "t": self.t_ms & 0xFFFFFFFF, "frame": f"0CF11E05#{data.hex().upper()}"}]

    def step(self, dt: float) -> List[Dict[str, Any]]:
        step_ms = max(1, int(round(dt * 1000)))
        self.t_ms += step_ms
        self._model(step_ms / 1000.0)
        out: List[Dict[str, Any]] = []
        if int(self.t) != self._last_hello_s:
            self._last_hello_s = int(self.t)
            out.append(self.hello())
        out.append(self.state())
        if self.can_log:
            out.extend(self.can_frames())
        return out

    def handle(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Reply to one message from the app, the way the firmware does."""
        if msg.get("type") != "cmd":
            return []
        cmd = msg.get("cmd")
        if cmd == "set_config":
            key, value = msg.get("key"), msg.get("value")
            problem = proto.check_config(key, value)
            if problem:
                return [_log("warn", "cmd", f"set_config rejected: {problem}")]
            self.config[key] = value
            return [_log("info", "cmd", f"set_config {key}={json.dumps(value)} ok")]
        if cmd == "can_log":
            on = msg.get("on")
            if not isinstance(on, bool):
                return [_log("warn", "cmd", "can_log rejected: on must be true or false")]
            self.can_log = on
            return [_log("info", "cmd", f"can_log {'on' if on else 'off'} ok")]
        return [_log("warn", "cmd", f"unknown cmd {cmd!r}")]


def _log(lvl: str, tag: str, text: str) -> Dict[str, Any]:
    return {"type": "log", "lvl": lvl, "tag": tag, "msg": text}


# Producers -------------------------------------------------------------------

Emit = Callable[[bytes], None]


class SimProducer:
    def __init__(self, sim: Sim, rate_hz: float, speedup: float):
        self.sim = sim
        self.period = 1.0 / rate_hz
        self.speedup = speedup

    def greeting(self) -> List[bytes]:
        return [proto.encode(self.sim.hello())]

    def handle(self, msg: Dict[str, Any]) -> List[bytes]:
        return [proto.encode(m) for m in self.sim.handle(msg)]

    async def run(self, emit: Emit, duration: Optional[float]) -> None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        n = 0
        while duration is None or loop.time() - start < duration:
            n += 1
            await asyncio.sleep(max(0.0, start + n * self.period - loop.time()))
            msgs = self.sim.step(self.period * self.speedup)
            if self.sim.silent():
                continue
            for m in msgs:
                emit(proto.encode(m))


class ReplayProducer:
    """Replays a recorded .jsonl stream, paced by the `t` (state) and `uptime_s` (hello) fields."""

    def __init__(self, path: Path, loop: bool, speedup: float):
        self.lines = [ln if ln.endswith(b"\n") else ln + b"\n" for ln in Path(path).read_bytes().splitlines()]
        self.loop = loop
        self.speedup = speedup

    def greeting(self) -> List[bytes]:
        return []

    def handle(self, msg: Dict[str, Any]) -> List[bytes]:
        if msg.get("type") == "cmd":
            return [proto.encode(_log("warn", "cmd", "replay mode, command ignored"))]
        return []

    async def run(self, emit: Emit, duration: Optional[float]) -> None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        while True:
            last_ms: Optional[int] = None
            for line in self.lines:
                if duration is not None and loop.time() - start >= duration:
                    return
                msg = proto.parse_line(line)
                t_ms = None
                if msg and msg.get("type") == "state":
                    t_ms = msg["t"]
                if t_ms is not None:
                    if last_ms is not None and t_ms > last_ms:
                        await asyncio.sleep(min((t_ms - last_ms) / 1000.0 / self.speedup, 5.0))
                    last_ms = t_ms
                emit(line)
            if not self.loop:
                return
            await asyncio.sleep(0.1)


# Transports ------------------------------------------------------------------


async def serve_tcp(producer, host: str, port: int, duration: Optional[float]) -> None:
    clients: List[asyncio.StreamWriter] = []

    def emit(data: bytes) -> None:
        for w in list(clients):
            if w.transport.get_write_buffer_size() > 256 * 1024:
                continue  # client is not reading; drop rather than buffer forever
            w.write(data)

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        print(f"client connected: {peer}", file=sys.stderr, flush=True)
        clients.append(writer)
        for line in producer.greeting():
            writer.write(line)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                msg = proto.parse_line(line)
                if msg is None:
                    continue
                if msg.get("type") == "cmd":
                    print(f"cmd from {peer}: {json.dumps(msg)}", file=sys.stderr, flush=True)
                for reply in producer.handle(msg):
                    writer.write(reply)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            if writer in clients:
                clients.remove(writer)
            writer.close()
            print(f"client disconnected: {peer}", file=sys.stderr, flush=True)

    server = await asyncio.start_server(on_client, host, port)
    real_port = server.sockets[0].getsockname()[1]
    print(f"listening on {host}:{real_port}", file=sys.stderr, flush=True)
    if host in ("127.0.0.1", "0.0.0.0", "localhost"):
        print(f"Android emulator: connect to 10.0.2.2:{real_port}", file=sys.stderr, flush=True)
    async with server:
        await producer.run(emit, duration)
        for w in list(clients):
            w.close()


async def serve_pty(producer, link: Optional[str], duration: Optional[float]) -> None:
    import tty

    master, slave = os.openpty()
    tty.setraw(slave)
    os.set_blocking(master, False)
    name = os.ttyname(slave)
    if link:
        try:
            os.remove(link)
        except FileNotFoundError:
            pass
        os.symlink(name, link)
    print(f"virtual serial port: {name}" + (f" (also {link})" if link else ""), file=sys.stderr, flush=True)

    def emit(data: bytes) -> None:
        try:
            os.write(master, data)
        except (BlockingIOError, OSError):
            pass  # nobody is reading; drop

    buf = bytearray()

    def on_readable() -> None:
        try:
            chunk = os.read(master, 4096)
        except (BlockingIOError, OSError):
            return
        buf.extend(chunk)
        while b"\n" in buf:
            line, _, rest = bytes(buf).partition(b"\n")
            buf[:] = rest
            msg = proto.parse_line(line)
            if msg is not None:
                for reply in producer.handle(msg):
                    emit(reply)

    loop = asyncio.get_running_loop()
    loop.add_reader(master, on_readable)
    try:
        await producer.run(emit, duration)
    finally:
        loop.remove_reader(master)
        os.close(master)
        os.close(slave)
        if link:
            try:
                os.remove(link)
            except OSError:
                pass


async def serve_stdout(producer, duration: Optional[float]) -> None:
    out = sys.stdout.buffer

    def emit(data: bytes) -> None:
        try:
            out.write(data)
            out.flush()
        except BrokenPipeError:
            raise SystemExit(0)

    await producer.run(emit, duration)


def parse_hostport(text: str) -> Tuple[str, int]:
    if ":" in text:
        host, _, port = text.rpartition(":")
        return host or "127.0.0.1", int(port)
    return "127.0.0.1", int(text)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    out = p.add_mutually_exclusive_group(required=True)
    out.add_argument("--tcp", metavar="[HOST:]PORT", help="serve over TCP (default host 127.0.0.1)")
    out.add_argument("--pty", action="store_true", help="create a virtual serial port")
    out.add_argument("--stdout", action="store_true", help="print lines to stdout")
    p.add_argument("--link", help="with --pty, also create this symlink to the port")
    p.add_argument("--scenario", choices=SCENARIOS, default="drive")
    p.add_argument("--replay", metavar="FILE", help="replay a recorded .jsonl stream instead of simulating")
    p.add_argument("--loop", action="store_true", help="with --replay, start over at the end")
    p.add_argument("--rate", type=float, default=10.0, help="state messages per second (default 10)")
    p.add_argument("--speedup", type=float, default=1.0, help="run simulated time this many times faster")
    p.add_argument("--duration", type=float, help="stop after this many seconds")
    p.add_argument("--seed", type=int, default=1)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.replay:
        producer = ReplayProducer(Path(args.replay), args.loop, args.speedup)
    else:
        producer = SimProducer(Sim(args.scenario, args.seed, args.rate), args.rate, args.speedup)

    if args.tcp:
        host, port = parse_hostport(args.tcp)
        coro = serve_tcp(producer, host, port, args.duration)
    elif args.pty:
        coro = serve_pty(producer, args.link, args.duration)
    else:
        coro = serve_stdout(producer, args.duration)
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
