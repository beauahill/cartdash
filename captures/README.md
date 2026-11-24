# Captures

Raw captures. CAN captures are made with `tools/can_capture.py`. They are committed on purpose: the factory bus captures cannot be redone once the Tianji controller is removed, so git is their backup.

Layout:

```
captures/
  factory/                      original Tianji controller to factory screen
    20261106-101500_02-gear/
      can.log.gz                frames, candump -L format, gzip
      markers.csv               notes typed during the capture
      meta.json                 label, bitrate, listen-only, counts
      plots/                    made by can_log_analyze.py --plot, not committed
  kelly/                        Kelly controller, later
  bms/                          JBD BMS over Bluetooth, from tools/bms_probe.py
    2026-11-24-1015-parked.jsonl  one meta line, then every request (tx) and notification (rx) as hex
```

Analyze with `tools/can_log_analyze.py`. See `tools/README.md` for the session list.

## BMS captures

The firmware decoder's tests replay these files, so each one needs what the JBD app showed during it. Add a row per file:

| File | Situation | JBD app showed (voltage, current, SOC, temperatures, lowest and highest cell) |
|---|---|---|
| | | |
