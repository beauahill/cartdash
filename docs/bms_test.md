# BMS Bluetooth test

A checklist for the first laptop test of the BMS (Phase 3, step 1 in `docs/plan.md`). It takes about 20 minutes at the cart. It answers the BMS rows in `docs/verify.md` and saves the raw data the ESP32 decoder will be tested against.

Tool: `tools/bms_probe.py`. More detail is in `tools/README.md` under "BMS probe".

## Before going to the cart

1. Update the repo and the Python packages (in the repo folder, with the venv active):

```bash
git pull
```

```bash
pip install -r tools/requirements.txt
```

2. Check that the laptop's Bluetooth is on. Look for `Powered: yes`:

```bash
bluetoothctl show
```

3. Have the JBD app on the phone, and something to write with.

## At the cart

The BMS accepts one Bluetooth connection at a time. **Close the JBD app on the phone, or turn the phone's Bluetooth off, before every command below.** Open the app again only between runs, to read its numbers.

### 1. Find the BMS

```bash
python3 tools/bms_probe.py --scan
```

The BMS is usually the strongest signal next to the cart, and its name is often the one the JBD app shows. Write down its address (looks like `A4:C1:38:12:34:56`).

### 2. One read, key off

```bash
python3 tools/bms_probe.py --address <address> --save parked
```

It prints:
- The services the BMS offers.
- The hardware version.
- Voltage, current, SOC, capacity, cycles, temperatures, the FET states and every cell voltage.
- The line the ESP32 will send.

Then open the JBD app and fill in the "parked" row of the table below.

### 3. Charging, 60 seconds

Plug in the charger, wait for it to start, close the app, then:

```bash
python3 tools/bms_probe.py --address <address> --watch 60 --save charging
```

The current should read **positive**. Fill in the "charging" row from the app afterwards.

### 4. A small load, 60 seconds (optional)

Charger unplugged, key on, headlights on. The current should read slightly negative:

```bash
python3 tools/bms_probe.py --address <address> --watch 60 --save lights
```

### 5. Optional: from the dash

Hold the laptop where the ESP32 will sit (behind the dash) and run the scan again. Write down the BMS's signal strength in dBm. Above about -80 dBm is comfortable; below -90 is marginal.

## Write down

| Run | JBD app: voltage | current | SOC | temperatures | lowest cell | highest cell | Probe agreed? |
|---|---|---|---|---|---|---|---|
| parked | | | | | | | |
| charging | | | | | | | |
| lights | | | | | | | |

Also note:
- Did the JBD app ask for a PIN when it connected? Yes or no only. **Never write the PIN down here or type it into the tool.**
- The BMS signal strength from the dash spot, if you did step 5.

## What the tool may say

| Message | Meaning | What to do |
|---|---|---|
| `Could not connect` | The phone still holds the connection, or the BMS is out of range | Close the app, turn the phone's Bluetooth off, stand closer |
| `No JBD service` | The BMS speaks something other than JBD | Send the printed service list to Claude |
| `No answer to the read requests` | The phone holds it, or this BMS wants its PIN before answering | Try once more with the phone's Bluetooth off. If it still fails, tell Claude (not the PIN) |
| `Bluetooth is not available` | Laptop Bluetooth is off or missing | `bluetoothctl power on` |

## Afterwards

Send Claude the tool's output and the table above. Or commit the new files in `captures/bms/` and copy the table into `captures/README.md` under "BMS captures":

```bash
git add captures && git commit -m "BMS captures from the cart" && git push
```

The captures hold only BMS readings and its Bluetooth address, never the PIN.
