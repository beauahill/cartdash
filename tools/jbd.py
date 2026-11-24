"""Reference decoder for the JBD BMS Bluetooth protocol (docs/protocols.md).

The firmware ports this to C++ (bms_jbd.cpp) and tests it against the same
captured frames, as the app and firmware do with protocol/fixtures. Pure
functions only: no Bluetooth here, see tools/bms_probe.py for that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

START = 0xDD
END = 0x77
READ = 0xA5

CMD_BASIC = 0x03
CMD_CELLS = 0x04
CMD_VERSION = 0x05

# GATT, as 128 bit UUIDs (the 16 bit ones are FF00, FF01, FF02).
SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

# Protection flag bit -> short fault code for `bms_faults` on the USB link.
FAULT_BITS = {
    0: "cell_ov",
    1: "cell_uv",
    2: "pack_ov",
    3: "pack_uv",
    4: "chg_ot",
    5: "chg_ut",
    6: "dsg_ot",
    7: "dsg_ut",
    8: "chg_oc",
    9: "dsg_oc",
    10: "short",
    11: "afe_error",
    12: "fet_lock",
}
# Added when the discharge FET is off: the cart has no power.
DSG_FET_OFF = "dsg_fet_off"

# Basic info is 23 bytes plus 2 per temperature sensor. Newer BMS firmware
# appends more bytes after the temperatures; they are ignored.
BASIC_FIXED_LEN = 23


def checksum(body: bytes) -> int:
    """0x10000 minus the byte sum, as 16 bits. Requests sum cmd, length, and
    data; responses sum status, length, and data."""
    return (0x10000 - sum(body)) & 0xFFFF


def request(cmd: int) -> bytes:
    """Read request for a register, for example DD A5 03 00 FF FD 77."""
    body = bytes([cmd, 0x00])
    c = checksum(body)
    return bytes([START, READ]) + body + bytes([c >> 8, c & 0xFF, END])


@dataclass
class Frame:
    cmd: int
    status: int
    data: bytes
    raw: bytes

    @property
    def ok(self) -> bool:
        return self.status == 0


def build_response(cmd: int, data: bytes, status: int = 0) -> bytes:
    """A response frame as the BMS sends it. Used by tests and tools."""
    body = bytes([status, len(data)]) + data
    c = checksum(body)
    return bytes([START, cmd]) + body + bytes([c >> 8, c & 0xFF, END])


class FrameAssembler:
    """Collects notification chunks into whole frames.

    A response is often split across several notifications of 20 bytes or
    less. Bytes before a start byte are skipped. A candidate frame with a bad
    end byte or checksum is dropped one byte at a time until the stream lines
    up again, so one corrupt chunk does not lose the next good frame.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.dropped = 0  # bytes thrown away while resyncing

    def feed(self, chunk: bytes) -> List[Frame]:
        self._buf += chunk
        out: List[Frame] = []
        while True:
            start = self._buf.find(START)
            if start < 0:
                self.dropped += len(self._buf)
                self._buf.clear()
                return out
            if start:
                self.dropped += start
                del self._buf[:start]
            if len(self._buf) < 4:
                return out
            total = 4 + self._buf[3] + 3
            if len(self._buf) < total:
                return out
            cand = bytes(self._buf[:total])
            body = cand[2:4 + cand[3]]
            if cand[-1] == END and ((cand[-3] << 8) | cand[-2]) == checksum(body):
                out.append(Frame(cmd=cand[1], status=cand[2], data=cand[4:4 + cand[3]], raw=cand))
                del self._buf[:total]
            else:
                self.dropped += 1
                del self._buf[:1]


def _u16(b: bytes, i: int) -> int:
    return (b[i] << 8) | b[i + 1]


def _s16(b: bytes, i: int) -> int:
    v = _u16(b, i)
    return v - 0x10000 if v & 0x8000 else v


@dataclass
class BasicInfo:
    pack_v: float
    pack_a: float  # positive is charging, same sign as the USB link
    remaining_ah: float
    nominal_ah: float
    cycles: int
    balancing: int  # one bit per cell, cell 1 in bit 0
    protection: int
    sw_version: int
    soc_pct: int
    charge_fet: bool
    discharge_fet: bool
    cell_count: int
    temps_c: List[float] = field(default_factory=list)

    @property
    def faults(self) -> List[str]:
        codes = [code for bit, code in sorted(FAULT_BITS.items()) if self.protection & (1 << bit)]
        if not self.discharge_fet:
            codes.append(DSG_FET_OFF)
        return codes


def parse_basic(data: bytes) -> BasicInfo:
    if len(data) < BASIC_FIXED_LEN:
        raise ValueError(f"basic info too short: {len(data)} bytes")
    n_temps = data[22]
    if len(data) < BASIC_FIXED_LEN + 2 * n_temps:
        raise ValueError(f"basic info says {n_temps} temperatures but has {len(data)} bytes")
    temps = [round((_u16(data, BASIC_FIXED_LEN + 2 * i) - 2731) / 10.0, 1) for i in range(n_temps)]
    fet = data[20]
    return BasicInfo(
        pack_v=_u16(data, 0) / 100.0,
        pack_a=_s16(data, 2) / 100.0,
        remaining_ah=_u16(data, 4) / 100.0,
        nominal_ah=_u16(data, 6) / 100.0,
        cycles=_u16(data, 8),
        balancing=_u16(data, 12) | (_u16(data, 14) << 16),
        protection=_u16(data, 16),
        sw_version=data[18],
        soc_pct=data[19],
        charge_fet=bool(fet & 0x01),
        discharge_fet=bool(fet & 0x02),
        cell_count=data[21],
        temps_c=temps,
    )


def parse_cells(data: bytes) -> List[float]:
    """Cell voltages in volts, cell 1 first."""
    if len(data) % 2:
        raise ValueError(f"cell data has an odd length: {len(data)} bytes")
    return [_u16(data, i) / 1000.0 for i in range(0, len(data), 2)]


def parse_version(data: bytes) -> str:
    return data.decode("ascii", errors="replace").strip("\x00 ")


def c_to_f(c: float) -> float:
    return round(c * 9.0 / 5.0 + 32.0, 1)


def state_fields(basic: Optional[BasicInfo], cells: Optional[List[float]]) -> Dict[str, object]:
    """The USB link `state` fields the BMS fills (docs/usb_protocol.md).
    A field is left out when its source has not been read."""
    out: Dict[str, object] = {}
    if basic is not None:
        out["soc_pct"] = basic.soc_pct
        out["pack_v"] = round(basic.pack_v, 2)
        out["pack_a"] = round(basic.pack_a, 2)
        out["power_kw"] = round(basic.pack_v * basic.pack_a / 1000.0, 2)
        out["bms_temp_f"] = [c_to_f(t) for t in basic.temps_c]
        out["bms_faults"] = basic.faults
    if cells:
        out["cell_v_min"] = min(cells)
        out["cell_v_max"] = max(cells)
    return out
