# Bezel

A new bezel to mount the Topway TS10s where the factory screen was. **Status: collecting measurements.** The design will be parametric (OpenSCAD) in `mechanical/bezel/`, so a wrong number is a one-line fix and a reprint, not a redesign.

## Measurements needed

Millimeters if you can; inches are fine if every number uses the same unit. Write "about" next to anything you are unsure of. A photo with a tape measure or ruler in the frame helps more than a number on its own.

### The head unit

| # | What | Value |
|---|---|---|
| H1 | Front panel (glass and frame): width x height | |
| H2 | Front panel thickness, glass face to where the metal body starts | |
| H3 | Visible screen area: width x height | |
| H4 | Border from the panel edge to the visible screen: left, right, top, bottom | |
| H5 | Metal body behind the panel: width x height x depth | |
| H6 | Where the body sits behind the panel: distance from the panel's left edge and top edge to the body's | |
| H7 | Mounting holes on the body: how many on each side, their positions (from the panel face and from the top), and the screw size if known (M4 or M5 are common) | |
| H8 | Depth needed behind the body for the plugs and cables, with them plugged in and bent the way they would go | |
| H9 | Anything on the front that must stay uncovered: buttons, microphone hole, light sensor, reset hole. Positions from the panel edges | |
| H10 | Weight (a kitchen scale is fine) | |

Photos: the front straight on, the back, each side (showing the mounting holes), and the rear with the cables plugged in.

### The dash

| # | What | Value |
|---|---|---|
| D1 | Factory screen opening: width x height, and the corner radius (round, sharp, or about how big) | |
| D2 | How the factory screen is held: screws, clips, or a bracket, and where they sit relative to the opening | |
| D3 | Dash panel thickness at the edge of the opening | |
| D4 | Depth behind the opening to the first obstruction (steering column, frame tube, wiring), at the center and at each corner | |
| D5 | Free space on the dash face around the opening: how far the bezel can extend left, right, up, and down before it hits switches, vents, or curves | |
| D6 | Is the face flat around the opening? Lay a straight edge across the opening, side to side and then top to bottom, and measure the biggest gap under it | |
| D7 | Angle of the dash face from vertical, with a phone level app laid flat on it | |
| D8 | Distance from the steering wheel rim to the dash face in front of the opening, at the closest point | |
| D9 | Where the ESP32 box (about 100 x 70 x 40 mm) could mount behind the dash, close to the factory plugs | |

Photos: the opening straight on from about 1 m, with a tape across it; the same from the driver's seat at eye height; a side view showing the angle and the steering wheel; behind the dash through the opening, showing D4.

If the dash face is curved, a cardboard template beats numbers. Press a piece of cardboard against the face, trace the opening and the outline the bezel may cover, cut it out, and photograph it flat next to a ruler.

## Questions

- Do you have a 3D printer? What is its bed size? The bezel for a 10 inch screen may be wider than the bed. If so it prints in two pieces that bolt or key together behind the face.
- Which filament? ASA is best in a cart: it takes sun and heat. PETG is fine. PLA softens in a hot cart and is not recommended.
- Do you want a small sun hood over the top of the screen? It helps readability in direct sun. Sun readability is the dash's hardest requirement.
- Should the bezel match the dash color, or plain black?

## Design notes

- The head unit body mounts to a bracket through its side holes. The bezel covers the gap between the screen and the opening. The dash does not carry the head unit by its front panel alone.
- The head unit's metal case must not touch the cart frame (`docs/wiring.md`, grounds).
- Leave a path for the USB, GPS, and harness cables, and room to unplug the head unit without removing the dash.
