#!/usr/bin/env python3
"""Download the aerial photo for a course: USGS NAIP imagery, which is public domain.

For each course file it writes, next to it:

    <course>.photo.jpg    the photo covering the course boundary plus a margin
    <course>.photo.json   bounds and size, so the app can place the photo

The photo is in plain longitude and latitude (EPSG:4326): pixel x is linear in
longitude and pixel y in latitude, from the north west corner. NAIP is mostly
0.6 m per pixel (0.3 m where newer flights exist); the default output of
0.5 m per pixel keeps all of that detail.

Needs Pillow (pip install pillow) and internet access to imagery.nationalmap.gov.

Examples:
    python3 tools/course_imagery.py courses/bell-nob-golf-course.geojson
    python3 tools/course_imagery.py courses/*.geojson
    python3 tools/course_imagery.py courses/casper-country-club.geojson --mpp 0.3
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import courselib as cl  # noqa: E402

SERVICE = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer"
ATTRIBUTION = "Aerial imagery: USDA NAIP via USGS The National Map (public domain)"
USER_AGENT = "cartdash-course-tool/0.1"
MAX_REQUEST_PX = 4000  # the service's limit per request
CHUNK_PX = 2000  # smaller requests are more reliable

Fetch = Callable[[str, Dict[str, str]], bytes]


@dataclass
class Grid:
    """The output photo's pixel grid, aligned so every chunk tiles exactly."""

    west: float
    north: float
    dlon: float  # degrees per pixel
    dlat: float
    width: int
    height: int

    @property
    def east(self) -> float:
        return self.west + self.width * self.dlon

    @property
    def south(self) -> float:
        return self.north - self.height * self.dlat

    def chunks(self, size: int = CHUNK_PX) -> List[Tuple[int, int, int, int, Tuple[float, float, float, float]]]:
        """(col, row, width, height, (west, south, east, north)) for each request."""
        out = []
        for row in range(0, self.height, size):
            h = min(size, self.height - row)
            for col in range(0, self.width, size):
                w = min(size, self.width - col)
                west = self.west + col * self.dlon
                north = self.north - row * self.dlat
                out.append((col, row, w, h, (west, north - h * self.dlat, west + w * self.dlon, north)))
        return out


def course_extent(course: cl.Course) -> List[cl.LonLat]:
    pts: List[cl.LonLat] = list(course.boundary or [])
    if not pts:
        for h in course.holes.values():
            pts += (h.line or []) + (h.green or []) + [p for t in h.tees for p in t]
        for ft in course.features:
            g = ft.geometry
            if g["type"] == "Polygon":
                pts += [tuple(p) for p in g["coordinates"][0]]
            elif g["type"] == "LineString":
                pts += [tuple(p) for p in g["coordinates"]]
    if not pts:
        raise SystemExit(f"{course.name}: nothing to cover (no boundary and no holes)")
    return pts


def make_grid(points: Sequence[cl.LonLat], mpp: float, margin_m: float) -> Grid:
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    center = ((min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2)
    frame = cl.LocalFrame(center)
    dlon = mpp / frame.kx
    dlat = mpp / frame.ky
    west = min(lons) - margin_m / frame.kx
    east = max(lons) + margin_m / frame.kx
    south = min(lats) - margin_m / frame.ky
    north = max(lats) + margin_m / frame.ky
    return Grid(west, north, dlon, dlat, int(math.ceil((east - west) / dlon)), int(math.ceil((north - south) / dlat)))


def say(text: str) -> None:
    print(text, flush=True)


def http_fetch(url: str, params: Dict[str, str], tries: int = 3) -> bytes:
    """GET with retries. The service can take minutes on an area nobody asked for recently."""
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=300) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == tries - 1:
                raise SystemExit(f"Could not download imagery: {exc}")
            time.sleep(5 * (attempt + 1))
    raise SystemExit("unreachable")


