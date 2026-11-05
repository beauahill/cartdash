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
| `course` | Polygon, or null if the boundary is not mapped | no | Course boundary and metadata. Always first. Properties: `format`, `name`, `holes` (expected count, may be missing), `source`, `attribution`, `osm`, `built`. |
| `hole` | LineString, or null | yes | Line of play from the tee to the green. Properties: `par`, `handicap`. A null geometry keeps the par when no line is mapped. |
| `green` | Polygon | yes | Green outline. Required for yardage. |
| `tee` | Polygon or Point | yes | A tee box. A hole may have several. |
| `front`, `center`, `back` | Point | yes | Optional fixed yardage points. When present they replace the computed ones. |
| `pin` | Point | yes | Pin position from OpenStreetMap. Shown on the map only. |
| `fairway`, `bunker`, `water`, `rough`, `range` | Polygon or MultiPolygon | no | Drawn on the map. |
| `cartpath` | LineString | no | Drawn on the map. |

Receivers ignore unknown kinds and unknown properties, like the USB link.

## How the app uses it

- **A hole is ready for yardage** when it has a `green` (or a fixed `center`) and a hole number.
- **Center** is the area center of the green outline, unless a fixed `center` exists.
- **Front and back** are where the line from the cart through the center crosses the green edge, nearest and farthest. Fixed `front` and `back` points win when present. On the green there is no front.
- **Current hole**: the hole whose line of play passes closest to the cart. Without a line, the tee to green center is used. The app adds hysteresis and manual previous and next.
- **Course screen trigger**: the cart is inside the `course` polygon.
- **Attribution**: show the `attribution` text on the course screen.

## Versioning

`format` changes only for breaking changes, as with the USB link protocol.
