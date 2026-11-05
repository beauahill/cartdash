# Wish list

Ideas that are out of scope for the current phases. Move an item into `docs/plan.md` when it is picked up.

## Charge state in Home Assistant while parked

Report SOC and charging status to Home Assistant with the key off, for example while plugged in at home.

Why it is not in the plan: the brief puts the ESP32 into light sleep 60 s after ACC off, and the cart charges with the key off. Doing this needs a change to the sleep rules.

Possible approach when it gets picked up:
- Stay awake while the BMS reports charge current, publishing at a slower rate.
- Otherwise wake on a timer every 10 to 15 minutes, read the BMS, publish, and sleep again.
- First confirm that the 12V converter (factory pin 9) stays on with the key off, and how much it draws.
