"""Reference implementation of the USB link receiver rules (docs/usb_protocol.md).

The firmware and the Android app implement the same rules in their own
languages. This version is used by tools/fake_esp.py and by the tests that
check the shared samples in protocol/fixtures.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Union

PROTO_VERSION = 1
MAX_LINE_BYTES = 2048
STALE_AFTER_S = 2.0
LINK_LOST_AFTER_S = 1.0

# Required fields per known message type, with the Python types they must have.
_REQUIRED = {
    "state": {"seq": int, "t": int},
    "hello": {"proto": int, "fw": str, "uptime_s": int},
    "cmd": {"cmd": str},
    "log": {},
}

CONFIG_KEYS = {
    "wheel_dia_in": (float, int),
    "gear_ratio": (float, int),
    "speed_src": (str,),
    "pulses_per_rev": (float, int),
    "sim": (bool,),
}
SPEED_SOURCES = ("pulse", "rpm")


def _is_type(value: Any, kind: type) -> bool:
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, kind)


def parse_line(raw: Union[bytes, str]) -> Optional[Dict[str, Any]]:
    """Return the message in one received line, or None if the line must be dropped.

    Unknown message types are returned as they are; callers ignore types they
    do not handle. Unknown fields are left in place and ignored.
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8", errors="replace")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if raw.endswith(b"\r"):
        raw = raw[:-1]
    if not raw or len(raw) > MAX_LINE_BYTES:
        return None
    try:
        msg = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
        return None
    for name, kind in _REQUIRED.get(msg["type"], {}).items():
        if not _is_type(msg.get(name), kind):
            return None
    if msg["type"] == "log" and not isinstance(msg.get("msg"), str) and not isinstance(msg.get("frame"), str):
        return None
    return msg


def encode(msg: Dict[str, Any]) -> bytes:
    """One message as a compact JSON line."""
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")


def shown_value(state: Dict[str, Any], field: str) -> Any:
    """What the dash should show for a field: the value, or None for `--`."""
    if field in (state.get("stale") or []):
        return None
    return state.get(field)


def check_config(key: Any, value: Any) -> Optional[str]:
    """None if `set_config key=value` is acceptable, otherwise the reason it is not."""
    if key not in CONFIG_KEYS:
        return f"unknown key {key!r}"
    kinds = CONFIG_KEYS[key]
    if bool not in kinds and isinstance(value, bool):
        return f"{key} needs a {kinds[0].__name__}"
    if not isinstance(value, kinds):
        return f"{key} needs a {kinds[0].__name__}"
    if key == "speed_src" and value not in SPEED_SOURCES:
        return f"speed_src must be one of {', '.join(SPEED_SOURCES)}"
    if key in ("wheel_dia_in", "gear_ratio", "pulses_per_rev") and value <= 0:
        return f"{key} must be above zero"
    return None
