#!/usr/bin/env python3
"""Find the CAN bytes that matter in labeled capture sessions.

Give it one or more session folders made by can_capture.py (or bare candump
logs). For each session it prints a Markdown report:

  IDs           every ID with frame count, period, jitter, and a per byte
                summary (constant value, number of values, or counter)
  Steps         bytes whose steady value changes across each marker,
                for example the gear byte when "R" is marked
  Segments      bytes that hold a different steady value between markers,
                ranked higher when repeated labels agree (D, N, R, D)
  Toggling      bits that toggle in some segments and sit still in others,
                which is how blinkers show up
  Correlation   8 and 16 bit fields that track a measured series: GPS speed
                (--gps), any CSV columns (--series), or readings typed as
                markers like "v=66.4 a=-48"; with a suggested scale and offset

Examples:
    python3 tools/can_log_analyze.py captures/factory/20261106-101500_gear-dnr
    python3 tools/can_log_analyze.py captures/factory/*_drive --gps drive.gpx --plot
    python3 tools/can_log_analyze.py captures/factory/* --out docs/factory_can_report.md
    python3 tools/can_log_analyze.py SESSION --trace 18FF50E5
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import math
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canlog  # noqa: E402

Series = List[Tuple[float, float]]  # (unix time, value)

MPS_TO_MPH = 2.2369362920544
KMH_TO_MPH = 0.621371192237334
KNOT_TO_MPH = 1.15077944802354


# Per ID data -----------------------------------------------------------------


@dataclass
class IdData:
    ident: str
    times: List[float] = field(default_factory=list)
    rows: List[bytes] = field(default_factory=list)

    @property
    def max_len(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    def byte(self, i: int) -> Tuple[List[float], List[int]]:
        ts, vs = [], []
        for t, r in zip(self.times, self.rows):
            if len(r) > i:
                ts.append(t)
                vs.append(r[i])
        return ts, vs


def group_by_id(frames: Iterable[canlog.Frame]) -> Dict[str, IdData]:
    out: Dict[str, IdData] = {}
    for f in frames:
        if f.err or f.rtr:
            continue
        d = out.get(f.ident)
        if d is None:
            d = out[f.ident] = IdData(f.ident)
        d.times.append(f.t)
        d.rows.append(f.data)
    return out


@dataclass
class ByteStats:
    count: int
    unique: int
    vmin: int
    vmax: int
    change_rate: float  # share of consecutive frames where the byte changed
    changed_bits: int  # OR of every bit that ever flipped
    counter: Optional[str]  # "ct" full byte, "ct lo" / "ct hi" nibble counters

    @property
    def const(self) -> Optional[int]:
        return self.vmin if self.unique == 1 else None

    def token(self) -> str:
        if self.const is not None:
            return f"{self.const:02X}"
        if self.counter:
            return "ct"
        return "~" + (str(self.unique) if self.unique < 100 else "*")


def detect_counter(values: Sequence[int]) -> Optional[str]:
    """Rolling counter: the same nonzero step on at least 90% of frames."""
    if len(values) < 8:
        return None
    pairs = list(zip(values, values[1:]))

    def steady(mask: int, shift: int, mod: int) -> bool:
        if len({(v >> shift) & mask for v in values}) < 4:
            return False
        steps = Counter((((b >> shift) & mask) - ((a >> shift) & mask)) % mod for a, b in pairs)
        step, n = steps.most_common(1)[0]
        return step != 0 and n / len(pairs) >= 0.9

    hi_const = len({v >> 4 for v in values}) == 1
    lo_const = len({v & 0x0F for v in values}) == 1
    lo = steady(0x0F, 0, 16)
    hi = steady(0x0F, 4, 16)
    if lo and hi_const:
        return "ct lo"
    if hi and lo_const:
        return "ct hi"
    if steady(0xFF, 0, 256):
        return "ct"
    if lo:
        return "ct lo"
    if hi:
        return "ct hi"
    return None


def byte_stats(values: Sequence[int]) -> ByteStats:
    changes = 0
    bits = 0
    for a, b in zip(values, values[1:]):
        if a != b:
            changes += 1
            bits |= a ^ b
    return ByteStats(
        count=len(values),
        unique=len(set(values)),
        vmin=min(values),
        vmax=max(values),
        change_rate=changes / (len(values) - 1) if len(values) > 1 else 0.0,
        changed_bits=bits,
        counter=detect_counter(values),
    )


@dataclass
class IdStats:
    ident: str
    count: int
    period_ms: Optional[float]
    jitter_ms: Optional[float]
    dlcs: List[int]
    bytes: List[ByteStats]


def id_stats(d: IdData) -> IdStats:
    diffs = [b - a for a, b in zip(d.times, d.times[1:]) if b > a]
    period = statistics.median(diffs) * 1000 if diffs else None
    jitter = statistics.pstdev(diffs) * 1000 if len(diffs) > 1 else None
    dlcs = sorted({len(r) for r in d.rows})
    return IdStats(
        ident=d.ident,
        count=len(d.rows),
        period_ms=period,
        jitter_ms=jitter,
        dlcs=dlcs,
        bytes=[byte_stats(d.byte(i)[1]) for i in range(d.max_len)],
    )


# Windows and markers ---------------------------------------------------------


def window(times: Sequence[float], values: Sequence[int], t0: float, t1: float) -> Sequence[int]:
    return values[bisect.bisect_left(times, t0) : bisect.bisect_left(times, t1)]


def mode_purity(values: Sequence[int]) -> Tuple[int, float]:
    v, n = Counter(values).most_common(1)[0]
    return v, n / len(values)


def is_reading(label: str) -> bool:
    """True for markers that only carry typed readings, like "v=66.4 a=-48"."""
    if not canlog.parse_kv(label):
        return False
    return not canlog._KV_RE.sub("", label).strip(" ,;")


def event_markers(markers: Sequence[canlog.Marker]) -> List[canlog.Marker]:
    return [m for m in markers if not is_reading(m.label)]


def bits_text(mask: int) -> str:
    return ",".join(str(b) for b in range(8) if mask >> b & 1)


@dataclass
class Step:
    marker_index: int
    marker: canlog.Marker
    ident: str
    byte: int
    before: int
    after: int
    purity_before: float
    purity_after: float
    alignment: float  # share of the stepped bits' changes that happen near some marker

    @property
    def score(self) -> float:
        return self.purity_before * self.purity_after * self.alignment


def marker_alignment(
    times: Sequence[float],
    values: Sequence[int],
    marker_times: Sequence[float],
    reach: float,
    mask: int = 0xFF,
) -> float:
    """Share of a byte's changes (in the bits of `mask`) that fall within `reach` seconds of a marker.

    A gear byte that only changes when the operator marks a shift scores 1.0.
    A slowly drifting temperature that happens to tick over at one marker scores
    low. Looking only at the bits that step keeps a blinker that shares the
    byte from dragging down the brake bit next to it.
    """
    change_times = [t for t, a, b in zip(times[1:], values, values[1:]) if (a ^ b) & mask]
    if not change_times:
        return 0.0
    mts = sorted(marker_times)
    near = 0
    for t in change_times:
        i = bisect.bisect_left(mts, t - reach)
        if i < len(mts) and mts[i] <= t + reach:
            near += 1
    return near / len(change_times)


def marker_steps(
    ids: Dict[str, IdData],
    stats: Dict[str, IdStats],
    markers: Sequence[canlog.Marker],
    pre: float = 3.0,
    post: float = 3.0,
    guard: float = 0.7,
    min_purity: float = 0.8,
) -> List[Step]:
    """Bytes whose steady value before a marker differs from the steady value after it.

    The `guard` seconds on either side of the marker are skipped because the
    operator presses Enter a little before or after the actual change.
    """
    steps: List[Step] = []
    mtimes = [m.t for m in markers]
    for ident, d in ids.items():
        st = stats[ident]
        for b in range(d.max_len):
            bs = st.bytes[b]
            if bs.const is not None or bs.counter:
                continue
            times, values = d.byte(b)
            aligns: Dict[int, float] = {}
            for mi, m in enumerate(markers):
                w0 = window(times, values, m.t - guard - pre, m.t - guard)
                w1 = window(times, values, m.t + guard, m.t + guard + post)
                if not w0 or not w1:
                    continue
                v0, p0 = mode_purity(w0)
                v1, p1 = mode_purity(w1)
                if v0 != v1 and p0 >= min_purity and p1 >= min_purity:
                    mask = v0 ^ v1
                    if mask not in aligns:
                        aligns[mask] = marker_alignment(times, values, mtimes, guard + 1.0, mask)
                    steps.append(Step(mi, m, ident, b, v0, v1, p0, p1, aligns[mask]))
    steps.sort(key=lambda s: (s.marker_index, -s.score))
    return steps


def segments(start: float, end: float, markers: Sequence[canlog.Marker], guard: float = 0.7) -> List[Tuple[str, float, float]]:
    """(label, t0, t1) for the time before the first marker and after each marker."""
    bounds = [start] + [m.t for m in markers] + [end]
    labels = ["(start)"] + [m.label for m in markers]
    out = []
    for i, label in enumerate(labels):
        a = bounds[i] + (guard if i > 0 else 0.0)
        b = bounds[i + 1] - (guard if i < len(markers) else 0.0)
        out.append((label, a, b))
    return out


@dataclass
class SegmentRow:
    ident: str
    byte: int
    modes: List[Optional[int]]  # None where the segment has no frames
    purities: List[float]
    alignment: float  # share of the differing bits' changes that happen near a marker
    labels_agree: bool
    min_purity: float = 0.8

    def is_steady(self, i: int) -> bool:
        return self.modes[i] is not None and self.purities[i] >= self.min_purity

    def cell(self, i: int) -> str:
        """Hex value for steady segments, ~ for segments where the byte keeps moving."""
        if self.modes[i] is None:
            return ""
        return f"{self.modes[i]:02X}" if self.is_steady(i) else "~"

    @property
    def score(self) -> float:
        present = [i for i, m in enumerate(self.modes) if m is not None]
        steady = [i for i in present if self.is_steady(i)]
        share = len(steady) / len(present) if present else 0.0
        return self.alignment * share * (1.0 if self.labels_agree else 0.5)


def segment_rows(
    ids: Dict[str, IdData],
    stats: Dict[str, IdStats],
    segs: Sequence[Tuple[str, float, float]],
    markers: Sequence[canlog.Marker],
    min_purity: float = 0.8,
    reach: float = 1.7,
) -> List[SegmentRow]:
    """Bytes with at least two steady segments holding different values.

    Segments where the byte keeps moving (a blinker sharing the byte, say) do
    not disqualify the row; they show as ~ and lower its score. Rows rank by
    how well the byte's changes line up with markers, and whether repeated
    labels (D, N, R, D) hold the same value.
    """
    rows: List[SegmentRow] = []
    mtimes = [m.t for m in markers]
    for ident, d in ids.items():
        st = stats[ident]
        for b in range(d.max_len):
            bs = st.bytes[b]
            if bs.const is not None or bs.counter:
                continue
            times, values = d.byte(b)
            modes: List[Optional[int]] = []
            purities: List[float] = []
            for _, a, z in segs:
                w = window(times, values, a, z)
                if not w:
                    modes.append(None)
                    purities.append(0.0)
                    continue
                v, p = mode_purity(w)
                modes.append(v)
                purities.append(p)
            steady = [i for i, (m, p) in enumerate(zip(modes, purities)) if m is not None and p >= min_purity]
            if len({modes[i] for i in steady}) < 2:
                continue
            by_label: Dict[str, set] = defaultdict(set)
            for i in steady:
                by_label[segs[i][0]].add(modes[i])
            agree = all(len(v) == 1 for v in by_label.values())
            mask = 0
            for i in steady:
                mask |= modes[i] ^ modes[steady[0]]
            align = marker_alignment(times, values, mtimes, reach, mask) if mtimes else 1.0
            if align == 0:
                continue  # none of its changes happen near a marker, so it is drift or noise
            rows.append(SegmentRow(ident, b, modes, purities, align, agree, min_purity))
    rows.sort(key=lambda r: -r.score)
    return rows


@dataclass
class ToggleRow:
    ident: str
    byte: int
    bit: int
    rates: List[Optional[float]]  # transitions per second in each segment

    @property
    def quiet_share(self) -> float:
        present = [r for r in self.rates if r is not None]
        return sum(1 for r in present if r == 0) / len(present) if present else 0.0


def toggle_rows(
    ids: Dict[str, IdData],
    stats: Dict[str, IdStats],
    segs: Sequence[Tuple[str, float, float]],
    min_rate: float = 0.3,
) -> List[ToggleRow]:
    """Bits that toggle at least `min_rate` times a second in some segments and never in others."""
    rows: List[ToggleRow] = []
    for ident, d in ids.items():
        st = stats[ident]
        for b in range(d.max_len):
            bs = st.bytes[b]
            if bs.const is not None or bs.counter:
                continue
            times, values = d.byte(b)
            for bit in range(8):
                if not bs.changed_bits >> bit & 1:
                    continue
                rates: List[Optional[float]] = []
                for _, a, z in segs:
                    i, j = bisect.bisect_left(times, a), bisect.bisect_left(times, z)
                    if j - i < 2 or z <= a:
                        rates.append(None)
                        continue
                    seg = values[i:j]
                    flips = sum(1 for x, y in zip(seg, seg[1:]) if (x ^ y) >> bit & 1)
                    rates.append(flips / (z - a))
                present = [r for r in rates if r is not None]
                if len(present) >= 2 and max(present) >= min_rate and min(present) == 0:
                    rows.append(ToggleRow(ident, b, bit, rates))
    rows.sort(key=lambda r: (-r.quiet_share, -max(x for x in r.rates if x is not None)))
    return rows


# Correlation with measured series ---------------------------------------------


@dataclass
class Candidate:
    name: str
    times: List[float]
    values: List[float]
    bits: int = 8


def candidates(ids: Dict[str, IdData], stats: Dict[str, IdStats]) -> List[Candidate]:
    """Every 8 and 16 bit field that changes and is not a counter, in each byte order and signedness."""
    out: List[Candidate] = []
    for ident, d in ids.items():
        st = stats[ident]
        n = d.max_len
        live = [st.bytes[i].const is None and not st.bytes[i].counter for i in range(n)]
        for b in range(n):
            if not live[b]:
                continue
            ts, vs = d.byte(b)
            out.append(Candidate(f"{ident} b{b} u8", ts, [float(v) for v in vs]))
            if st.bytes[b].vmax >= 0x80:
                out.append(Candidate(f"{ident} b{b} s8", ts, [float(v - 256 if v >= 0x80 else v) for v in vs]))
        for b in range(n - 1):
            if not (live[b] or live[b + 1]):
                continue
            if st.bytes[b].counter or st.bytes[b + 1].counter:
                continue
            ts = [t for t, r in zip(d.times, d.rows) if len(r) > b + 1]
            rows = [r for r in d.rows if len(r) > b + 1]
            le = [r[b] | r[b + 1] << 8 for r in rows]
            be = [r[b] << 8 | r[b + 1] for r in rows]
            orders = []
            # Skip the byte order whose low byte never moves while its high byte does.
            # It fits as well as the 8 bit field but is almost never the real layout.
            if live[b] or not live[b + 1]:
                orders.append(("u16le", le))
            if live[b + 1] or not live[b]:
                orders.append(("u16be", be))
            for kind, vals in orders:
                out.append(Candidate(f"{ident} b{b}-{b + 1} {kind}", ts, [float(v) for v in vals], 16))
                if max(vals) >= 0x8000:
                    signed = [float(v - 0x10000 if v >= 0x8000 else v) for v in vals]
                    out.append(Candidate(f"{ident} b{b}-{b + 1} s{kind[1:]}", ts, signed, 16))
    return out


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[Tuple[float, float, float]]:
    """(r, slope, intercept) for y = slope * x + intercept, or None if either side is flat."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return sxy / math.sqrt(sxx * syy), slope, my - slope * mx


