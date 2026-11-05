# Protocols

Decoded data formats for every source the ESP32 reads. The USB link between the ESP32 and the app is specified separately in `docs/usb_protocol.md`.

Each section says how sure we are: **expected** means taken from public documentation and not yet seen on this hardware, **confirmed** means checked on the cart.

## BMS over Bluetooth LE (JBD)

Status: **expected**. The BMS is managed with the JBD app, so it should speak the JBD protocol. Confirm the service and a few readings against the JBD app before the decoder depends on them.

GATT:
- Service `0xFF00`
- `0xFF01`: notify, responses arrive here
- `0xFF02`: write, requests go here

Request frame: `DD A5 <cmd> 00 <chk_hi> <chk_lo> 77`

| Request | Bytes |
|---|---|
| Basic info (cmd 0x03) | `DD A5 03 00 FF FD 77` |
| Cell voltages (cmd 0x04) | `DD A5 04 00 FF FC 77` |
| Hardware version (cmd 0x05) | `DD A5 05 00 FF FB 77` |

Response frame: `DD <cmd> <status> <len> <data ...> <chk_hi> <chk_lo> 77`. Status `00` means OK. The checksum is 0x10000 minus the byte sum of status, length, and data. A response is often split across several notifications, so collect bytes until the frame length is complete and it ends in `77`.

Basic info data, big endian:

| Offset | Size | Field | Unit |
|---|---|---|---|
| 0 | 2 | Pack voltage | 10 mV |
| 2 | 2 | Current, signed, positive is charging | 10 mA |
| 4 | 2 | Remaining capacity | 10 mAh |
| 6 | 2 | Nominal capacity | 10 mAh |
| 8 | 2 | Cycle count | |
| 10 | 2 | Production date (packed) | |
| 12 | 2 | Balancing, cells 1 to 16 (one bit per cell) | |
| 14 | 2 | Balancing, cells 17 to 32 | |
| 16 | 2 | Protection flags (see below) | |
| 18 | 1 | Software version | |
| 19 | 1 | State of charge | % |
| 20 | 1 | FET state: bit 0 charge, bit 1 discharge | |
| 21 | 1 | Cell count | |
| 22 | 1 | Temperature sensor count N | |
| 23 | 2 x N | Temperatures | 0.1 K (subtract 2731 for 0.1 C) |

Protection flag bits: 0 cell overvoltage, 1 cell undervoltage, 2 pack overvoltage, 3 pack undervoltage, 4 charge overtemp, 5 charge undertemp, 6 discharge overtemp, 7 discharge undertemp, 8 charge overcurrent, 9 discharge overcurrent, 10 short circuit, 11 front end IC error, 12 MOSFETs locked by software.

Cell voltages data: one big endian 16 bit value per cell, in mV.

The JBD current sign already matches the USB link convention (negative is discharge).

## Factory CAN bus (original Tianji controller to factory screen)

Status: not captured yet. Bitrate unknown. Fill this in from the capture sessions (see `tools/README.md`) and keep `docs/factory_can.dbc` in sync.

| ID | Rate | Bytes | Meaning | Scale and offset | Evidence (session, marker) | Confidence |
|---|---|---|---|---|---|---|
| | | | | | | |

## Kelly KAC7250ND

Status: not sniffed yet. Unknown whether it exposes CAN, and whether it broadcasts on its own or only answers requests.

Target fields: motor RPM, phase current, battery current, controller temp, motor temp, fault codes, direction.

| ID or command | Rate | Bytes | Meaning | Scale and offset | Confidence |
|---|---|---|---|---|---|
| | | | | | |
