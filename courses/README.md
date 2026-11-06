# Courses

One course file per course, in the format described in `docs/course_format.md`, plus its aerial photo. Course data is © OpenStreetMap contributors, available under the Open Database License. Photos are USDA NAIP imagery via USGS The National Map, in the public domain.

| Course | Town | Course file | Holes ready | Pars | Photo | Notes |
|---|---|---|---|---|---|---|
| Bell Nob Golf Course | Gillette | `bell-nob-golf-course.geojson` | 18 of 18 | missing | yes | A 9 hole short course is also mapped, without hole numbers, so it is not included. Hole 1's tees are mapped south of the clubhouse, so its line of play crosses the parking lot in the photo; worth checking. |
| Gillette Golf Club | Gillette | `gillette-golf-club.geojson` | 9 of 9 | missing | yes | Greens, tees, and fairways east of the 9 holes have no hole lines. The photo shows that ground still being graded, so those holes are newer than the photo. |
| Casper Country Club | Casper | `casper-country-club.geojson` | 18 of 18 | missing | yes | |
| Newcastle Country Club | Newcastle | `newcastle-country-club.geojson` | 9 of 9 | yes | yes | |

`osm/` holds the raw OpenStreetMap downloads, so a course file can be rebuilt without internet access:

```bash
python3 tools/course_from_osm.py build --osm-json courses/osm/bell-nob.json
```

After fixing a course on OpenStreetMap, download it again:

```bash
python3 tools/course_from_osm.py build --name "Bell Nob" --save-osm courses/osm/bell-nob.json
```

Check it by eye, on the drawn shapes or on the photo:

```bash
python3 tools/course_preview.py courses/bell-nob-golf-course.geojson --photo
```

Copy the `.geojson`, `.photo.jpg`, and `.photo.json` files to the head unit by USB drive or ADB.
