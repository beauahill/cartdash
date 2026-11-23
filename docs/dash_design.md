# Dash design

The look of the drive dash and the course screen, chosen by the owner on 2026-11-23 from mockups:
- **Layout A**, twin round gauges, for the drive dash.
- **Layout C** for the course screen.
- **Blue accent.**
- **Speedometer from 0 to 45 mph.**
- **Night theme while the headlights are on.**

The mockup sources are in `docs/design/`: `dash_main.dc.html` and `course_screen.dc.html`. They are HTML with `{{ }}` placeholders filled in by the script at the bottom of each file, so the exact arc and tick math is there. The accent is a parameter in those files; ignore their red default.

The style is Ram head unit inspired, with blue in place of Ram's gold:
- Glossy black panels.
- Round dials with a chrome-looking rim.
- Tall condensed numerals.
- Accent-colored arcs with a soft glow at night.
- A row of rounded tiles along the bottom.

## Rules

- **Red and amber mean a warning, nothing else.** Never use them for decoration, accents, or normal states. This is why the accent is blue.
- **One unit of size.** Every size is in `u`, 1% of the screen height, as the app already does.
  - The mockups are 1000 x 600, so 6 mockup pixels are 1 u.
  - At 2000 x 1200 one mockup pixel is 2 screen pixels.
  - Widths are in u too: the screen is about 167 u wide at 2000 x 1200.
- **Missing or stale values** show `--` in the dim color, as today. A dial with a missing value shows only its gray track, no arc.
- **Tabular digits** on every number, so numbers do not shift sideways as they change.

## Type

- **Numbers:** Barlow Condensed Bold (700).
- **Labels:** Barlow Condensed SemiBold (600), all caps, letter spacing about 0.12 em.
- **Body text** in menus: Barlow Medium (500) and SemiBold (600).
- **Bundle the font files.** The fonts are under the SIL Open Font License. Bundle the TTF files in `android/app/src/main/res/font/` with the license file next to them. The cart has no internet, so do not use downloadable fonts.
  - Source: the Google Fonts repository on GitHub, `ofl/barlowcondensed` and `ofl/barlow`.
- **Check the digits:** confirm in the emulator that `fontFeatureSettings = "tnum"` keeps the speed number from shifting sideways.

## Colors

| Token | Night | Day | Use |
|---|---|---|---|
| accent | `#2D8CFF` | `#0A5FD6` | Dial arcs, active gear F, active buttons, icons, center yardage, cart dot |
| background | `#16181C` at the top to `#08090B` at 60% | `#F7F8FA` to `#E9ECF0` | Vertical gradient behind everything |
| panel | `#121418` | `#FFFFFF` | Tiles, buttons, yardage card |
| panelEdge | `#2B2F36` | `#C6CBD3` | 1 px border of panels, idle gear boxes, dividers |
| panelHighlight | white at 7% | `#FFFFFF` | 1 px line along the inside top edge of panels (the gloss) |
| dial | `#0E1013` | `#FFFFFF` | Dial face |
| rim | `#6A707A` at the top to `#1A1C20` at the bottom | `#FFFFFF` to `#9AA1AB` | Dial rim gradient, the chrome look |
| text | `#F3F5F8` | `#0B0C0E` | Numbers, major ticks |
| dim | `#9097A1` | `#4A505A` | Labels, units, `--` |
| track | `#24272D` | `#DCE0E6` | Unlit part of arcs and bars |
| tick | `#6E747E` | `#7A808A` | Minor ticks |
| inactive | `#3A3F47` | `#B6BCC5` | Outline of a signal light that is off |
| green | `#2BD96B` | `#0E9F4F` | Blinker arrows, low beam light, regen |
| blue | keep `#448AFF` | keep `#0040E0` | High beam light |
| amber | keep `#FFB300` | keep `#E08A00` | Cautions: regen into a full pack, gear R, SOC under 30% |
| red | keep `#FF1744` | keep `#D50000` | Warnings: faults, link lost, SOC under 15%, park brake, brake |

The glow is night only. Draw the arc once at about 2.2 times its stroke width in accent at 30% alpha, then the arc itself on top. This works on any API level and costs less than a blur. Do the same with green under a lit blinker arrow. Day has no glow.

## Day and night

- Night while `illum` is true (headlights on), day while it is false. While `illum` is unknown, keep the last theme, as the app does now, so a dropout at night does not flash the screen white.
- The menu has a theme override: Auto (default), Day, Night. It is saved.
- Check both themes outside in direct sun (Phase 6).