def export_params(bbox: Tuple[float, float, float, float], w: int, h: int) -> Dict[str, str]:
    west, south, east, north = bbox
    return {
        "bbox": f"{west:.9f},{south:.9f},{east:.9f},{north:.9f}",
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{w},{h}",
        "format": "jpg",
        "compressionQuality": "92",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }


def download_photo(grid: Grid, fetch: Fetch = http_fetch, pause_s: float = 0.5, log: Callable[[str], None] = say):
    """Fetch every chunk and stitch them. Returns (Pillow image, warnings)."""
    from PIL import Image

    photo = Image.new("RGB", (grid.width, grid.height))
    warnings = []
    chunks = grid.chunks()
    for i, (col, row, w, h, bbox) in enumerate(chunks, 1):
        started = time.time()
        data = fetch(SERVICE + "/exportImage", export_params(bbox, w, h))
        try:
            tile = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            raise SystemExit(f"The imagery service did not return an image: {data[:300].decode(errors='replace')}")
        if tile.size != (w, h):
            tile = tile.resize((w, h))
        lo, hi = tile.convert("L").getextrema()
        if hi - lo < 8:
            warnings.append(f"chunk {i} at column {col}, row {row} is blank; no imagery there")
        photo.paste(tile, (col, row))
        log(f"  chunk {i}/{len(chunks)} ({w}x{h}) in {time.time() - started:.0f} s")
        if pause_s and i < len(chunks):
            time.sleep(pause_s)
    return photo, warnings


def photo_paths(course_path: Path) -> Tuple[Path, Path]:
    base = course_path.with_suffix("")
    return base.with_name(base.name + ".photo.jpg"), base.with_name(base.name + ".photo.json")


def build(course_path: Path, mpp: float, margin_m: float, fetch: Fetch = http_fetch, quality: int = 85,
          pause_s: float = 0.5, log: Callable[[str], None] = say) -> dict:
    course = cl.load_course(course_path)
    grid = make_grid(course_extent(course), mpp, margin_m)
    if grid.width * grid.height > 120_000_000:
        raise SystemExit(f"{course.name}: {grid.width}x{grid.height} px is too big; use a larger --mpp")
    log(f"{course.name}: {grid.width}x{grid.height} px at {mpp} m per pixel, {len(grid.chunks())} requests")
    photo, warnings = download_photo(grid, fetch, pause_s, log)
    jpg, meta_path = photo_paths(course_path)
    photo.save(jpg, quality=quality, optimize=True, progressive=True)
    meta = {
        "format": 1,
        "course": course.name,
        "image": jpg.name,
        "crs": "EPSG:4326",
        "bounds": [grid.west, grid.south, grid.east, grid.north],
        "width": grid.width,
        "height": grid.height,
        "meters_per_pixel": mpp,
        "source": "USGS NAIP Imagery, The National Map",
        "service": SERVICE,
        "attribution": ATTRIBUTION,
        "downloaded": dt.date.today().isoformat(),
    }
    meta_path.write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    for w in warnings:
        log(f"  warning: {w}")
    log(f"  wrote {jpg} ({jpg.stat().st_size / 1e6:.1f} MB) and {meta_path.name}")
    return meta


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("courses", nargs="+", help="course .geojson files")
    p.add_argument("--mpp", type=float, default=0.5, help="meters per pixel (default 0.5)")
    p.add_argument("--margin", type=float, default=40.0, help="meters of photo beyond the course boundary (default 40)")
    p.add_argument("--quality", type=int, default=85, help="JPEG quality (default 85)")
    args = p.parse_args(argv)
    try:
        import PIL  # noqa: F401
    except ImportError:
        raise SystemExit("Pillow is needed: pip install pillow")
    for c in args.courses:
        if c.endswith(".photo.json"):
            continue
        build(Path(c), args.mpp, args.margin, quality=args.quality)
    return 0


if __name__ == "__main__":
    sys.exit(main())