def sample_at(c: Candidate, series: Series, shift: float, max_age: float) -> Tuple[List[float], List[float]]:
    """Pair each series point with the latest CAN value at or before (t + shift)."""
    xs, ys = [], []
    for t, y in series:
        tt = t + shift
        i = bisect.bisect_right(c.times, tt) - 1
        if i < 0 or tt - c.times[i] > max_age:
            continue
        xs.append(c.values[i])
        ys.append(y)
    return xs, ys


@dataclass
class Match:
    name: str
    r: float
    n: int
    shift: float
    factor: float
    offset: float
    raw_min: float
    raw_max: float
    bits: int = 8


def correlate(
    cands: Sequence[Candidate],
    series: Series,
    max_shift: float = 3.0,
    shift_step: float = 0.25,
    max_age: float = 1.0,
    min_points: int = 4,
    keep: int = 10,
) -> List[Match]:
    """Rank candidates by |r| against a series, then search a clock shift for the best few."""
    first: List[Tuple[float, Candidate]] = []
    for c in cands:
        xs, ys = sample_at(c, series, 0.0, max_age)
        if len(xs) < min_points:
            continue
        res = pearson(xs, ys)
        if res is not None:
            first.append((abs(res[0]), c))
    first.sort(key=lambda x: -x[0])

    shifts = [0.0]
    if max_shift > 0 and shift_step > 0:
        k = int(round(max_shift / shift_step))
        shifts = sorted({round(i * shift_step, 6) for i in range(-k, k + 1)}, key=abs)

    matches: List[Match] = []
    for _, c in first[: max(keep * 3, 30)]:
        best: Optional[Tuple[float, float, int, float, float]] = None
        for s in shifts:
            xs, ys = sample_at(c, series, s, max_age)
            if len(xs) < min_points:
                continue
            res = pearson(xs, ys)
            if res is None:
                continue
            if best is None or abs(res[0]) > abs(best[0]) + 1e-9:
                best = (res[0], s, len(xs), res[1], res[2])
        if best is not None:
            r, s, n, slope, icpt = best
            matches.append(Match(c.name, r, n, s, slope, icpt, min(c.values), max(c.values), c.bits))
    # On a tie, list the 16 bit field first: when its high byte never moved in this
    # session the 8 bit low byte fits just as well, but the wider field is the likely truth.
    matches.sort(key=lambda m: (-round(abs(m.r), 4), -m.bits))
    return matches[:keep]


