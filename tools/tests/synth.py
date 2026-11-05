"""Synthetic capture sessions with known answers, for testing the analyzer.

Bus layout used by every session:
  18FF50E5 (extended, 10 Hz)
      b0 gear: N=00, D=01, R=02
      b1 constant 12
      b2 rolling counter
      b3 temperature, drifts slowly upward
      b5 bit 0 left blinker (toggles at 1.5 Hz while on), bit 3 brake
  0CF11E05 (extended, 20 Hz)
      b0-1 motor RPM, unsigned 16 bit little endian, RPM = 191 x mph
      b2-3 pack current x10, signed 16 bit little endian (negative is discharge)
      b4-5 pack voltage x10, unsigned 16 bit big endian
  123 (standard, 5 Hz) constant 01 02 03 04
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

import canlog

T0 = 1_800_000_000.0
RPM_PER_MPH = 191.0


def _frames(duration: float, sig: Callable[[float], Dict[str, float]], temp_phase: float = 0.0) -> List[canlog.Frame]:
    """temp_phase shifts when the drifting temperature byte ticks over (every 20 s)."""
    out: List[canlog.Frame] = []
    counter = 0
    steps = int(duration * 20)
    for k in range(steps):
        t = T0 + k * 0.05
        s = sig(t - T0)
        rpm = int(round(s.get("mph", 0.0) * RPM_PER_MPH))
        amps10 = int(round(s.get("amps", -2.0) * 10)) & 0xFFFF
        volts10 = int(round(s.get("volts", 66.4) * 10))
        out.append(
            canlog.Frame(
                t=t + 0.001,
                can_id=0x0CF11E05,
                ext=True,
                data=bytes([rpm & 0xFF, rpm >> 8, amps10 & 0xFF, amps10 >> 8, volts10 >> 8, volts10 & 0xFF, 0, 0]),
            )
        )
        if k % 2 == 0:
            temp = 40 + int((t - T0 + temp_phase) / 20)
            b5 = (int(s.get("left", 0)) & 1) | (8 if s.get("brake") else 0)
            out.append(
                canlog.Frame(
                    t=t + 0.003,
                    can_id=0x18FF50E5,
                    ext=True,
                    data=bytes([int(s.get("gear", 0)), 0x12, counter & 0xFF, temp, 0, b5, 0, 0]),
                )
            )
            counter += 1
        if k % 4 == 0:
            out.append(canlog.Frame(t=t + 0.007, can_id=0x123, ext=False, data=bytes([1, 2, 3, 4])))
    return out


def _write(folder: Path, label: str, frames: Sequence[canlog.Frame], markers: Sequence[Tuple[float, str]], duration: float) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    canlog.write_frames(folder / canlog.LOG_GZ_NAME, frames)
    w = canlog.MarkerWriter(folder / canlog.MARKERS_NAME, T0)
    for t, text in markers:
        w.add(canlog.Marker(T0 + t, text))
    w.close()
    meta = {"label": label, "bitrate": 250000, "listen_only": True, "started_unix": T0, "ended_unix": T0 + duration}
    (folder / canlog.META_NAME).write_text(json.dumps(meta))
    return folder


GEAR_MARKERS = [(8.0, "D"), (20.0, "N"), (32.0, "R"), (44.0, "D")]


def gear_session(folder: Path) -> Path:
    """Shift N (start) to D, N, R, D. The real change lands 0.3 s after each marker.

    The temperature byte deliberately ticks over right at the N marker, to check
    that a coincidence does not outrank the gear byte.
    """
    codes = {"D": 1, "N": 0, "R": 2}

    def sig(t: float) -> Dict[str, float]:
        gear = 0
        for mt, label in GEAR_MARKERS:
            if t >= mt + 0.3:
                gear = codes[label]
        return {"gear": gear}

    return _write(folder, "gear-dnr", _frames(56.0, sig), GEAR_MARKERS, 56.0)


LIGHT_MARKERS = [(10.0, "left on"), (20.0, "left off"), (30.0, "brake on"), (40.0, "brake off")]


def lights_session(folder: Path) -> Path:
    def sig(t: float) -> Dict[str, float]:
        left = 1 if 10.2 <= t < 20.2 and int((t - 10.2) / 0.333) % 2 == 0 else 0
        brake = 30.2 <= t < 40.2
        return {"left": left, "brake": brake}

    return _write(folder, "lights", _frames(50.0, sig, temp_phase=7.0), LIGHT_MARKERS, 50.0)


def drive_profile(t: float) -> Dict[str, float]:
    """0 to 15 mph over 20 s, hold to 40 s, slow to 0 by 55 s, stopped to 60 s."""
    if t < 5:
        mph, amps = 0.0, -2.0
    elif t < 25:
        mph, amps = 15.0 * (t - 5) / 20, -80.0 - 2.0 * (t - 5)
    elif t < 40:
        mph, amps = 15.0, -40.0 + (t - 25)
    elif t < 55:
        mph, amps = 15.0 * (55 - t) / 15, 20.0 + 0.5 * (t - 40)
    else:
        mph, amps = 0.0, -2.0
    volts = 66.4 + amps * 0.02 - 0.03 * t  # sag under load plus slow drain, so it is not just a copy of current
    return {"mph": mph, "amps": amps, "volts": volts}


GPS_CLOCK_LAG = 1.0  # the phone clock runs 1 s behind the laptop


def drive_session(folder: Path) -> Tuple[Path, List[Tuple[float, float]]]:
    """Returns the session and a 1 Hz GPS series (unix time, mph) on a lagging clock."""
    reading_times = [3.0, 12.0, 22.0, 30.0, 38.0, 45.0, 52.0, 58.0]
    markers = []
    for rt in reading_times:
        p = drive_profile(rt)
        markers.append((rt, f"v={p['volts']:.1f} a={p['amps']:.1f}"))
    gps = []
    for k in range(60):
        gps.append((T0 + k - GPS_CLOCK_LAG, drive_profile(float(k))["mph"]))
    return _write(folder, "drive", _frames(60.0, drive_profile), markers, 60.0), gps
