# Wish list

Ideas that are out of scope for the current phases. Move an item into `docs/plan.md` when it is picked up.

## Course GPS extras

Beyond front, center, and back yardage (Track G):
- Tap anywhere on the hole to get the distance from the cart to that spot and from that spot to the green (layup distance).
- Carry distances to bunkers and water on the current hole.
- Today's pin position, tapped on the green, used in place of the center.
- Sharper aerial photos than USGS NAIP, if the photo view looks too soft. Needs a commercial source that allows offline storage.
- Elevation adjusted "plays like" yardage.

## Charge state in Home Assistant while parked

Report SOC and charging status to Home Assistant with the key off, for example while plugged in at home.

Why it is not in the plan: the brief puts the ESP32 into light sleep 60 s after ACC off, and the cart charges with the key off. Doing this needs a change to the sleep rules.

Possible approach when it gets picked up:
- Stay awake while the BMS reports charge current, publishing at a slower rate.
- Otherwise wake on a timer every 10 to 15 minutes, read the BMS, publish, and sleep again.
- First confirm that the 12V converter (factory pin 9) stays on with the key off, and how much it draws.

## Reading the DROK shunt monitor

The DROK 200A shunt on the main negative has its own display. Reading it into the ESP32 is not planned, because the other sources cover it:
- The BMS measures all pack current, charge included, and gives SOC. The shunt does not see charge current.
- After Phase 4 the Kelly reports battery current faster than the BMS does.
- Measuring the shunt directly would mean a 75 mV measurement on the main negative, which is the cable that shifts under motor current, plus another wire run to the pack.

The DROK display can stay as a standalone backup gauge. Pick this up only if the BMS Bluetooth link turns out unreliable on the cart. If the DROK model has Bluetooth, reading that would be the easier route.

