# Courses

One course file per course, in the format described in `docs/course_format.md`. Built from OpenStreetMap with `tools/course_from_osm.py`; course data is © OpenStreetMap contributors, available under the Open Database License.

| Course | Town | File | Holes ready |
|---|---|---|---|
| Bell Nob | Gillette | not built yet | |
| Gillette Golf Club | Gillette | not built yet | |
| Casper Country Club | Casper | not built yet | |
| Newcastle Golf Course | Newcastle | not built yet | |

To rebuild a course after fixing it on OpenStreetMap:

```bash
python3 tools/course_from_osm.py build --name "Bell Nob" --region US-WY
```

Copy the `.geojson` files to the head unit by USB drive or ADB.