# Measured series loaders ------------------------------------------------------


def parse_time(text: str) -> float:
    """Unix seconds, unix milliseconds, or ISO 8601 (no zone means local time)."""
    s = text.strip()
    try:
        v = float(s)
        return v / 1000.0 if v > 1e11 else v
    except ValueError:
        pass
    s = s.replace("Z", "+00:00")
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    return dt.datetime.fromisoformat(s).timestamp()


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def speeds_from_track(points: Sequence[Tuple[float, float, float, Optional[float]]]) -> Series:
    """points: (t, lat, lon, speed_mph or None). Missing speeds come from distance over time."""
    pts = sorted(points)
    out: Series = []
    for i, (t, lat, lon, mph) in enumerate(pts):
        if mph is None:
            if i == 0:
                continue
            t0, la0, lo0, _ = pts[i - 1]
            if t <= t0:
                continue
            mph = haversine_m(la0, lo0, lat, lon) / (t - t0) * MPS_TO_MPH
        out.append((t, mph))
    return out


def load_gpx(path: Path) -> Series:
    pts = []
    for el in ET.parse(str(path)).iter():
        if not el.tag.endswith("trkpt"):
            continue
        t = None
        mph = None
        for ch in el.iter():
            tag = ch.tag.rsplit("}", 1)[-1].lower()
            if tag == "time" and ch.text:
                t = parse_time(ch.text)
            elif tag == "speed" and ch.text:
                mph = float(ch.text) * MPS_TO_MPH  # GPX speed is m/s
        if t is not None:
            pts.append((t, float(el.get("lat")), float(el.get("lon")), mph))
    return speeds_from_track(pts)


