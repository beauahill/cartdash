"""Shared helpers for CAN capture sessions.

A capture session is a folder with three files:

    can.log.gz     frames in candump -L text format, gzip compressed
                   (can.log while a capture is still running)
    markers.csv    operator notes typed during the capture
    meta.json      label, bitrate, interface, counts

Frame lines look like this, one per frame:

    (1730000000.123456) can0 18FF50E5#0102030405060708

Standard IDs are written with 3 hex digits and extended IDs with 8, the same
way candump does. Error frames carry the 0x20000000 flag in the ID. Remote
frames have R instead of data. Files written by candump, can_capture.py, or
python-can's CanutilsLogWriter can all be read here.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Dict, Iterable, Iterator, List, Optional

CAN_ERR_FLAG = 0x20000000
CAN_EFF_MASK = 0x1FFFFFFF

LOG_NAME = "can.log"
LOG_GZ_NAME = "can.log.gz"
MARKERS_NAME = "markers.csv"
META_NAME = "meta.json"


@dataclass
class Frame:
    """One received CAN frame. `can_id` never includes flag bits."""

    t: float
    can_id: int
    ext: bool = False
    data: bytes = b""
    err: bool = False
    rtr: bool = False
    dlc: int = 0

    @property
    def ident(self) -> str:
        """ID as text: 3 hex digits for standard IDs, 8 for extended."""
        return format_id(self.can_id, self.ext)


def format_id(can_id: int, ext: bool) -> str:
    return f"{can_id & CAN_EFF_MASK:08X}" if ext else f"{can_id & 0x7FF:03X}"


def format_candump(frame: Frame, channel: str = "can0") -> str:
    """Return one candump -L line for a frame, without the newline."""
    if frame.err:
        ident = f"{(frame.can_id & CAN_EFF_MASK) | CAN_ERR_FLAG:08X}"
        body = frame.data.hex().upper()
    elif frame.rtr:
        ident = frame.ident
        body = "R" + (str(frame.dlc) if frame.dlc else "")
    else:
        ident = frame.ident
        body = frame.data.hex().upper()
    return f"({frame.t:.6f}) {channel} {ident}#{body}"


_LINE_RE = re.compile(
    r"^\((?P<t>[0-9]+(?:\.[0-9]+)?)\)\s+(?P<ch>\S+)\s+(?P<id>[0-9A-Fa-f]{1,8})#(?P<body>\S*)"
)


def parse_candump(line: str) -> Optional[Frame]:
    """Parse one candump -L line. Returns None for lines that are not frames."""
    m = _LINE_RE.match(line.strip())
    if not m:
        return None
    id_hex = m.group("id")
    raw_id = int(id_hex, 16)
    body = m.group("body")
    t = float(m.group("t"))

    if len(id_hex) == 8 and raw_id & CAN_ERR_FLAG:
        try:
            data = bytes.fromhex(body)
        except ValueError:
            data = b""
        return Frame(t=t, can_id=raw_id & CAN_EFF_MASK, ext=True, data=data, err=True, dlc=len(data))

    ext = len(id_hex) > 3
    if body.startswith("#"):  # CAN FD: ##<flags><data>
        body = body[2:]
    if body[:1] in ("R", "r"):
        dlc = int(body[1:]) if body[1:].isdigit() else 0
        return Frame(t=t, can_id=raw_id & CAN_EFF_MASK, ext=ext, rtr=True, dlc=dlc)
    try:
        data = bytes.fromhex(body)
    except ValueError:
        return None
    return Frame(t=t, can_id=raw_id & CAN_EFF_MASK, ext=ext, data=data, dlc=len(data))


def open_text(path: Path) -> IO[str]:
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def iter_frames(path: Path) -> Iterator[Frame]:
    """Yield frames from a candump log (.log or .log.gz).

    Other formats that python-can understands (.asc, .blf, .trc, .csv) are
    read through python-can, so captures from SavvyCAN or other tools work too.
    """
    path = Path(path)
    suffixes = [s.lower() for s in path.suffixes]
    if suffixes[-1:] == [".log"] or suffixes[-2:] == [".log", ".gz"]:
        with open_text(path) as f:
            for line in f:
                frame = parse_candump(line)
                if frame is not None:
                    yield frame
        return

    import can  # only needed for non candump formats

    for msg in can.LogReader(str(path)):
        yield Frame(
            t=float(msg.timestamp),
            can_id=int(msg.arbitration_id),
            ext=bool(msg.is_extended_id),
            data=bytes(msg.data or b""),
            err=bool(msg.is_error_frame),
            rtr=bool(msg.is_remote_frame),
            dlc=int(msg.dlc),
        )


# Markers ---------------------------------------------------------------

_KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([-+]?[0-9]*\.?[0-9]+)")


def parse_kv(label: str) -> Dict[str, float]:
    """Pull numeric readings out of a marker label.

    `v=66.4 a=-48.5` gives {"v": 66.4, "a": -48.5}. The analyzer treats each
    key as a measured series and looks for CAN bytes that track it.
    """
    return {k.lower(): float(v) for k, v in _KV_RE.findall(label)}


@dataclass
class Marker:
    t: float
    label: str

    @property
    def values(self) -> Dict[str, float]:
        return parse_kv(self.label)


class MarkerWriter:
    """Appends markers to markers.csv and flushes each one right away."""

    HEADER = ["t_unix", "t_rel_s", "label"]

    def __init__(self, path: Path, t0: float):
        self.path = Path(path)
        self.t0 = t0
        self._f = open(self.path, "w", newline="", encoding="utf-8")
        self._w = csv.writer(self._f)
        self._w.writerow(self.HEADER)
        self._f.flush()

    def add(self, marker: Marker) -> None:
        self._w.writerow([f"{marker.t:.6f}", f"{marker.t - self.t0:.3f}", marker.label])
        self._f.flush()

    def close(self) -> None:
        self._f.close()


def read_markers(path: Path) -> List[Marker]:
    path = Path(path)
    if not path.exists():
        return []
    out: List[Marker] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                out.append(Marker(t=float(row["t_unix"]), label=row.get("label", "") or ""))
            except (KeyError, TypeError, ValueError):
                continue
    out.sort(key=lambda m: m.t)
    return out


# Sessions --------------------------------------------------------------


@dataclass
class Session:
    path: Path
    name: str
    log_path: Path
    frames: List[Frame]
    markers: List[Marker]
    meta: dict

    @property
    def data_frames(self) -> List[Frame]:
        return [f for f in self.frames if not f.err and not f.rtr]

    @property
    def error_frames(self) -> List[Frame]:
        return [f for f in self.frames if f.err]

    @property
    def start(self) -> float:
        times = [f.t for f in self.frames] + [m.t for m in self.markers]
        if self.meta.get("started_unix"):
            times.append(float(self.meta["started_unix"]))
        return min(times) if times else 0.0

    @property
    def end(self) -> float:
        times = [f.t for f in self.frames] + [m.t for m in self.markers]
        if self.meta.get("ended_unix"):
            times.append(float(self.meta["ended_unix"]))
        return max(times) if times else 0.0


def find_log(folder: Path) -> Optional[Path]:
    for name in (LOG_GZ_NAME, LOG_NAME):
        p = Path(folder) / name
        if p.exists():
            return p
    return None


def load_session(path: Path) -> Session:
    """Load a session folder, or a bare log file (markers.csv next to it is used if present)."""
    p = Path(path)
    if p.is_dir():
        log_path = find_log(p)
        if log_path is None:
            raise FileNotFoundError(f"no {LOG_NAME} or {LOG_GZ_NAME} in {p}")
        folder = p
    else:
        log_path = p
        folder = p.parent
    meta: dict = {}
    meta_path = folder / META_NAME
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
    frames = sorted(iter_frames(log_path), key=lambda f: f.t)
    markers = read_markers(folder / MARKERS_NAME)
    name = meta.get("label") or (folder.name if p.is_dir() else p.name)
    return Session(path=folder, name=str(name), log_path=log_path, frames=frames, markers=markers, meta=meta)


def write_frames(path: Path, frames: Iterable[Frame], channel: str = "can0") -> None:
    """Write frames as a candump log. Gzip compressed if the name ends in .gz."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "wt", encoding="utf-8") as f:  # type: ignore[operator]
        for frame in frames:
            f.write(format_candump(frame, channel) + "\n")