## Drive dash, layout A

Top to bottom: top bar, gauge row, bottom row.

Outer padding:
- 3.3 u at the top.
- 4.3 u at the sides.
- 3.7 u at the bottom.

There is 2.3 u between the three rows.

### Top bar, 9.7 u tall

- **Blinker arrows** at the far left and right, about 11 u wide.
  - Off: outline in `inactive`.
  - Flashing: filled `green` with the night glow.
  - The flashing itself comes from the `turn_left` and `turn_right` flags, which already stay true while the blinker is on.
- **Center group**, left to right:
  - Low beam light: a headlight icon, `green` when on.
  - High beam light: `blue` when on.
  - Clock: the head unit's time, 12 hour, 5.7 u. The "PM" is smaller and dim.
  - Park brake light: a P in a circle, `red` when on.
  - Brake light: `red` while the pedal is pressed.
  - Link dot: `green` while lines are arriving.
  - When a light is off or unknown, it is drawn as an outline in `inactive`.
- **SIM chip:** an amber chip in the center group while the data is simulated.
- **Warnings:** while any banner is active, the most severe banner replaces the center group, running the full width between the arrows.
  - Red banners come before amber ones.
  - A `+N` badge shows when more banners are waiting.
  - Banner texts and conditions stay as they are now.

### Gauge row

Speed dial on the left, center column, battery dial on the right. The dials are 62 u square and sit at the outer edges. The center column takes the rest of the width.