TIME_COLUMNS = ("t_unix", "time", "timestamp", "datetime", "date time", "date_time", "t", "utc")


def _time_column(fields: Sequence[str]) -> Optional[str]:
    lower = {f.lower().strip(): f for f in fields}
    for name in TIME_COLUMNS:
        if name in lower:
            return lower[name]
    for f in fields:
        if "time" in f.lower():
            return f
    return None


def _speed_factor(col: str) -> float:
    c = col.lower()
    if "mph" in c:
        return 1.0
    if "km" in c:
        return KMH_TO_MPH
    if "knot" in c or "kn)" in c:
        return KNOT_TO_MPH
    return MPS_TO_MPH  # plain "speed" columns from GPS loggers are m/s


def load_gps_csv(path: Path) -> Series:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        tcol = _time_column(fields)
        if tcol is None:
            raise SystemExit(f"{path}: no time column found (looked for {', '.join(TIME_COLUMNS)})")
        scol = next((c for c in fields if "speed" in c.lower()), None)
        latcol = next((c for c in fields if c.lower().strip() in ("lat", "latitude")), None)
        loncol = next((c for c in fields if c.lower().strip() in ("lon", "lng", "long", "longitude")), None)
        pts = []
        for row in reader:
            try:
                t = parse_time(row[tcol])
            except (ValueError, TypeError):
                continue
            mph = None
            if scol and row.get(scol, "").strip():
                try:
                    mph = float(row[scol]) * _speed_factor(scol)
                except ValueError:
                    mph = None
            if mph is not None:
                pts.append((t, 0.0, 0.0, mph))
            elif latcol and loncol:
                try:
                    pts.append((t, float(row[latcol]), float(row[loncol]), None))
                except ValueError:
                    continue
    if not pts:
        raise SystemExit(f"{path}: no speed or lat/lon values found")
    return speeds_from_track(pts)


