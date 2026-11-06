# Courses

One course file per course, in the format described in `docs/course_format.md`, plus its aerial photo. Course data is © OpenStreetMap contributors, available under the Open Database License. Photos are USDA NAIP imagery via USGS The National Map, in the public domain.

| Course | Town | Course file | Holes ready | Scorecard | Photo | Notes |
|---|---|---|---|---|---|---|
| Bell Nob Golf Course | Gillette | `bell-nob-golf-course.geojson` | 18 of 18 | pars, handicaps, 6 tees | yes | Front 9 south of the clubhouse, back 9 north into the neighborhood. Mapped lengths match the Black tees within 3%, except hole 10 (+28 yd). |
| Bell Nob Short Course | Gillette | `bell-nob-short-course.geojson` | 9 of 9 | par 3 on every hole, 1,133 yd | yes | Built from 9 unnumbered holes inside Bell Nob's boundary. Hole order, numbers, and pars confirmed by the owner. |
| Gillette Golf Club | Gillette | `gillette-golf-club.geojson` | 9 of 9 | pars, handicaps, Yellow tees | yes | 9 holes. An eastern expansion was abandoned; its features are excluded in the overrides file. |
| Casper Country Club | Casper | `casper-country-club.geojson` | 18 of 18 | pars, handicaps, Blue tees | yes | |
| Newcastle Country Club | Newcastle | `newcastle-country-club.geojson` | 9 of 9 | pars from OpenStreetMap | yes | |

Files:
- `<course>.geojson`: the course file the app reads.
- `<course>.photo.jpg` and `.photo.json`: the aerial photo and where it sits.
- `<course>.overrides.json`: scorecard, exclusions, and short course settings, applied on every build.
- `osm/`: the raw OpenStreetMap downloads, so course files can be rebuilt without internet access.

Rebuild from the saved download (picks up the overrides file):

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
