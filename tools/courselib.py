"""Course files and yardage math.

This is the Python reference for the app's course code (course/Yardage.kt).
The format is described in docs/course_format.md. Coordinates are GeoJSON
order everywhere: (lon, lat).

Distances use a flat local frame around a point of interest. At golf
distances (under 1 km) the error is far below GPS error.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

LonLat = Tuple[float, float]
Ring = List[LonLat]

FORMAT_VERSION = 1
YARDS_PER_METER = 1.0936133
EARTH_RADIUS_M = 6371008.8
OSM_ATTRIBUTION = "© OpenStreetMap contributors"

AREA_KINDS = ("fairway", "bunker", "water", "rough", "range", "tee", "green")
HOLE_KINDS = ("green", "tee", "hole", "front", "center", "back", "pin")


# Geometry --------------------------------------------------------------------


class LocalFrame:
    """Flat x (east) and y (north) meters around an origin."""

    def __init__(self, origin: LonLat):
        self.lon0, self.lat0 = origin
        self.ky = EARTH_RADIUS_M * math.pi / 180.0
        self.kx = self.ky * math.cos(math.radians(self.lat0))

    def xy(self, p: LonLat) -> Tuple[float, float]:
        return ((p[0] - self.lon0) * self.kx, (p[1] - self.lat0) * self.ky)

    def lonlat(self, x: float, y: float) -> LonLat:
        return (self.lon0 + x / self.kx, self.lat0 + y / self.ky)


def distance_m(a: LonLat, b: LonLat) -> float:
    """Great circle distance in meters."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def yards(meters: float) -> float:
    return meters * YARDS_PER_METER


def open_ring(ring: Sequence[LonLat]) -> List[LonLat]:
    """Ring without the repeated closing point."""
    pts = list(ring)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def centroid(ring: Sequence[LonLat]) -> LonLat:
    """Area weighted center of a polygon ring. Falls back to the vertex mean for degenerate rings."""
    pts = open_ring(ring)
    if not pts:
        raise ValueError("empty ring")
    mean = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    if len(pts) < 3:
        return mean
    f = LocalFrame(mean)
    xy = [f.xy(p) for p in pts]
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(xy, xy[1:] + xy[:1]):
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if abs(a) < 1e-9:
        return mean
    return f.lonlat(cx / (3 * a), cy / (3 * a))


def area_m2(ring: Sequence[LonLat]) -> float:
    pts = open_ring(ring)
    if len(pts) < 3:
        return 0.0
    f = LocalFrame(pts[0])
    xy = [f.xy(p) for p in pts]
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(xy, xy[1:] + xy[:1]))) / 2


def contains(ring: Sequence[LonLat], p: LonLat) -> bool:
    """Point in polygon (even-odd rule)."""
    pts = open_ring(ring)
    inside = False
    x, y = p
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xc:
                inside = not inside
    return inside


def point_segment_m(p: LonLat, a: LonLat, b: LonLat) -> Tuple[float, float]:
    """(distance in meters, position along the segment 0..1) from p to segment ab."""
    f = LocalFrame(p)
    ax, ay = f.xy(a)
    bx, by = f.xy(b)
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, (-ax * dx - ay * dy) / L2))
    return math.hypot(ax + u * dx, ay + u * dy), u


def polyline_length_m(line: Sequence[LonLat]) -> float:
    return sum(distance_m(a, b) for a, b in zip(line, line[1:]))


def point_polyline_m(p: LonLat, line: Sequence[LonLat]) -> Tuple[float, float]:
    """(distance in meters, share of the line's length before the closest point)."""
    if len(line) == 1:
        return distance_m(p, line[0]), 0.0
    total = polyline_length_m(line) or 1.0
    best = (float("inf"), 0.0)
    walked = 0.0
    for a, b in zip(line, line[1:]):
        seg = distance_m(a, b)
        d, u = point_segment_m(p, a, b)
        if d < best[0]:
            best = (d, (walked + u * seg) / total)
        walked += seg
    return best


def point_ring_m(p: LonLat, ring: Sequence[LonLat]) -> float:
    """Distance from p to a polygon in meters, 0 if inside."""
    if contains(ring, p):
        return 0.0
    pts = open_ring(ring)
    return min(point_segment_m(p, a, b)[0] for a, b in zip(pts, pts[1:] + pts[:1]))


