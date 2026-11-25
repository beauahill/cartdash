# Bezel

Mounting the Topway TS10s where the factory screen was. **Status: measuring.** The design will be parametric (OpenSCAD) in `mechanical/bezel/`, so a wrong number is a one-line fix and a reprint, not a redesign.

## The factory setup (photos 2026-11-24)

- **Pod.** A box-shaped pod sits on top of the dash, in front of the steering column. It is screwed down to the dash from inside, through its floor, with about seven screws around a cable hole. Its top runs a little past the face, which makes a short built-in sun hood. The face leans back toward the windshield. Photos: `photos/dash-pod-side.jpg`, `photos/dash-pod-top.jpg`, `photos/dash-pod-open-front.jpg`, `photos/dash-pod-open-angle.jpg`.
- **Face plate.** A plate carries the factory screen, whose metal frame screws to the plate's back. The plate screws onto the pod at four bosses: two along the top and one on each side wall. Photos: `photos/factory-faceplate-front.jpg`, `photos/factory-faceplate-back.jpg`, `photos/factory-faceplate-side.jpg`.
- **Through the pod floor:** the 9 and 16 pin plugs, and an FM antenna lead with a Motorola plug. The head unit's radio antenna input can take that lead.

## Two ways to go

1. **A new face plate on the existing pod (try this first).**
   - It screws into the four bosses and holds the TS10s by its side mounting holes, through a bracket printed as part of the plate.
   - It keeps the factory look and the built-in hood, adds no new holes in the dash, and is the smallest print.
   - It works if two things are true:
     - The TS10s front panel fits within, or close to, the pod's face. The plate can stand a little proud of the face.
     - The TS10s body, with its plugs and cables, fits inside the pod's depth and can reach the floor hole.
2. **A new pod and face plate, if the TS10s does not fit.**
   - It screws to the dash through the same holes as the old pod, so the dash stays untouched.
   - It lets us set the screen angle and leave room for the ESP32 box.
   - It is a bigger print, in several parts.

What decides between them: the head unit's H1, H5, and H8 against the pod's P1 to P3 below.

## Measurements

Millimeters if you can; inches are fine if every number uses the same unit. Write "about" next to anything you are unsure of.

### First: trace the old face plate

This gives the face outline and the screw positions more accurately than anything else.

1. Lay the face plate face down on a sheet of paper or cardboard bigger than it, and trace around it.
2. Measure the center of each of the four bosses from the two nearest edges of the plate, and write the numbers on the tracing, next to that boss.
3. Write down the boss height, measured from the back of the plate.
4. Photograph the tracing straight down, with a tape measure lying along two edges.

The factory screen can stay in the plate while you do this.

### The pod

| # | What | Value |
|---|---|---|
| P1 | Opening at the face, inside: width along the top, width along the bottom, height | |
| P2 | Depth, straight in from the face to the back wall, at the center | |
| P3 | Inside size at the back wall: width x height (the pod tapers) | |
| P4 | Floor cable hole: its size, and its distance from the face and from the left wall | |
| P5 | How far the top (the hood) reaches past the face | |
| P6 | Angle of the face from vertical: a phone level app held flat on the installed face plate | |
| P7 | One of the four boss screws, taken out: thread diameter and length | |
| P8 | Steering wheel rim to the face, at the closest point | |
| P9 | Only for a new pod: the dash under it. Trace the pod's footprint and its screw holes on paper with the pod off, and photograph the bare dash with a tape across it | |

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

Photos of the head unit: the front straight on, the back, each side (showing the mounting holes), and the back with the cables plugged in, each with a ruler in the frame.

## Printing

The owner's printer is a Bambu Lab H2S: enclosed, with a heated chamber, and a bed of roughly 340 x 320 mm (check the exact size in Bambu Studio). So:
- **One piece.** A plate for a 10 inch screen fits on the bed, so it needs no split and no joint.
- **Black ASA**, on hand. The heated chamber keeps ASA from warping, and ASA takes sun and cart heat.
- **Face down on the textured PEI plate.** The visible face then comes out matte and textured, close to the factory plastic, with no supports on it.
- **Strength settings:** about 4 walls and 25% infill.
- **Threads:** heat-set brass inserts where the head unit bracket screws in, so the threads survive repeated removal. The plate gets plain through holes for the four boss screws, which are the factory screws reused.
- **Fit test first.** Print a thin outline of the plate with the four boss holes, about 2 mm thick, and check it against the pod. It takes a few minutes and little filament. If anything is off, fix it before the full plate.
- **Files.** The design comes as an OpenSCAD file plus a ready STL or 3MF in `mechanical/bezel/`, which Bambu Studio opens directly.

## Decided

- No deeper sun hood (owner, 2026-11-25). The pod's own short hood stays as it is.
- Black ASA.

## Design notes

- The head unit body mounts to a bracket through its side holes. The plate does not carry the head unit by its glass or front frame alone.
- The head unit's metal case must not touch the cart frame (`docs/wiring.md`, grounds). The pod and plate are plastic, so this holds as long as no screw reaches the frame.
- Leave a path from the head unit's back to the floor hole for the harness, USB, GPS, and FM antenna leads. Leave room to unplug the head unit without taking the pod off.
- The ESP32 box (with its 5 V buck and opto board, roughly 100 x 70 x 40 mm) goes inside the pod beside the head unit body if P2, P3, and H5 leave room. Otherwise it goes under the dash near the plugs.