Both dials use the same parts:
- Face in `dial`.
- A 1 u rim with the `rim` gradient.
- A thin `panelEdge` ring just inside the rim.
- A 2.7 u track ring at 79% of the dial radius, with round caps.
- Ticks just inside the track.
- Labels inside the ticks.
- The arc sweeps 270 degrees, starting at the lower left (135 degrees clockwise from 3 o'clock) and ending at the lower right.

**Speed dial:**
- Scale 0 to 45 mph.
  - A minor tick every 1 mph.
  - A major tick and a label every 5 mph.
  - Above 45 mph the arc stops at full and the number shows the real speed.
- The accent arc runs from 0 to the shown speed. Use the same dead-banded speed as the number, so the arc and number agree.
- In the middle: the speed number at 25 u, with "MPH" under it at 4 u in `dim`.
- In the gap at the bottom of the dial: `speed_mode` in accent, all caps ("HIGH", "LOW"). It shows `--` in `dim` when unknown.

**Center column:**
- **Gear stack**, with F, N and R boxes about 14 u wide and 9.7 u tall, rounded.
  - The data says `D` for forward; show it as **F** to match the cart's shifter.
  - Active F: accent fill, white letter.
  - Active N: `text`-colored border, `text` letter.
  - Active R: amber fill.
  - Idle boxes: `panelEdge` border, `dim` letter.
  - All three are idle when the gear is unknown.
- **Power**, below the gear stack.
  - A label: "USING" while `power_kw` is negative, "REGEN" while it is positive.
  - The number shows the size of the value in kW, 7.7 u, one decimal.
  - Under the number is a bar with zero in the middle.
    - Discharge fills to the right in accent and is full at 20 kW.
    - Regen fills to the left in `green` and is full at 10 kW.
    - Both full-scale values are constants, to be tuned once the Kelly is in.
  - Small "REGEN" and "POWER" labels sit under the two ends of the bar.
- **Phase 6:** the trip distance goes under the power bar ("TRIP 4.2 mi"), once trips exist.

**Battery dial:**
- Scale 0 to 100%.
  - A minor tick every 10%.
  - A major tick at 0, 50 and 100, labeled E, 50 and F.
- **Color.** The arc and the number take the same color:
  - Accent from 30% up.
  - Amber under 30%.
  - Red under 15%.
- In the middle: the SOC number at 25 u, with a smaller "%".
- **Line under the number:**
  - Now: pack voltage ("66.4 V").
  - Phase 6: the range estimate ("31 MI RANGE").
- **Gap at the bottom of the dial:**
  - Now: pack current ("-48 A").
  - Phase 6: pack voltage, once the range takes the line above.

### Bottom row, 15.3 u tall

- **Four tiles** of equal width. Each has a small label above and the value at 5.7 u, with the unit smaller in `dim`.
  - **MOTOR °F.**
  - **CONTROLLER °F.**
  - **BATTERY °F:** the hottest of the BMS sensors.
  - **CELLS:** lowest to highest cell voltage, two decimals ("3.31 to 3.32").
  - The mockup's TRIP tile became BATTERY °F, because trip moves under the power bar in Phase 6.
- **Three buttons**, each 15.3 u square, with an accent icon over a small label:
  - **CARPLAY** launches the CarPlay app. Its package is a setting (Phase 6).
  - **COURSE** opens the course screen (Track G). Draw it dimmed until that screen exists.
  - **MENU** opens the menu.
- The tiles and buttons use `panel` fill, a 1 px `panelEdge` border, the `panelHighlight` top line, and 2.3 u corners.

The status line at the bottom of today's dash goes away. SIM moves to the top bar. The data source and firmware version move to the menu.

### Menu

A plain list screen in the same colors. Tapping outside it or a close button returns to the dash.

For now it holds:
- **Data source:** Sim or TCP, and USB from Phase 1. This replaces tapping SOURCE on today's status line.
- **Theme:** Auto, Day or Night.
- **Firmware:** version and uptime, from `hello`.
- **Screen readout:**
  - `densityDpi`.
  - The screen size in px and in dp.
  - The size of `u` in px.

  This answers the screen density VERIFY item in `docs/verify.md` on the real head unit.
- **App log:** the last 200 `log` lines from the ESP32, for debugging on the head unit while ADB is locked behind the unknown developer options code.

The rest of the settings join in Phase 6.

## Course screen, layout C

### Top strip, 7.3 u tall

Left side:
- The left blinker arrow, smaller.
- Speed, at 5.7 u with "MPH".
- A small gear chip (accent F, amber R).

Center:
- The clock.

Right side:
- A small SOC bar and percent, in the same colors as the battery dial.
- The right blinker arrow.

The most severe banner replaces the clock while one is active. Tapping the strip goes back to the drive dash. Android back does nothing on the launcher activity (Phase 1).

### Map panel

- The left 54% of the width and the full height below the strip, with 2.7 u corners and a 1 px `panelEdge` border.
- The hole is drawn with the tee at the bottom and the green at the top (Track G).
- On top of the hole:
  - **Cart dot:** accent, with a white ring and a soft accent halo.
  - **Line of play:** a dashed line from the cart to the green center, in `text`.
  - **Front and back:** small white dots on the green edge, labeled F and B.
  - **Center:** a slightly larger accent dot.
- **Corner labels:**
  - Top left: a course chip with the course name and tees ("BELL NOB · BLACK TEES") on a translucent background.
  - Bottom right: "© OpenStreetMap contributors" in small text.
- Photo view draws the same marks over the aerial photo.

Drawn view colors:

| Feature | Night | Day |
|---|---|---|
| Rough (background) | `#16231A` | `#CFE3C0` |
| Trees | `#0E1811` | `#A6CB95` |
| Fairway | `#2E5E37` | `#8FC97A` |
| Mowing stripes over the fairway | white at 5% | white at 18% |
| Green | `#3E9B4C` | `#5DB65A` |
| Fringe (ring around the green) | fairway color | fairway color |
| Bunker | `#CDBB8A` | `#EFE2B5` |
| Water | `#1F5A96` | `#6FA8DC` |
| Tee | `#3A7A45` | `#74B866` |

### Right column

- **Header:** "HOLE 7" at 11 u on the left. Two lines on the right:
  - "PAR 5" in `text`.
  - "564 YD · HCP 1" in `dim`. The yards are from the chosen tees.
- **Yardage card** (`panel`), with thin dividers between three rows:
  - **BACK:** number at 9.7 u.
  - **CENTER:** the biggest number on the screen, 25 u, in accent with the night glow, and a short accent bar on the card's left edge.
  - **FRONT:** number at 9.7 u.
  - When GPS accuracy is worse than about 10 yards (Track G), the numbers go `dim` and a "GPS ±14 YD" line shows in the card.
  - With no GPS fix, the numbers show `--`.
- **Controls row,** 10 u tall:
  - A previous-hole button on the left and a next-hole button on the right.
  - Between them, a DRAWN / PHOTO switch. The active side is filled with accent. The choice is remembered.

## Not decided yet

- Gear source after the Kelly swap (Phase 4) does not change the look.
- The overlay strip over CarPlay (Phase 6) should reuse the course screen's top strip.