# Yardage ---------------------------------------------------------------------


def _crossings(p: Tuple[float, float], d: Tuple[float, float], pts: Sequence[Tuple[float, float]]) -> List[float]:
    """Values of t > 0 where the ray p + t*d crosses the edges of polygon pts (flat x/y)."""
    px, py = p
    dx, dy = d
    ts = []
    for (ax, ay), (bx, by) in zip(pts, list(pts[1:]) + list(pts[:1])):
        ex, ey = bx - ax, by - ay
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue  # parallel to this edge
        wx, wy = ax - px, ay - py
        t = (wx * ey - wy * ex) / den
        u = (wx * dy - wy * dx) / den
        if 0.0 <= u <= 1.0 and t > 0:
            ts.append(t)
    return ts


@dataclass
class Yardage:
    front: Optional[float]  # yards, None when the cart is on the green or no edge is crossed
    center: float
    back: Optional[float]
    front_point: Optional[LonLat] = None
    center_point: Optional[LonLat] = None
    back_point: Optional[LonLat] = None


def green_yardage(cart: LonLat, green: Sequence[LonLat], fixed: Optional[Dict[str, LonLat]] = None) -> Yardage:
    """Front, center, and back yardage from the cart to a green.

    Center is the middle of the green outline. Front and back are where the
    line from the cart through the center crosses the green edge, nearest and
    farthest. Fixed points from the course file win over computed ones.
    """
    fixed = fixed or {}
    c = fixed.get("center") or centroid(green)
    f = LocalFrame(c)
    px, py = f.xy(cart)
    dx, dy = -px, -py  # from the cart to the center (the center is the frame origin)

    front_t: Optional[float] = None
    back_t: Optional[float] = None
    if math.hypot(dx, dy) > 1e-6:
        ts = _crossings((px, py), (dx, dy), [f.xy(p) for p in open_ring(green)])
        if ts:
            back_t = max(ts)
            if not contains(green, cart):  # on the green there is no front
                front_t = min(ts)

    def at(t: Optional[float]) -> Optional[LonLat]:
        return None if t is None else f.lonlat(px + t * dx, py + t * dy)

    front_pt, back_pt = at(front_t), at(back_t)
    if "front" in fixed:
        front_pt = fixed["front"]
    if "back" in fixed:
        back_pt = fixed["back"]
    return Yardage(
        front=None if front_pt is None else yards(distance_m(cart, front_pt)),
        center=yards(distance_m(cart, c)),
        back=None if back_pt is None else yards(distance_m(cart, back_pt)),
        front_point=front_pt,
        center_point=c,
        back_point=back_pt,
    )


# Course model ----------------------------------------------------------------


@dataclass
class Hole:
    number: int
    par: Optional[int] = None
    handicap: Optional[int] = None
    line: Optional[List[LonLat]] = None  # line of play, tee to green
    green: Optional[Ring] = None
    tees: List[List[LonLat]] = field(default_factory=list)  # rings, or a single point
    fixed: Dict[str, LonLat] = field(default_factory=dict)  # front, center, back
    osm: Dict[str, str] = field(default_factory=dict)  # kind -> "way/123"

    def green_center(self) -> Optional[LonLat]:
        if "center" in self.fixed:
            return self.fixed["center"]
        return centroid(self.green) if self.green else None

    def play_line(self) -> Optional[List[LonLat]]:
        """The line of play, or tee to green center when no line is mapped."""
        if self.line and len(self.line) >= 2:
            return self.line
        gc = self.green_center()
        if gc and self.tees:
            return [centroid(self.tees[0]), gc]
        return None

    @property
    def complete(self) -> bool:
        return self.green is not None or "center" in self.fixed


@dataclass
class Feature:
    kind: str
    geometry: dict  # GeoJSON geometry
    osm: Optional[str] = None


@dataclass
class Course:
    name: str
    holes: Dict[int, Hole] = field(default_factory=dict)
    features: List[Feature] = field(default_factory=list)  # drawn only: fairways, bunkers, water...
    boundary: Optional[Ring] = None
    expected_holes: Optional[int] = None
    osm: Optional[str] = None
    source: str = "OpenStreetMap"
    attribution: str = OSM_ATTRIBUTION
    built: Optional[str] = None


