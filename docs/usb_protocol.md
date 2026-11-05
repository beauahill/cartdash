# USB link protocol, version 1

The ESP32 and the Android app talk over the ESP32-S3 native USB port (CDC ACM serial). This document is the contract between them. The machine readable version is `protocol/schema/cartdash.schema.json`, and `protocol/fixtures/` holds sample lines that the tools, the firmware tests, and the app tests all check against.

## Framing

- Newline delimited JSON, UTF-8, one JSON object per line. Lines end in `\n`; a `\r` before it is tolerated.
- The serial baud rate setting does not matter on native USB.
- Maximum line length is 2048 bytes. A receiver discards a longer line up to the next newline.

## Rules both sides follow

- **Skip anything that is not a JSON object.** The ESP32 ROM prints plain text right after a reset, and the first line after connecting may be cut off. Neither may break the receiver.
- **Ignore unknown `type` values and unknown fields,** so firmware and app can be updated separately.
- **Drop a message whose required fields are missing or the wrong type.** An optional field with the wrong type is treated as missing.
- **Units are imperial** (mph, Fahrenheit). Current is negative while discharging.
- The ESP32 never prints raw text on purpose. Its debug output goes out as `log` messages.

## ESP32 to app

### `hello`

Sent once a second, and right away after the ESP32 boots or the port opens. It tells the app the link is alive even when no data changes.

```json
{"type":"hello","proto":1,"fw":"0.1.0","uptime_s":120,"sim":false}
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `proto` | integer | yes | Protocol version. This document is 1. |
| `fw` | string | yes | Firmware version. |
| `uptime_s` | integer | yes | Seconds since the ESP32 booted. If it goes down, the ESP32 reset. |
| `sim` | boolean | no | True when the simulator is the data source. The app shows a SIM badge so fake data is never mistaken for real data. |

### `state`

Sent about 10 times a second.

```json
{"type":"state","seq":1042,"t":1234567,
 "speed_mph":14.2,"gear":"D","speed_mode":"high",
 "soc_pct":82,"pack_v":66.4,"pack_a":-48.5,"power_kw":-3.2,
 "cell_v_min":3.311,"cell_v_max":3.324,"bms_temp_f":[78,80],
 "ctrl_temp_f":104,"motor_temp_f":121,"motor_rpm":2210,
 "turn_left":false,"turn_right":true,"low_beam":true,"high_beam":false,
 "brake":false,"park_brake":false,"reverse":false,"illum":true,
 "kelly_faults":[],"bms_faults":[],
 "stale":["motor_temp_f"]}
```

| Field | Type | Unit | Source | Notes |
|---|---|---|---|---|
| `seq` | integer, required | | | Goes up by 1 for every `state` message. Wraps at 2^32. Gaps mean lost lines. |
| `t` | integer, required | ms | | Milliseconds since the ESP32 booted. Wraps at 2^32. |
| `speed_mph` | number | mph | Pulse or Kelly RPM | Which one is set by the `speed_src` config. |
| `gear` | `"D"`, `"N"`, `"R"` | | TBD | Where gear comes from is still a VERIFY item. |
| `speed_mode` | string | | Factory lines | `"low"` or `"high"`. Show other values as they are. |
| `soc_pct` | number | % | BMS | |
| `pack_v` | number | V | BMS | |
| `pack_a` | number | A | BMS | Negative while discharging. |
| `power_kw` | number | kW | ESP32 | `pack_v * pack_a / 1000`. Negative while discharging. |
| `cell_v_min`, `cell_v_max` | number | V | BMS | |
| `bms_temp_f` | array of numbers | F | BMS | One entry per BMS temperature sensor. |
| `ctrl_temp_f` | number | F | Kelly | |
| `motor_temp_f` | number | F | Kelly | |
| `motor_rpm` | number | rpm | Kelly | |
| `turn_left`, `turn_right` | boolean | | Opto | True while flashing, meaning the line toggled within the last 1.2 s. Not each flash. |
| `low_beam`, `high_beam` | boolean | | Opto | |
| `brake`, `park_brake` | boolean | | Opto | |
| `reverse` | boolean | | Opto | |
| `illum` | boolean | | Opto | Headlights on. Drives the night theme. |
| `kelly_faults`, `bms_faults` | array of strings | | Kelly, BMS | Short fault codes. `[]` means no faults. Missing means unknown. |
| `stale` | array of strings | | ESP32 | Names of fields whose reading is more than 2 s old. |

Every field except `type`, `seq`, and `t` is optional.

**Missing, null, and stale all mean "show `--`":**
- Missing or `null`: no reading yet, or that source is not fitted.
- Listed in `stale`: the last reading is more than 2 s old. The ESP32 may still send the old value; the app ignores it.

**Link lost:** the app treats more than 1 s without any line as link lost and shows that clearly.

### `log`

Debug output. Never required for the app to work.

```json
{"type":"log","lvl":"warn","tag":"ble","msg":"BMS disconnected, retrying"}
```

| Field | Type | Meaning |
|---|---|---|
| `lvl` | string | `debug`, `info`, `warn`, or `error` |
| `tag` | string | Subsystem: `sys`, `usb`, `cmd`, `ble`, `can`, `wifi`, `mqtt`, `inputs` |
| `msg` | string | Text |
| `t` | integer | Optional, ms since boot |
| `frame` | string | Raw CAN frame in candump form, only with `tag` `can` (see below) |

At least one of `msg` or `frame` is present.

Raw CAN frames, sent while `can_log` is on:

```json
{"type":"log","lvl":"debug","tag":"can","t":1234567,"frame":"18FF50E5#0102030405060708"}
```

`frame` uses the same `ID#DATA` form as candump: 3 hex digits for standard IDs, 8 for extended. These lines can be turned into a capture file for `tools/can_log_analyze.py`.

## App to ESP32

### `cmd`

Rare commands. The ESP32 answers each one with a `log` line tagged `cmd`: level `info` if it worked, `warn` with the reason if not.

```json
{"type":"cmd","cmd":"set_config","key":"wheel_dia_in","value":22.0}
{"type":"cmd","cmd":"can_log","on":true}
```

| `cmd` | Fields | Effect |
|---|---|---|
| `set_config` | `key` (string), `value` | Store a config value in NVS and apply it now. |
| `can_log` | `on` (boolean) | Start or stop raw CAN frame `log` lines. |

Config keys:

| Key | Type | Meaning |
|---|---|---|
| `wheel_dia_in` | number | Tire diameter in inches. Placeholder default in `config.h` until measured. |
| `gear_ratio` | number | Motor turns per wheel turn. Placeholder default until measured. |
| `speed_src` | `"pulse"` or `"rpm"` | Speed from the factory pulse line or from Kelly motor RPM. |
| `pulses_per_rev` | number | Speed pulses per wheel turn. |
| `sim` | boolean | Use the simulator instead of the hardware inputs. |

The app owns these settings. It sends every one with `set_config` after each connect, and the ESP32 also keeps them in NVS so it works without the app.

## Versioning

`proto` changes only for breaking changes: a field removed, renamed, or given a different unit or meaning. Adding fields or message types does not change it, because receivers ignore what they do not know.
