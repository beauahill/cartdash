# Protocol sample lines

Shared test data for the USB link (`docs/usb_protocol.md`). The Python tools, the firmware native tests, and the Android unit tests all read these files, so the two ends of the link cannot drift apart. Change them only together with the spec.

Every file is JSON Lines: one message per line. `.gitattributes` keeps them byte exact (no line ending conversion), because `garbage.jsonl` tests a `\r\n` ending.

| File | What a receiver must do |
|---|---|
| `state_full.jsonl` | Parse every field. `motor_temp_f` is listed in `stale`, so it shows `--` even though a value is present. |
| `state_minimal.jsonl` | Parse. Every field shows `--`: nothing has been read yet. |
| `state_stale.jsonl` | Parse. `soc_pct`, `pack_v`, `pack_a`, `power_kw`, and `motor_temp_f` show `--` (stale). `ctrl_temp_f` shows `--` (null). `speed_mph` 0.0, `gear` N, `motor_rpm` 0, `bms_faults` `["cell_uv"]` show normally. |
| `hello.jsonl` | Parse. `proto` 1, `sim` true. |
| `log.jsonl` | Parse 4 log lines. The last two carry raw CAN frames (`frame`), one with no data bytes. |
| `unknown.jsonl` | Line 1: a state with `speed_mph` 3.5 and `gear` D; the unknown fields are ignored. Line 2: unknown type, ignore the whole line. Line 3: a hello, unknown field ignored. |
| `cmd.jsonl` | App to ESP32 commands. The ESP32 side must accept all 4. |
| `garbage.jsonl` | 12 lines. Exactly 3 are messages: the hello (line 1), state `seq` 2 (line 8), and state `seq` 3 (line 12, ends in `\r\n`). Drop the rest without crashing: ROM boot text, a cut off line, a JSON array, a JSON string, an empty line, a state whose `seq` is a string, an object with no `type`, and a line longer than 2048 bytes. |

The schema for every valid message is `protocol/schema/cartdash.schema.json`. A reference receiver that follows these rules is `tools/cartdash_proto.py`.