def nearest_hole(cart: LonLat, course: Course) -> Optional[int]:
    """Hole whose line of play passes closest to the cart. The app adds hysteresis on top."""
    best: Tuple[float, Optional[int]] = (float("inf"), None)
    for n, h in sorted(course.holes.items()):
        line = h.play_line()
        if line:
            d = point_polyline_m(cart, line)[0]
        elif h.green_center():
            d = distance_m(cart, h.green_center())
        else:
            continue
        if d < best[0]:
            best = (d, n)
    return best[1]


# Course files (GeoJSON) --------------------------------------------------------


def _poly(ring: Sequence[LonLat]) -> dict:
    pts = [list(p) for p in open_ring(ring)]
    return {"type": "Polygon", "coordinates": [pts + [pts[0]]]}


def _shape(points: Sequence[LonLat]) -> dict:
    if len(points) == 1:
        return {"type": "Point", "coordinates": list(points[0])}
    return _poly(points)


def _feat(geometry: Optional[dict], **props) -> dict:
    return {"type": "Feature", "properties": {k: v for k, v in props.items() if v is not None}, "geometry": geometry}


def to_geojson(course: Course) -> dict:
    feats = [
        _feat(
            _poly(course.boundary) if course.boundary else None,
            kind="course",
            format=FORMAT_VERSION,
            name=course.name,
            holes=course.expected_holes,
            source=course.source,
            attribution=course.attribution,
            osm=course.osm,
            built=course.built,
        )
    ]
    for n, h in sorted(course.holes.items()):
        if h.line:
            feats.append(_feat({"type": "LineString", "coordinates": [list(p) for p in h.line]},
                               kind="hole", hole=n, par=h.par, handicap=h.handicap, osm=h.osm.get("hole")))
        if h.green:
            feats.append(_feat(_poly(h.green), kind="green", hole=n, osm=h.osm.get("green")))
        for tee in h.tees:
            feats.append(_feat(_shape(tee), kind="tee", hole=n))
        for name, p in sorted(h.fixed.items()):
            feats.append(_feat({"type": "Point", "coordinates": list(p)}, kind=name, hole=n))
        if not h.line and h.par is not None:
            # Keep par even when no line of play is mapped.
            feats.append(_feat(None, kind="hole", hole=n, par=h.par, handicap=h.handicap))
    for ft in course.features:
        feats.append(_feat(ft.geometry, kind=ft.kind, osm=ft.osm))
    return {"type": "FeatureCollection", "features": feats}


def _outer(geom: dict) -> Optional[List[LonLat]]:
    if not geom:
        return None
    if geom["type"] == "Polygon":
        return [tuple(p) for p in geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [tuple(p) for p in max(geom["coordinates"], key=lambda poly: len(poly[0]))[0]]
    if geom["type"] == "Point":
        return [tuple(geom["coordinates"])]
    return None


def from_geojson(data: dict) -> Course:
    course = Course(name="")
    for ft in data.get("features", []):
        props = ft.get("properties") or {}
        kind = props.get("kind")
        geom = ft.get("geometry")
        n = props.get("hole")
        if kind == "course":
            course.name = props.get("name", "")
            course.expected_holes = props.get("holes")
            course.osm = props.get("osm")
            course.source = props.get("source", course.source)
            course.attribution = props.get("attribution", course.attribution)
            course.built = props.get("built")
            course.boundary = _outer(geom)
            continue
        if isinstance(n, int) and kind in HOLE_KINDS:
            h = course.holes.setdefault(n, Hole(n))
            if kind == "hole":
                h.par = props.get("par", h.par)
                h.handicap = props.get("handicap", h.handicap)
                if geom and geom["type"] == "LineString":
                    h.line = [tuple(p) for p in geom["coordinates"]]
            elif kind == "green":
                h.green = _outer(geom)
            elif kind == "tee":
                h.tees.append(_outer(geom))
            elif kind in ("front", "center", "back", "pin") and geom and geom["type"] == "Point":
                h.fixed[kind] = tuple(geom["coordinates"])
            continue
        if geom:
            course.features.append(Feature(kind or "other", geom, props.get("osm")))
    return course


def write_course(course: Course, path: Path) -> None:
    Path(path).write_text(json.dumps(to_geojson(course), indent=1) + "\n", encoding="utf-8")


def load_course(path: Path) -> Course:
    return from_geojson(json.loads(Path(path).read_text(encoding="utf-8")))