def load_gps(path: Path) -> Series:
    return load_gpx(path) if Path(path).suffix.lower() == ".gpx" else load_gps_csv(path)


def load_series_csv(path: Path) -> Dict[str, Series]:
    """Every numeric column of a CSV becomes a series, keyed by column name."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        tcol = _time_column(fields)
        if tcol is None:
            raise SystemExit(f"{path}: no time column found (looked for {', '.join(TIME_COLUMNS)})")
        out: Dict[str, Series] = defaultdict(list)
        for row in reader:
            try:
                t = parse_time(row[tcol])
            except (ValueError, TypeError):
                continue
            for col in fields:
                if col == tcol:
                    continue
                try:
                    out[col.strip()].append((t, float(row[col])))
                except (TypeError, ValueError):
                    continue
    return {k: sorted(v) for k, v in out.items() if len(v) >= 2}


def marker_series(markers: Sequence[canlog.Marker]) -> Dict[str, Series]:
    out: Dict[str, Series] = defaultdict(list)
    for m in markers:
        for k, v in m.values.items():
            out[k].append((m.t, v))
    return dict(out)


def shift_series(series: Series, offset: float) -> Series:
    return [(t + offset, v) for t, v in series]


# Report -------------------------------------------------------------------------


def fmt(v: Optional[float], digits: int = 1) -> str:
    return "" if v is None else f"{v:.{digits}f}"


def fmt_num(v: float) -> str:
    if v == 0:
        return "0"
    return f"{v:.1f}" if abs(v) >= 100 else f"{v:.4g}"


def md_table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> List[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "/") for c in r) + " |")
    return out


@dataclass
class Options:
    pre: float = 3.0
    post: float = 3.0
    guard: float = 0.7
    min_purity: float = 0.8
    min_toggle_hz: float = 0.3
    top: int = 25
    steps_per_marker: int = 5
    max_shift: float = 3.0
    ids: Optional[List[str]] = None


def analyze_session(
    session: canlog.Session,
    extra_series: Dict[str, Series],
    opts: Options,
) -> Tuple[List[str], dict]:
    """Return (markdown lines, findings) for one session."""
    lines: List[str] = []
    frames = session.data_frames
    if opts.ids:
        wanted = {parse_id(i) for i in opts.ids}
        frames = [f for f in frames if f.can_id in wanted]
    ids = group_by_id(frames)
    stats = {k: id_stats(v) for k, v in ids.items()}
    start, end = session.start, session.end
    findings: dict = {"ids": stats}

    lines.append(f"## Session: {session.name}")
    lines.append("")
    bits = [
        f"`{session.log_path}`",
        f"{end - start:.1f} s",
        f"{len(session.data_frames):,} frames",
        f"{len(session.error_frames):,} error frames",
        f"{len(ids)} IDs",
    ]
    if session.meta.get("bitrate"):
        bits.append(f"bitrate {session.meta['bitrate']}")
    if session.meta.get("listen_only") is not None:
        bits.append("listen-only" if session.meta.get("listen_only") else "listen-only NOT confirmed")
    lines.append(", ".join(bits))
    if session.meta.get("notes"):
        lines.append("")
        lines.append(f"Notes: {session.meta['notes']}")
    lines.append("")

    if not ids:
        lines.append("No data frames in this session.")
        lines.append("")
        return lines, findings

    # IDs
    lines.append("### IDs")
    lines.append("")
    lines.append("Bytes: two hex digits = never changes, ~N = N different values, ct = rolling counter.")
    lines.append("")
    rows = []
    for ident in sorted(stats):
        s = stats[ident]
        rows.append(
            [
                ident,
                f"{s.count:,}",
                fmt(s.period_ms),
                fmt(s.jitter_ms),
                ",".join(str(x) for x in s.dlcs),
                " ".join(b.token() for b in s.bytes),
            ]
        )
    lines += md_table(["ID", "Frames", "Period ms", "Jitter ms", "DLC", "Bytes 0 to 7"], rows)
    lines.append("")

    events = event_markers(session.markers)
    if session.markers:
        lines.append("### Markers")
        lines.append("")
        lines += md_table(
            ["#", "t (s)", "Label"],
            [[str(i + 1), f"{m.t - start:.1f}", m.label] for i, m in enumerate(session.markers)],
        )
        lines.append("")

    if events:
        steps = marker_steps(ids, stats, events, opts.pre, opts.post, opts.guard, opts.min_purity)
        findings["steps"] = steps
        lines.append("### Bytes that step at a marker")
        lines.append("")
        lines.append(
            f"Steady value in the {opts.pre:g} s before vs the {opts.post:g} s after each marker, "
            f"skipping {opts.guard:g} s either side. Best {opts.steps_per_marker} per marker."
        )
        lines.append("")
        rows = []
        per: Dict[int, int] = defaultdict(int)
        for s in steps:
            if per[s.marker_index] >= opts.steps_per_marker:
                continue
            per[s.marker_index] += 1
            rows.append(
                [
                    f"{s.marker_index + 1}: {s.marker.label}",
                    s.ident,
                    str(s.byte),
                    f"{s.before:02X}",
                    f"{s.after:02X}",
                    bits_text(s.before ^ s.after),
                    f"{s.score:.2f}",
                ]
            )
        if rows:
            lines += md_table(["Marker", "ID", "Byte", "Before", "After", "Bits changed", "Score"], rows)
        else:
            lines.append("No clean steps found.")
        lines.append("")

        segs = segments(start, end, events, opts.guard)
        seg_rows = segment_rows(ids, stats, segs, events, opts.min_purity, opts.guard + 1.0)
        findings["segments"] = seg_rows
        lines.append("### Bytes that hold a different value in each segment")
        lines.append("")
        lines.append("A segment runs from one marker to the next. Rows where repeated labels agree rank first.")
        lines.append("")
        if seg_rows:
            header = ["ID", "Byte"] + [label for label, _, _ in segs] + ["Score"]
            rows = []
            for r in seg_rows[: opts.top]:
                cells = [r.cell(i) for i in range(len(r.modes))]
                rows.append([r.ident, str(r.byte)] + cells + [f"{r.score:.2f}"])
            lines += md_table(header, rows)
        else:
            lines.append("None found.")
        lines.append("")

        tog = toggle_rows(ids, stats, segs, opts.min_toggle_hz)
        findings["toggles"] = tog
        lines.append("### Bits that toggle in some segments and sit still in others")
        lines.append("")
        lines.append("Blinkers show up here. Values are bit flips per second in each segment.")
        lines.append("")
        if tog:
            header = ["ID", "Byte.bit"] + [label for label, _, _ in segs]
            rows = []
            for r in tog[: opts.top]:
                rows.append([r.ident, f"{r.byte}.{r.bit}"] + ["" if x is None else f"{x:.1f}" for x in r.rates])
            lines += md_table(header, rows)
        else:
            lines.append("None found.")
        lines.append("")

    all_series = dict(marker_series(session.markers))
    all_series.update(extra_series)
    if all_series:
        cands = candidates(ids, stats)
        findings["correlations"] = {}
        lines.append("### Correlation with measured series")
        lines.append("")
        lines.append(
            "8 and 16 bit fields ranked by how well they track each series. "
            "Physical value = factor x raw + offset. Shift is how many seconds the series clock "
            f"was moved (searched up to {opts.max_shift:g} s) to line up with the CAN clock. "
            "An r above 0.95 is a strong match; below 0.8 is probably coincidence. "
            "Typed readings give only a few points, so confirm them against a second session."
        )
        lines.append("")
        for name in sorted(all_series):
            series = [(t, v) for t, v in all_series[name] if start - 5 <= t <= end + 5]
            lines.append(f"#### {name} ({len(series)} points in this session)")
            lines.append("")
            if len(series) < 4:
                lines.append("Too few points to correlate (need 4).")
                lines.append("")
                continue
            matches = correlate(cands, series, max_shift=opts.max_shift, keep=min(opts.top, 10))
            findings["correlations"][name] = matches
            if not matches:
                lines.append("No field tracks this series.")
                lines.append("")
                continue
            rows = [
                [
                    m.name,
                    f"{m.r:+.3f}",
                    str(m.n),
                    f"{m.shift:+.2f}",
                    fmt_num(m.factor),
                    fmt_num(m.offset),
                    f"{m.raw_min:g} to {m.raw_max:g}",
                ]
                for m in matches
            ]
            lines += md_table(["Field", "r", "Points", "Shift s", "Factor", "Offset", "Raw range"], rows)
            lines.append("")
    return lines, findings


def presence_matrix(sessions: Sequence[canlog.Session]) -> List[str]:
    counts = [Counter(f.ident for f in s.data_frames) for s in sessions]
    all_ids = sorted(set().union(*counts))
    lines = ["## IDs across sessions", ""]
    lines.append("Frame count per session. IDs missing from some sessions are listed first.")
    lines.append("")
    header = ["ID"] + [s.name for s in sessions]
    rows = []
    for ident in sorted(all_ids, key=lambda i: (all(c.get(i) for c in counts), i)):
        rows.append([ident] + [str(c.get(ident, "")) for c in counts])
    lines += md_table(header, rows)
    lines.append("")
    return lines


def parse_id(text: str) -> int:
    """`18FF50E5`, `0x18ff50e5`, or `123` (always hex) to an integer ID."""
    s = text.strip().lower()
    return int(s[2:] if s.startswith("0x") else s, 16)


def trace(session: canlog.Session, ident: str) -> List[str]:
    """Every frame where the data changes for one ID, with markers in between.

    Rolling counter bytes are shown as -- and ignored, otherwise every frame
    would count as a change.
    """
    want = parse_id(ident)
    frames = [f for f in session.data_frames if f.can_id == want]
    if not frames:
        return [f"ID {ident} not found in {session.name}"]
    d = group_by_id(frames)[frames[0].ident]
    counters = {i for i, b in enumerate(id_stats(d).bytes) if b.counter}

    def shown(data: bytes) -> str:
        return " ".join("--" if i in counters else f"{v:02X}" for i, v in enumerate(data))

    start = session.start
    events: List[Tuple[float, str]] = []
    last = None
    for f in frames:
        key = bytes(0 if i in counters else v for i, v in enumerate(f.data))
        if key != last:
            events.append((f.t, f"{f.t - start:9.3f}  {shown(f.data)}"))
            last = key
    for m in session.markers:
        events.append((m.t, f"{m.t - start:9.3f}  >> {m.label}"))
    events.sort(key=lambda e: e[0])
    note = f", counter bytes {sorted(counters)} hidden" if counters else ""
    out = [f"## Trace of {frames[0].ident} in {session.name} ({len(frames)} frames, changes only{note})", "", "```"]
    out += [e[1] for e in events]
    out.append("```")
    return out


# Plots --------------------------------------------------------------------------


def plot_session(session: canlog.Session, findings: dict, extra_series: Dict[str, Series], top: int = 6) -> List[Path]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed; skipping plots (pip install matplotlib).", file=sys.stderr)
        return []

    out_dir = session.path / "plots"
    out_dir.mkdir(exist_ok=True)
    ids = group_by_id(session.data_frames)
    start = session.start
    written: List[Path] = []

    picks: List[Tuple[str, int]] = []
    for r in findings.get("segments", [])[:top]:
        picks.append((r.ident, r.byte))
    for s in findings.get("steps", []):
        if (s.ident, s.byte) not in picks and len(picks) < top * 2:
            picks.append((s.ident, s.byte))

    def draw_markers(ax):
        for m in session.markers:
            ax.axvline(m.t - start, color="0.6", lw=0.8, ls="--")
            ax.text(m.t - start, ax.get_ylim()[1], m.label, rotation=90, va="top", ha="right", fontsize=7)

    for ident, b in picks:
        times, values = ids[ident].byte(b)
        fig, ax = plt.subplots(figsize=(11, 3))
        ax.step([t - start for t in times], values, where="post", lw=1)
        ax.set_title(f"{ident} byte {b}")
        ax.set_xlabel("s")
        draw_markers(ax)
        p = out_dir / f"{ident}_b{b}.png"
        fig.tight_layout()
        fig.savefig(p, dpi=110)
        plt.close(fig)
        written.append(p)

    all_series = dict(marker_series(session.markers))
    all_series.update(extra_series)
    cands = {c.name: c for c in candidates(ids, {k: id_stats(v) for k, v in ids.items()})}
    for name, matches in findings.get("correlations", {}).items():
        if not matches:
            continue
        m = matches[0]
        c = cands.get(m.name)
        if c is None:
            continue
        fig, ax = plt.subplots(figsize=(11, 3))
        ax.plot([t - start for t in c.times], [m.factor * v + m.offset for v in c.values], lw=1, label=f"{m.name} scaled")
        s = all_series[name]
        ax.plot([t + m.shift - start for t, _ in s], [v for _, v in s], "o", ms=3, label=name)
        ax.set_title(f"{name} vs {m.name} (r={m.r:+.3f})")
        ax.legend(fontsize=8)
        draw_markers(ax)
        p = out_dir / f"corr_{name.replace('/', '_').replace(' ', '_')}.png"
        fig.tight_layout()
        fig.savefig(p, dpi=110)
        plt.close(fig)
        written.append(p)
    return written


# Main ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sessions", nargs="+", help="session folders or log files")
    p.add_argument("--gps", action="append", default=[], help="GPS track (.gpx or .csv), adds series gps_mph")
    p.add_argument("--series", action="append", default=[], help="CSV with a time column and numeric columns")
    p.add_argument("--series-offset", type=float, default=0.0, help="seconds to add to --gps and --series times")
    p.add_argument("--max-shift", type=float, default=3.0, help="largest clock shift searched, seconds")
    p.add_argument("--pre", type=float, default=3.0, help="seconds of steady data before a marker")
    p.add_argument("--post", type=float, default=3.0, help="seconds of steady data after a marker")
    p.add_argument("--guard", type=float, default=0.7, help="seconds skipped either side of a marker")
    p.add_argument("--min-purity", type=float, default=0.8, help="share of samples that must hold the steady value")
    p.add_argument("--top", type=int, default=25, help="rows per table")
    p.add_argument("--id", action="append", dest="ids", help="only analyze these IDs (repeatable)")
    p.add_argument("--trace", metavar="ID", help="print the change history of one ID and stop")
    p.add_argument("--plot", action="store_true", help="write PNG plots into each session's plots folder")
    p.add_argument("--out", help="write the report to this file instead of stdout")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    sessions = [canlog.load_session(Path(s)) for s in args.sessions]

    if args.trace:
        out = []
        for s in sessions:
            out += trace(s, args.trace) + [""]
        print("\n".join(out))
        return 0

    extra: Dict[str, Series] = {}
    for g in args.gps:
        name = "gps_mph" if len(args.gps) == 1 else f"gps_mph ({Path(g).name})"
        extra[name] = shift_series(load_gps(Path(g)), args.series_offset)
    for f in args.series:
        for k, v in load_series_csv(Path(f)).items():
            extra[k] = shift_series(v, args.series_offset)

    opts = Options(
        pre=args.pre,
        post=args.post,
        guard=args.guard,
        min_purity=args.min_purity,
        top=args.top,
        max_shift=args.max_shift,
        ids=args.ids,
    )
    lines = ["# CAN capture analysis", ""]
    if len(sessions) > 1:
        lines += presence_matrix(sessions)
    for s in sessions:
        sl, findings = analyze_session(s, extra, opts)
        lines += sl
        if args.plot:
            for p in plot_session(s, findings, extra):
                print(f"wrote {p}", file=sys.stderr)

    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
