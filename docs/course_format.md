# Course file format, version 1

One GeoJSON file per course in `courses/`, built by `tools/course_from_osm.py` and copied to the head unit. The app reads it with no internet. `tools/courselib.py` reads and writes this format and is the reference for the app's course code.

Coordinates are GeoJSON order: `[longitude, latitude]`, WGS84.

Files can be opened and edited in any GeoJSON editor (geojson.io, QGIS). Hand edits survive as long as the `kind` and `hole` properties stay. Prefer fixing errors in OpenStreetMap and rebuilding, so the fix helps everyone and is not lost on the next build.

## Structure

A `FeatureCollection`. Every feature has a `kind` property. The first feature is always the course itself.

```json
{"type": "FeatureCollection", "features": [
  {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[...]]},
   "properties": {"kind": "course", "format": 1, "name": "Bell Nob Golf Course", "holes": 18,
                  "source": "OpenStreetMap", "attribution": "© OpenStreetMap contributors",
                  "osm": "way/123456", "built": "2026-11-05"}},
  {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[...], [...]]},
   "properties": {"kind": "hole", "hole": 1, "par": 4, "handicap": 5, "osm": "way/234567"}},
  {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[...]]},
   "properties": {"kind": "green", "hole": 1, "osm": "way/345678"}},
  {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[...]]},
   "properties": {"kind": "bunker", "osm": "way/456789"}}
]}
```

## Kinds

Features that belong to a hole carry an integer `hole` property.

| `kind` | Geometry | `hole` | Meaning |
|---|---|---|---|
| `course` | Polygon, or null if the boundary is not mapped | no | Course boundary and metadata. Always first. Properties: `format`, `name`, `holes` (expected count, may be missing), `source`, `attribution`, `osm`, `built`, and from a scorecard `tees` (tee names, longest first) and `scorecard` (where the card came from). |
| `hole` | LineString, or null | yes | Line of play from the tee to the green. Properties: `par`, `handicap`, `yards` (scorecard yardage by tee name, like `{"Black": 564, "Blue": 516}`). A null geometry keeps the scorecard when no line is mapped. |
| `green` | Polygon | yes | Green outline. Required for yardage. |
| `tee` | Polygon or Point | yes | A tee box. A hole may have several. |
| `front`, `center`, `back` | Point | yes | Optional fixed yardage points. When present they replace the computed ones. |
| `pin` | Point | yes | Pin position from OpenStreetMap. Shown on the map only. |
| `fairway`, `bunker`, `water`, `rough`, `range` | Polygon or MultiPolygon | no | Drawn on the map. |
| `green`, `tee` without `hole` | Polygon or Point | no | Practice greens, or greens and tees of holes with no number. Drawn on the map, no yardage. |
| `cartpath` | LineString | no | Drawn on the map. |

Receivers ignore unknown kinds and unknown properties, like the USB link.

## How the app uses it

- **A hole is ready for yardage** when it has a `green` (or a fixed `center`) and a hole number.
- **Center** is the area center of the green outline, unless a fixed `center` exists.
- **Front and back** are where the line from the cart through the center crosses the green edge, nearest and farthest. Fixed `front` and `back` points win when present. On the green there is no front.
- **Current hole**: the hole whose line of play passes closest to the cart. Without a line, the tee to green center is used. The app adds hysteresis and manual previous and next.
- **Course screen trigger**: the cart is inside the `course` polygon. Boundaries can overlap (Bell Nob's short course sits inside Bell Nob's boundary), so when the cart is inside more than one, pick the course whose nearest hole line is closest, and let the driver switch.
- **Scorecard**: show par, and the yardage for the tee chosen in settings, next to the hole number.
- **Attribution**: show the `attribution` text on the course screen.

## Overrides files

`courses/<course>.overrides.json` holds what OpenStreetMap lacks or gets wrong for one course. `tools/course_from_osm.py` applies it every time it builds that course, so rebuilding from a fresh download keeps the fixes. The app never reads it; the results are in the course file.

```json
{
 "holes": 9,
 "scorecard": {"source": "where the card came from", "par": [5, 4, 4], "handicap": [5, 1, 3],
               "tees": {"Black": [564, 366, 413], "Blue": [516, 332, 382]}},
 "exclude": ["way/1491784729", "way/1491784730"],
 "exclude_reason": "why those features are left out",
 "short_course": {"name": "Bell Nob Short Course", "numbering": {"way/1491799753": 1},
                  "scorecard": {"par": [3, 3, 3]}}
}
```

| Key | Meaning |
|---|---|
| `name` | Course name, if OpenStreetMap's is not the one to show |
| `holes` | Number of holes, if OpenStreetMap does not say |
| `scorecard` | Lists by hole, first entry is hole 1. A par that differs from OpenStreetMap is reported and the card wins. Tee lists must be the same length, and handicaps must not repeat. |
| `exclude` | OpenStreetMap features to leave out entirely, like the greens of an abandoned expansion |
| `short_course` | Turn the hole lines that have no number into a second course, written to its own course file. `numbering` maps each hole line to its number; without it the order is inferred from the routing (the loop with the shortest walks from green to next tee, starting nearest the clubhouse) and the report says so. |

## Aerial photo files

Made by `tools/course_imagery.py`, next to the course file:

- `<course>.photo.jpg`: USGS NAIP aerial photo covering the course boundary plus a margin.
- `<course>.photo.json`: where the photo sits.

```json
{"format": 1, "course": "Bell Nob Golf Course", "image": "bell-nob-golf-course.photo.jpg",
 "crs": "EPSG:4326", "bounds": [-105.57, 44.27, -105.55, 44.29], "width": 3699, "height": 5234,
 "meters_per_pixel": 0.5, "source": "USGS NAIP Imagery, The National Map",
 "attribution": "Aerial imagery: USDA NAIP via USGS The National Map (public domain)", "downloaded": "2026-11-06"}
```

`bounds` is `[west, south, east, north]`. Pixels are linear in longitude and latitude from the north west corner:

```
x = (lon - west) / (east - west) * width
y = (north - lat) / (north - south) * height
```

The app decodes only the part of the JPEG on screen (Android `BitmapRegionDecoder`), so a large photo does not need a large amount of memory. The photo view shows the `attribution` text.

## Versioning

`format` changes only for breaking changes, as with the USB link protocol.
