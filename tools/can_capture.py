#!/usr/bin/env python3
"""Labeled, listen-only CAN captures with keyboard markers.

Linux and SocketCAN only (a candleLight adapter shows up as can0). The tool
refuses to capture unless the kernel reports the interface in listen-only
mode, so nothing can ever be transmitted on the bus being sniffed.

Commands:
    check     show the interface state and whether it is safe to capture
    setup     put the interface in listen-only mode at a bitrate (uses sudo)
    scan      try several bitrates and report which one sees clean traffic
    capture   record a session: frames, typed markers, and metadata

Typical use (see tools/README.md for the full session list):
    python3 tools/can_capture.py scan
    python3 tools/can_capture.py capture --label gear-dnr --steps "D,N,R,D"

While capturing, type a note and press Enter at the moment something happens.
Pressing Enter on an empty line stamps the next --steps entry, or "mark N".
Readings typed as key=value (for example "v=66.4 a=-48") become measured
series that the analyzer tries to match to CAN bytes.
Type :s for stats, :q (or Ctrl-C) to stop.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canlog  # noqa: E402

TOOL_VERSION = "0.1.0"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "captures"
DEFAULT_BITRATES = [250000, 500000, 125000, 1000000]


# Interface state ---------------------------------------------------------


@dataclass
class IfaceInfo:
    exists: bool
    kind: Optional[str] = None  # "can" for real adapters, "vcan" for virtual ones
    up: bool = False
    listen_only: bool = False
    bitrate: Optional[int] = None
    state: Optional[str] = None  # ERROR-ACTIVE, ERROR-PASSIVE, BUS-OFF, STOPPED
    modes: List[str] = field(default_factory=list)

    @property
    def is_virtual(self) -> bool:
        return self.kind == "vcan"

    @property
    def is_can(self) -> bool:
        return self.kind in ("can", "vcan")


def parse_ip_json(text: str) -> IfaceInfo:
    """Parse `ip -details -json link show dev X` output."""
    data = json.loads(text)
    if not data:
        return IfaceInfo(exists=False)
    d = data[0]
    info = IfaceInfo(exists=True)
    info.up = "UP" in (d.get("flags") or [])
    linkinfo = d.get("linkinfo") or {}
    info.kind = linkinfo.get("info_kind") or ("can" if d.get("link_type") == "can" else None)
    idata = linkinfo.get("info_data") or {}
    ctrl = idata.get("ctrlmode") or []
    if isinstance(ctrl, dict):
        modes = [str(k).upper() for k, v in ctrl.items() if v]
    else:
        modes = [str(m).upper() for m in ctrl]
    info.modes = modes
    info.listen_only = "LISTEN-ONLY" in modes
    bt = idata.get("bittiming") or {}
    if bt.get("bitrate"):
        info.bitrate = int(bt["bitrate"])
    info.state = idata.get("state")
    return info


def parse_ip_text(text: str) -> IfaceInfo:
    """Parse plain `ip -details link show dev X` output (older iproute2)."""
    if not text.strip():
        return IfaceInfo(exists=False)
    info = IfaceInfo(exists=True)
    m = re.search(r"<([^>]*)>", text)
    if m:
        info.up = "UP" in m.group(1).split(",")
    if re.search(r"^\s*vcan\b", text, re.M):
        info.kind = "vcan"
    elif "link/can" in text:
        info.kind = "can"
    m = re.search(r"^\s*can\s+(?:<([^>]*)>\s+)?state\s+(\S+)", text, re.M)
    if m:
        info.modes = [s.upper() for s in (m.group(1) or "").split(",") if s]
        info.listen_only = "LISTEN-ONLY" in info.modes
        info.state = m.group(2)
    m = re.search(r"\bbitrate\s+(\d+)", text)
    if m:
        info.bitrate = int(m.group(1))
    return info


def query_iface(channel: str) -> IfaceInfo:
    if shutil.which("ip") is None:
        raise SystemExit("The `ip` command was not found. This tool needs Linux with iproute2.")
    r = subprocess.run(["ip", "-details", "-json", "link", "show", "dev", channel], capture_output=True, text=True)
    if r.returncode != 0:
        return IfaceInfo(exists=False)
    try:
        return parse_ip_json(r.stdout)
    except ValueError:
        r = subprocess.run(["ip", "-details", "link", "show", "dev", channel], capture_output=True, text=True)
        return parse_ip_text(r.stdout) if r.returncode == 0 else IfaceInfo(exists=False)


def _ip_set(channel: str, args: Sequence[str]) -> subprocess.CompletedProcess:
    cmd = ["ip", "link", "set", channel, *args]
    if os.geteuid() != 0:
        cmd = ["sudo", *cmd]
    return subprocess.run(cmd, capture_output=True, text=True)


def setup_iface(channel: str, bitrate: int, log: Callable[[str], None] = print) -> IfaceInfo:
    """Bring the interface up in listen-only mode at `bitrate`. Uses sudo when not root."""
    info = query_iface(channel)
    if not info.exists:
        raise SystemExit(f"{channel} not found. Is the adapter plugged in? Try `ip link` to list interfaces.")
    if info.is_virtual:
        log(f"{channel} is a virtual CAN interface; bitrate and listen-only do not apply.")
        if not info.up:
            _ip_set(channel, ["up"])
        return query_iface(channel)

    _ip_set(channel, ["down"])
    r = _ip_set(channel, ["type", "can", "bitrate", str(bitrate), "listen-only", "on", "berr-reporting", "on"])
    if r.returncode != 0:
        # Some adapters do not support bus error reporting. Listen-only is the part that matters.
        r = _ip_set(channel, ["type", "can", "bitrate", str(bitrate), "listen-only", "on"])
    if r.returncode != 0:
        raise SystemExit(f"Could not configure {channel}: {r.stderr.strip() or r.stdout.strip()}")
    r = _ip_set(channel, ["up"])
    if r.returncode != 0:
        raise SystemExit(f"Could not bring {channel} up: {r.stderr.strip()}")
    info = query_iface(channel)
    if not info.listen_only:
        _ip_set(channel, ["down"])
        raise SystemExit(f"{channel} did not report listen-only mode after setup, so it was taken down. Check the adapter firmware.")
    return info


def describe(info: IfaceInfo, channel: str) -> str:
    if not info.exists:
        return f"{channel}: not found"
    parts = [f"{channel}: kind={info.kind or '?'}", "up" if info.up else "DOWN"]
    if not info.is_virtual:
        parts.append(f"bitrate={info.bitrate or '?'}")
        parts.append("listen-only" if info.listen_only else "NOT listen-only")
        parts.append(f"state={info.state or '?'}")
    return ", ".join(parts)


def capture_blockers(info: IfaceInfo, channel: str) -> List[str]:
    """Reasons the interface is not safe or not ready to capture from. Empty means OK."""
    if not info.exists:
        return [f"{channel} not found. Plug in the adapter and check `ip link`."]
    problems = []
    if not info.is_can:
        problems.append(f"{channel} is not a CAN interface.")
    if not info.is_virtual and not info.listen_only:
        problems.append(f"{channel} is not in listen-only mode. Run: python3 tools/can_capture.py setup --bitrate <rate>")
    if not info.up:
        problems.append(f"{channel} is down. Run: python3 tools/can_capture.py setup --bitrate <rate>")
    return problems


# Recording ---------------------------------------------------------------


def frame_from_message(msg) -> canlog.Frame:
    return canlog.Frame(
        t=float(msg.timestamp) if msg.timestamp else time.time(),
        can_id=int(msg.arbitration_id),
        ext=bool(msg.is_extended_id),
        data=bytes(msg.data or b""),
        err=bool(msg.is_error_frame),
        rtr=bool(msg.is_remote_frame),
        dlc=int(msg.dlc or 0),
    )


class Recorder:
    """Writes frames and markers for one session and keeps running stats."""

    def __init__(self, session_dir: Path, channel: str, steps: Optional[Sequence[str]] = None, t0: Optional[float] = None):
        self.dir = Path(session_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.channel = channel
        self.t0 = time.time() if t0 is None else t0
        self.log_path = self.dir / canlog.LOG_NAME
        self._log = open(self.log_path, "w", buffering=1, encoding="utf-8")
        self._markers = canlog.MarkerWriter(self.dir / canlog.MARKERS_NAME, self.t0)
        self._lock = threading.Lock()
        self.steps: List[str] = [s.strip() for s in (steps or []) if s.strip()]
        self.markers: List[canlog.Marker] = []
        self.frames = 0
        self.errors = 0
        self.ids: Counter = Counter()
        self.first_frame_t: Optional[float] = None
        self.last_frame_t: Optional[float] = None

    def on_message(self, msg) -> None:
        self.on_frame(frame_from_message(msg))

    def on_frame(self, frame: canlog.Frame) -> None:
        self._log.write(canlog.format_candump(frame, self.channel) + "\n")
        if frame.err:
            self.errors += 1
        else:
            self.frames += 1
            self.ids[frame.ident] += 1
        if self.first_frame_t is None:
            self.first_frame_t = frame.t
        self.last_frame_t = frame.t

    def next_step(self) -> Optional[str]:
        with self._lock:
            return self.steps[0] if self.steps else None

    def mark(self, label: Optional[str] = None, t: Optional[float] = None) -> canlog.Marker:
        t = time.time() if t is None else t
        with self._lock:
            if not label:
                label = self.steps.pop(0) if self.steps else f"mark {len(self.markers) + 1}"
            elif self.steps and label == self.steps[0]:
                self.steps.pop(0)
            marker = canlog.Marker(t=t, label=label)
            self.markers.append(marker)
            self._markers.add(marker)
        return marker

    def status_line(self, now: Optional[float] = None) -> str:
        now = time.time() if now is None else now
        elapsed = max(now - self.t0, 1e-9)
        line = (
            f"[{elapsed:7.1f} s] {self.frames:,} frames ({self.frames / elapsed:,.0f}/s), "
            f"{len(self.ids)} IDs, {self.errors} error frames, {len(self.markers)} markers"
        )
        nxt = self.next_step()
        if nxt:
            line += f". Next step: {nxt}"
        return line

    def close(self, compress: bool = True) -> Path:
        self._log.close()
        self._markers.close()
        if not compress:
            return self.log_path
        gz_path = self.dir / canlog.LOG_GZ_NAME
        with open(self.log_path, "rb") as src, gzip.open(gz_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        self.log_path.unlink()
        self.log_path = gz_path
        return gz_path


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text.strip()).strip("-").lower()
    return s or "session"


def make_session_dir(out_dir: Path, bus_name: str, label: str, when: Optional[dt.datetime] = None) -> Path:
    when = when or dt.datetime.now()
    base = Path(out_dir) / slug(bus_name) / f"{when:%Y%m%d-%H%M%S}_{slug(label)}"
    path = base
    n = 2
    while path.exists():
        path = base.with_name(f"{base.name}-{n}")
        n += 1
    path.mkdir(parents=True)
    return path


def write_meta(path: Path, meta: dict) -> None:
    (Path(path) / canlog.META_NAME).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stdin_markers(rec: Recorder, stop: threading.Event, out: Callable[[str], None] = print) -> None:
    """Read marker lines from the keyboard until stdin closes or :q is typed."""
    try:
        _read_markers(rec, stop, out)
    except (OSError, ValueError):
        out("  (keyboard input unavailable; markers disabled for this capture)")


def _read_markers(rec: Recorder, stop: threading.Event, out: Callable[[str], None]) -> None:
    for line in sys.stdin:
        t = time.time()  # stamp at the moment Enter was pressed
        text = line.strip()
        if text in (":q", ":quit", ":stop"):
            stop.set()
            return
        if text in (":s", ":stats"):
            out(rec.status_line())
            continue
        m = rec.mark(text or None, t)
        msg = f"  marker {len(rec.markers)} at {m.t - rec.t0:.1f} s: {m.label}"
        nxt = rec.next_step()
        if nxt:
            msg += f"   (next: {nxt})"
        out(msg)
        if stop.is_set():
            return


def record(
    bus,
    rec: Recorder,
    stop: threading.Event,
    duration: Optional[float] = None,
    status_every: float = 10.0,
    out: Callable[[str], None] = print,
) -> None:
    """Receive frames into `rec` until `stop` is set, `duration` passes, or Ctrl-C.

    `bus` is a python-can bus. This function only ever calls recv(); it never sends.
    """
    next_status = time.time() + status_every if status_every else None
    try:
        while not stop.is_set():
            try:
                msg = bus.recv(timeout=0.2)
            except Exception as exc:  # adapter unplugged or interface taken down
                out(f"Bus error, stopping: {exc}. Everything received so far is saved.")
                break
            if msg is not None:
                rec.on_message(msg)
            now = time.time()
            if duration is not None and now - rec.t0 >= duration:
                break
            if next_status is not None and now >= next_status:
                out(rec.status_line(now))
                next_status = now + status_every
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


def open_bus(interface: str, channel: str):
    import can

    # receive_own_messages is irrelevant because nothing is ever sent, but keep it off.
    return can.Bus(interface=interface, channel=channel, receive_own_messages=False)


# Commands ----------------------------------------------------------------


def cmd_check(args) -> int:
    info = query_iface(args.channel)
    print(describe(info, args.channel))
    problems = capture_blockers(info, args.channel)
    for p in problems:
        print("  " + p)
    if not problems:
        print("  Ready to capture.")
    return 1 if problems else 0


def cmd_setup(args) -> int:
    info = setup_iface(args.channel, args.bitrate)
    print(describe(info, args.channel))
    return 0


@dataclass
class ScanResult:
    bitrate: int
    frames: int
    errors: int
    ids: int
    state: Optional[str]


def pick_bitrate(results: Sequence[ScanResult]) -> Optional[ScanResult]:
    """Best bitrate: clean frames with the fewest errors. None if every rate was silent."""
    seen = [r for r in results if r.frames > 0]
    if not seen:
        return None
    return max(seen, key=lambda r: (r.frames / (r.frames + r.errors), r.frames))


def cmd_scan(args) -> int:
    bitrates = [int(b) for b in args.bitrates.split(",") if b.strip()]
    print(f"Listening {args.seconds:g} s at each bitrate on {args.channel} (listen-only, nothing is sent).")
    results: List[ScanResult] = []
    for br in bitrates:
        setup_iface(args.channel, br, log=lambda s: None)
        bus = open_bus("socketcan", args.channel)
        frames = errors = 0
        ids = set()
        end = time.monotonic() + args.seconds
        try:
            while time.monotonic() < end:
                msg = bus.recv(timeout=0.1)
                if msg is None:
                    continue
                if msg.is_error_frame:
                    errors += 1
                else:
                    frames += 1
                    ids.add(canlog.format_id(msg.arbitration_id, msg.is_extended_id))
        finally:
            bus.shutdown()
        state = query_iface(args.channel).state
        results.append(ScanResult(br, frames, errors, len(ids), state))
        print(f"  {br:>8}: {frames:6} frames, {errors:6} error frames, {len(ids):3} IDs, state {state}")

    best = pick_bitrate(results)
    if best is None:
        print("No frames at any bitrate. Check: key on, probes on CANH/CANL (not swapped), adapter ground to 12V ground.")
        return 1
    setup_iface(args.channel, best.bitrate, log=lambda s: None)
    print(f"Best: {best.bitrate}. {args.channel} is now listening at that rate.")
    if best.errors:
        print("  Some error frames at the best rate. Check probe contact and that CANH/CANL are not swapped.")
    return 0


def cmd_capture(args) -> int:
    channel = args.channel
    bitrate = None
    listen_only = False
    if args.interface == "socketcan":
        if args.setup:
            setup_iface(channel, args.setup)
        info = query_iface(channel)
        problems = capture_blockers(info, channel)
        if problems:
            print("Not capturing:")
            for p in problems:
                print("  " + p)
            return 2
        bitrate = info.bitrate
        listen_only = info.listen_only
        print(describe(info, channel))
    else:
        print(f"WARNING: interface {args.interface} is for testing. Listen-only cannot be checked.")

    steps = [s for s in (args.steps or "").split(",") if s.strip()]
    bus = open_bus(args.interface, channel)  # before making the folder, so a failure leaves nothing behind
    session_dir = make_session_dir(Path(args.out), args.bus, args.label)
    t0 = time.time()
    meta = {
        "label": args.label,
        "bus": args.bus,
        "notes": args.notes or "",
        "channel": channel,
        "interface": args.interface,
        "bitrate": bitrate,
        "listen_only": listen_only,
        "planned_steps": steps,
        "started_unix": t0,
        "started_local": dt.datetime.fromtimestamp(t0).isoformat(timespec="seconds"),
        "host": platform.node(),
        "tool": f"can_capture.py {TOOL_VERSION}",
        "command": " ".join(sys.argv),
    }
    write_meta(session_dir, meta)

    rec = Recorder(session_dir, channel, steps=steps, t0=t0)
    stop = threading.Event()

    print(f"Recording to {session_dir}")
    print("Type a note and press Enter at the moment it happens. Empty Enter stamps the next step.")
    print("Type key=value readings like `v=66.4 a=-48`. :s for stats, :q or Ctrl-C to stop.")
    if steps:
        print(f"Planned steps: {', '.join(steps)}. First: {steps[0]}")
    if args.duration:
        print(f"Stops by itself after {args.duration:g} s.")

    reader = threading.Thread(target=stdin_markers, args=(rec, stop), daemon=True)
    reader.start()
    try:
        record(bus, rec, stop, duration=args.duration, status_every=args.status_every)
    finally:
        bus.shutdown()
        t1 = time.time()
        log_path = rec.close(compress=not args.no_compress)
        meta.update(
            {
                "ended_unix": t1,
                "duration_s": round(t1 - t0, 3),
                "frames": rec.frames,
                "error_frames": rec.errors,
                "unique_ids": len(rec.ids),
                "markers": len(rec.markers),
                "log_file": log_path.name,
            }
        )
        write_meta(session_dir, meta)

    print()
    print(rec.status_line(t1))
    if rec.ids:
        print("Busiest IDs:")
        span = max(t1 - t0, 1e-9)
        for ident, n in rec.ids.most_common(15):
            print(f"  {ident:>8}  {n:7} frames  {n / span:7.1f}/s")
    else:
        print("No data frames were received. Check the key, the probes, and the bitrate.")
    print(f"Saved {session_dir}")
    print(f"Analyze with: python3 tools/can_log_analyze.py {session_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--channel", default="can0", help="SocketCAN interface (default can0)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="show interface state and whether it is safe to capture")

    s = sub.add_parser("setup", help="listen-only mode at a bitrate (uses sudo)")
    s.add_argument("--bitrate", type=int, required=True)

    s = sub.add_parser("scan", help="find the bitrate")
    s.add_argument("--bitrates", default=",".join(str(b) for b in DEFAULT_BITRATES))
    s.add_argument("--seconds", type=float, default=3.0, help="listen time per bitrate")

    s = sub.add_parser("capture", help="record a labeled session")
    s.add_argument("--label", required=True, help="short session name, for example gear-dnr")
    s.add_argument("--bus", default="factory", help="which bus: factory or kelly (default factory)")
    s.add_argument("--steps", help="comma separated planned actions, stamped in order by pressing Enter")
    s.add_argument("--notes", help="free text saved in meta.json")
    s.add_argument("--duration", type=float, help="stop after this many seconds")
    s.add_argument("--setup", type=int, metavar="BITRATE", help="run setup at this bitrate first")
    s.add_argument("--out", default=str(DEFAULT_OUT), help=f"captures folder (default {DEFAULT_OUT})")
    s.add_argument("--status-every", type=float, default=10.0, help="seconds between status lines, 0 for none")
    s.add_argument("--no-compress", action="store_true", help="keep can.log uncompressed")
    s.add_argument("--interface", default="socketcan", help=argparse.SUPPRESS)  # "virtual" for tests only
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"check": cmd_check, "setup": cmd_setup, "scan": cmd_scan, "capture": cmd_capture}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
