#!/usr/bin/env python3
"""Talk to the BMS over Bluetooth from the laptop, the way the ESP32 will.

Answers the BMS rows in docs/verify.md and saves raw notifications as test
data for the firmware decoder (captures/bms/).

  bms_probe.py --scan                     list nearby Bluetooth devices
  bms_probe.py --address AA:BB:..         services, one read, decoded
  bms_probe.py --address AA:BB:.. --watch 60 --save charging
                                          read every second for 60 s and save
  bms_probe.py --replay captures/bms/FILE decode a saved capture, no Bluetooth

The BMS takes one Bluetooth connection at a time: close the JBD app on the
phone (or turn the phone's Bluetooth off) first. Needs `bleak` for every mode
except --replay.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jbd  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CAPTURE_DIR = REPO / "captures" / "bms"
ANSWER_TIMEOUT_S = 2.0


def summary_line(t: float, basic: Optional[jbd.BasicInfo], cells: Optional[List[float]]) -> str:
    parts = [f"t={t:6.1f} s"]
    if basic:
        parts += [
            f"{basic.pack_v:6.2f} V",
            f"{basic.pack_a:+7.2f} A",
            f"{basic.pack_v * basic.pack_a / 1000:+6.2f} kW",
            f"SOC {basic.soc_pct}%",
            "temps " + " ".join(f"{jbd.c_to_f(c)}" for c in basic.temps_c) + " F",
            "faults " + (",".join(basic.faults) or "none"),
        ]
    if cells:
        parts.append(f"cells {min(cells):.3f} to {max(cells):.3f} V")
    return "  ".join(parts)


def describe_basic(b: jbd.BasicInfo) -> str:
    rows = [
        ("Pack voltage", f"{b.pack_v:.2f} V"),
        ("Current (+ is charging)", f"{b.pack_a:+.2f} A"),
        ("State of charge", f"{b.soc_pct} %"),
        ("Remaining / nominal", f"{b.remaining_ah:.2f} / {b.nominal_ah:.2f} Ah"),
        ("Cycles", str(b.cycles)),
        ("Cells", str(b.cell_count)),
        ("Temperatures", ", ".join(f"{c} C ({jbd.c_to_f(c)} F)" for c in b.temps_c) or "none"),
        ("Charge FET / discharge FET", f"{'on' if b.charge_fet else 'OFF'} / {'on' if b.discharge_fet else 'OFF'}"),
        ("Protection flags", f"0x{b.protection:04X} " + (",".join(b.faults) or "none")),
        ("Balancing bits", f"0x{b.balancing:08X}"),
        ("Software version", f"0x{b.sw_version:02X}"),
    ]
    w = max(len(k) for k, _ in rows)
    return "\n".join(f"  {k:<{w}}  {v}" for k, v in rows)


class Capture:
    """Raw chunks as JSON lines: one meta line, then tx and rx records."""

    def __init__(self, path: Optional[Path], meta: Dict[str, object]):
        self.path = path
        self.t0 = time.monotonic()
        self._f = None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._f = path.open("w")
            self._write({"type": "meta", **meta})

    def _write(self, rec: Dict[str, object]) -> None:
        if self._f:
            self._f.write(json.dumps(rec) + "\n")
            self._f.flush()

    def chunk(self, direction: str, data: bytes) -> None:
        self._write({"t": round(time.monotonic() - self.t0, 3), "dir": direction, "hex": data.hex()})

    def close(self) -> None:
        if self._f:
            self._f.close()


async def scan(seconds: float) -> int:
    from bleak import BleakScanner

    print(f"Scanning {seconds:.0f} s ...")
    try:
        found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    except Exception as e:  # no adapter, BlueZ not running, adapter off
        print(f"Bluetooth is not available: {e!r}")
        print("Check that the laptop's Bluetooth is on: bluetoothctl show (Powered: yes).")
        return 1
    rows = sorted(found.values(), key=lambda da: da[1].rssi, reverse=True)
    for dev, adv in rows:
        name = adv.local_name or dev.name or "(no name)"
        jbd_mark = "  <- JBD service advertised" if jbd.SERVICE_UUID in [u.lower() for u in adv.service_uuids] else ""
        print(f"  {dev.address}  {adv.rssi:4d} dBm  {name}{jbd_mark}")
    if not rows:
        print("Nothing found. Is the laptop's Bluetooth on (bluetoothctl show)?")
    print("\nThe BMS is usually the strongest signal near the cart, often named like the JBD app shows it.")
    return 0


async def probe(address: str, watch_s: float, save: Optional[str]) -> int:
    from bleak import BleakClient

    print(f"Connecting to {address} ...")
    try:
        client = BleakClient(address, timeout=20.0)
        await client.connect()
    except Exception as e:  # bleak raises several types depending on the backend
        print(f"Could not connect: {e}")
        print("Close the JBD app on the phone (the BMS takes one connection at a time) and try again.")
        return 1

    try:
        print("\nServices and characteristics:")
        for svc in client.services:
            print(f"  service {svc.uuid}")
            for ch in svc.characteristics:
                print(f"    {ch.uuid}  {','.join(ch.properties)}")
        notify = client.services.get_characteristic(jbd.NOTIFY_UUID)
        write = client.services.get_characteristic(jbd.WRITE_UUID)
        if notify is None or write is None:
            print("\nNo JBD service (FF00 with FF01 and FF02). Send the list above to Claude.")
            return 2
        print("\nJBD service found: FF01 notify, FF02 write.")
        with_response = "write-without-response" not in write.properties

        path = None
        if save:
            stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M")
            path = CAPTURE_DIR / f"{stamp}-{save}.jsonl"
        cap = Capture(path, {"address": address, "date": dt.datetime.now().isoformat(timespec="seconds")})
        asm = jbd.FrameAssembler()
        latest: Dict[int, jbd.Frame] = {}
        got = {cmd: asyncio.Event() for cmd in (jbd.CMD_BASIC, jbd.CMD_CELLS, jbd.CMD_VERSION)}

        def on_notify(_sender, data: bytearray) -> None:
            cap.chunk("rx", bytes(data))
            for fr in asm.feed(bytes(data)):
                latest[fr.cmd] = fr
                if fr.cmd in got:
                    got[fr.cmd].set()

        async def ask(cmd: int) -> Optional[jbd.Frame]:
            got[cmd].clear()
            req = jbd.request(cmd)
            cap.chunk("tx", req)
            await client.write_gatt_char(write, req, response=with_response)
            try:
                await asyncio.wait_for(got[cmd].wait(), ANSWER_TIMEOUT_S)
            except asyncio.TimeoutError:
                return None
            return latest[cmd]

        await client.start_notify(notify, on_notify)

        ver = await ask(jbd.CMD_VERSION)
        basic_fr = await ask(jbd.CMD_BASIC)
        cells_fr = await ask(jbd.CMD_CELLS)
        if basic_fr is None and cells_fr is None:
            print("\nNo answer to the read requests. Either the JBD app still holds the BMS, or this BMS")
            print("wants its PIN before it answers. Tell Claude which, and keep the PIN out of the repo.")
            cap.close()
            return 3

        if ver is not None and ver.ok:
            print(f"Hardware version: {jbd.parse_version(ver.data)}")
        basic = jbd.parse_basic(basic_fr.data) if basic_fr is not None and basic_fr.ok else None
        cells = jbd.parse_cells(cells_fr.data) if cells_fr is not None and cells_fr.ok else None
        if basic:
            print("\nBasic info (compare with the JBD app):")
            print(describe_basic(basic))
        if cells:
            print("\nCells (V): " + " ".join(f"{v:.3f}" for v in cells))
        print("\nAs the ESP32 will send it:")
        print("  " + json.dumps(jbd.state_fields(basic, cells)))

        if watch_s > 0:
            print(f"\nReading every second for {watch_s:.0f} s (Ctrl+C stops):")
            t0 = time.monotonic()
            n = 0
            try:
                while time.monotonic() - t0 < watch_s:
                    tick = time.monotonic()
                    fr = await ask(jbd.CMD_BASIC)
                    if fr is not None and fr.ok:
                        basic = jbd.parse_basic(fr.data)
                    if n % 2 == 0:
                        fr = await ask(jbd.CMD_CELLS)
                        if fr is not None and fr.ok:
                            cells = jbd.parse_cells(fr.data)
                    print(summary_line(time.monotonic() - t0, basic, cells))
                    n += 1
                    await asyncio.sleep(max(0.0, 1.0 - (time.monotonic() - tick)))
            except (KeyboardInterrupt, asyncio.CancelledError):
                print("Stopped.")
        if asm.dropped:
            print(f"\n{asm.dropped} bytes did not form a valid frame and were skipped.")
        cap.close()
        if path:
            print(f"\nSaved {path.relative_to(REPO)}")
        return 0
    finally:
        await client.disconnect()


def replay(path: Path) -> int:
    asm = jbd.FrameAssembler()
    basic = None
    cells = None
    counts: Dict[int, int] = {}
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") == "meta":
            print(f"Capture of {rec.get('address')} on {rec.get('date')}")
            continue
        if rec["dir"] != "rx":
            continue
        for fr in asm.feed(bytes.fromhex(rec["hex"])):
            counts[fr.cmd] = counts.get(fr.cmd, 0) + 1
            if not fr.ok:
                print(f"t={rec['t']:6.1f} s  cmd 0x{fr.cmd:02X} status 0x{fr.status:02X} (not OK)")
                continue
            if fr.cmd == jbd.CMD_BASIC:
                basic = jbd.parse_basic(fr.data)
                print(summary_line(rec["t"], basic, cells))
            elif fr.cmd == jbd.CMD_CELLS:
                cells = jbd.parse_cells(fr.data)
            elif fr.cmd == jbd.CMD_VERSION:
                print(f"Hardware version: {jbd.parse_version(fr.data)}")
    print("Frames: " + ", ".join(f"0x{k:02X} x{v}" for k, v in sorted(counts.items())) + f"; bytes skipped: {asm.dropped}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--scan", action="store_true", help="list nearby Bluetooth devices")
    mode.add_argument("--address", help="BMS Bluetooth address, from --scan")
    mode.add_argument("--replay", type=Path, help="decode a saved capture")
    ap.add_argument("--seconds", type=float, default=8.0, help="scan time (default 8)")
    ap.add_argument("--watch", type=float, default=0.0, help="keep reading for this many seconds")
    ap.add_argument("--save", metavar="LABEL", help="save raw notifications to captures/bms/<date>-LABEL.jsonl")
    args = ap.parse_args(argv)

    if args.replay:
        return replay(args.replay)
    try:
        import bleak  # noqa: F401
    except ImportError:
        print("Needs bleak: pip install -r tools/requirements.txt")
        return 1
    if args.scan:
        return asyncio.run(scan(args.seconds))
    return asyncio.run(probe(args.address, args.watch, args.save))


if __name__ == "__main__":
    sys.exit(main())
