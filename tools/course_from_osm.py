#!/usr/bin/env python3
"""Build a Cart Dash course file from OpenStreetMap and report what is missing.

Commands:
    list     golf courses in a region, with their OSM IDs
    build    write courses/<name>.geojson for one course and print a coverage report
    report   coverage report for an existing course file (after hand edits)

Examples:
    python3 tools/course_from_osm.py list --region US-WY
    python3 tools/course_from_osm.py build --name "Bell Nob" --region US-WY
    python3 tools/course_from_osm.py build --osm-id way/123456789
    python3 tools/course_from_osm.py build --osm-json saved.json
    python3 tools/course_from_osm.py report courses/bell-nob-golf-course.geojson

What OpenStreetMap needs for a hole to work in the app: a green outline
(golf=green) and a hole number. The number comes from the hole's line of play
(golf=hole with ref=<number>, drawn from tee to green), or from ref on the
green itself. Tees, fairways, bunkers, and water make the map better.

Fix gaps in the OpenStreetMap editor (the report prints a link), wait a few
minutes for Overpass to pick up the edit, and build again. Course data is
© OpenStreetMap contributors, under the ODbL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import courselib as cl  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "courses"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "cartdash-course-tool/0.1"

GOLF_KINDS = {
    "green": "green",
    "tee": "tee",
    "hole": "hole",
    "fairway": "fairway",
    "bunker": "bunker",
    "water_hazard": "water",
    "lateral_water_hazard": "water",
    "rough": "rough",
    "driving_range": "range",
    "pin": "pin",
    "cartpath": "cartpath",
    "path": "cartpath",
}
DRAWN_KINDS = ("fairway", "bunker", "water", "rough", "range", "cartpath")
GREEN_LINK_M = 40.0  # a hole line's end must be this close to a green to claim it
TEE_LINK_M = 25.0  # a tee must be this close to the first half of a hole line
COURSE_MARGIN_M = 40.0  # features this far outside the course boundary still count


# Overpass ----------------------------------------------------------------------


def _ql_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _regex_escape(text: str) -> str:
    """Escape POSIX regex metacharacters only (Python's re.escape also escapes spaces)."""
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", text)


def query_list(region: Optional[str], name: Optional[str] = None) -> str:
    flt = f'["name"~"{_ql_string(_regex_escape(name))}",i]' if name else ""
    if region:
        return (
            "[out:json][timeout:120];\n"
            f'area["ISO3166-2"="{_ql_string(region)}"]->.r;\n'
            f'nwr["leisure"="golf_course"]{flt}(area.r);\n'
            "out tags center;"
        )
    return f'[out:json][timeout:180];\nnwr["leisure"="golf_course"]{flt};\nout tags center;'


def query_course(osm_type: str, osm_id: int) -> str:
    return f"[out:json][timeout:60];\n{osm_type}({osm_id});\nout geom;"


def query_features(bbox: Tuple[float, float, float, float]) -> str:
    s, w, n, e = (f"{v:.6f}" for v in bbox)
    box = f"({s},{w},{n},{e})"
    return f'[out:json][timeout:180];\n(\n  nwr["golf"]{box};\n  nwr["natural"="water"]{box};\n);\nout geom;'


def overpass(query: str, url: str = OVERPASS_URL, tries: int = 3) -> dict:
    data = urllib.parse.urlencode({"data": query}).encode()
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 502, 503, 504) and attempt < tries - 1:
                wait = 15 * (attempt + 1)
                print(f"Overpass is busy ({exc.code}), retrying in {wait} s", file=sys.stderr)
                time.sleep(wait)
                continue
            body = exc.read()[:300].decode(errors="replace")
            raise SystemExit(f"Overpass error {exc.code}: {body}")
        except urllib.error.URLError as exc:
            raise SystemExit(f"Could not reach {url}: {exc.reason}")
    raise SystemExit("Overpass did not answer")


# OSM elements to geometry --------------------------------------------------------


def ref_of(el: dict) -> str:
    return f"{el['type']}/{el['id']}"


def parse_ref(text: str) -> Tuple[str, int]:
    m = re.fullmatch(r"(node|way|relation)/(\d+)", text.strip())
    if not m:
        raise SystemExit(f"OSM ID must look like way/123 or relation/456, not {text!r}")
    return m.group(1), int(m.group(2))


def _coords(geometry: Sequence[dict]) -> List[cl.LonLat]:
    return [(g["lon"], g["lat"]) for g in geometry if g]


def assemble_rings(segments: Iterable[List[cl.LonLat]]) -> List[List[cl.LonLat]]:
    """Join way segments that share end points into closed rings. Open leftovers are dropped."""
    pending = [list(s) for s in segments if len(s) >= 2]
    rings = []
    while pending:
        ring = pending.pop(0)
        progress = True
        while ring[0] != ring[-1] and progress:
            progress = False
            for i, seg in enumerate(pending):
                if seg[0] == ring[-1]:
                    ring += seg[1:]
                elif seg[-1] == ring[-1]:
                    ring += seg[-2::-1]
                elif seg[-1] == ring[0]:
                    ring = seg[:-1] + ring
                elif seg[0] == ring[0]:
                    ring = seg[:0:-1] + ring
                else:
                    continue
                pending.pop(i)
                progress = True
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def element_geometry(el: dict) -> Optional[dict]:
    """GeoJSON geometry for an Overpass element fetched with `out geom`."""
    if el["type"] == "node":
        return {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
    if el["type"] == "way":
        pts = _coords(el.get("geometry") or [])
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return {"type": "Polygon", "coordinates": [[list(p) for p in pts]]}
        if len(pts) >= 2:
            return {"type": "LineString", "coordinates": [list(p) for p in pts]}
        return None
    if el["type"] == "relation":
        outers, inners = [], []
        for m in el.get("members") or []:
            if m.get("type") != "way" or not m.get("geometry"):
                continue
            (inners if m.get("role") == "inner" else outers).append(_coords(m["geometry"]))
        outer_rings = assemble_rings(outers)
        inner_rings = assemble_rings(inners)
        if not outer_rings:
            return None
        polys = [[ring] for ring in outer_rings]
        for inner in inner_rings:
            for poly in polys:
                if cl.contains(poly[0], inner[0]):
                    poly.append(inner)
                    break
        polys_json = [[[list(p) for p in ring] for ring in poly] for poly in polys]
        if len(polys_json) == 1:
            return {"type": "Polygon", "coordinates": polys_json[0]}
        return {"type": "MultiPolygon", "coordinates": polys_json}
    return None


def outer_ring(geom: Optional[dict]) -> Optional[List[cl.LonLat]]:
    if not geom:
        return None
    if geom["type"] == "Polygon":
        return [tuple(p) for p in geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        biggest = max(geom["coordinates"], key=lambda poly: cl.area_m2([tuple(p) for p in poly[0]]))
        return [tuple(p) for p in biggest[0]]
    return None


def anchor(geom: dict) -> cl.LonLat:
    """A representative point: polygon center, line midpoint, or the point itself."""
    if geom["type"] == "Point":
        return tuple(geom["coordinates"])
    if geom["type"] == "LineString":
        pts = geom["coordinates"]
        return tuple(pts[len(pts) // 2])
    return cl.centroid(outer_ring(geom))


def kind_of(tags: dict) -> Optional[str]:
    if tags.get("leisure") == "golf_course":
        return "course"
    golf = tags.get("golf")
    if golf in GOLF_KINDS:
        return GOLF_KINDS[golf]
    if tags.get("natural") == "water":
        return "water"
    return None


def int_tag(tags: dict, key: str) -> Optional[int]:
    m = re.match(r"\s*(\d+)", str(tags.get(key, "")))
    return int(m.group(1)) if m else None


# Building a course ---------------------------------------------------------------


@dataclass
class BuildNotes:
    warnings: List[str] = field(default_factory=list)
    unlinked_greens: List[str] = field(default_factory=list)
    unlinked_tees: int = 0
    skipped_outside: int = 0
    excluded: int = 0
    numbering_inferred: bool = False
    extra_courses: List[Tuple[cl.Course, "BuildNotes"]] = field(default_factory=list)


def find_course_element(elements: Sequence[dict], course_ref: Optional[str]) -> dict:
    courses = [e for e in elements if (e.get("tags") or {}).get("leisure") == "golf_course"]
    if course_ref:
        for e in courses:
            if ref_of(e) == course_ref:
                return e
        raise SystemExit(f"{course_ref} is not a golf course in this data")
    if len(courses) != 1:
        names = ", ".join(f"{ref_of(e)} {(e.get('tags') or {}).get('name', '?')}" for e in courses) or "none"
        raise SystemExit(f"Expected one golf course in the data, found: {names}. Pick one with --osm-id.")
    return courses[0]


def link_greens(holes: Dict[int, cl.Hole], greens: Sequence[Tuple[dict, dict]]) -> List[Tuple[dict, dict]]:
    """Give each hole its green: by the green's own ref, else the green where its line ends.

    Returns the greens no hole claimed. A double green may serve two holes.
    """
    pool = []
    for el, geom in greens:
        n = int_tag(el.get("tags") or {}, "ref")
        if n is not None:  # the green's own number wins, even for a hole with no line of play
            h = holes.setdefault(n, cl.Hole(n))
            h.green = outer_ring(geom)
            h.osm["green"] = ref_of(el)
        else:
            pool.append((el, geom))
    claimed = set()
    for n, h in sorted(holes.items()):
        if h.green is not None or not h.line:
            continue
        best = None
        for i, (el, geom) in enumerate(pool):
            d = cl.point_ring_m(h.line[-1], outer_ring(geom))
            if d <= GREEN_LINK_M and (best is None or d < best[0]):
                best = (d, i)
        if best is not None:
            el, geom = pool[best[1]]
            h.green = outer_ring(geom)
            h.osm["green"] = ref_of(el)
            claimed.add(best[1])
    return [g for i, g in enumerate(pool) if i not in claimed]


def link_tees(holes: Dict[int, cl.Hole], tees: Sequence[Tuple[dict, dict]], use_ref: bool = True) -> List[Tuple[dict, dict]]:
    """Give each tee to a hole: by ref, else the hole whose first half passes closest. Returns the rest."""
    rest = []
    for el, geom in tees:
        shape = [anchor(geom)] if geom["type"] == "Point" else outer_ring(geom)
        n = int_tag(el.get("tags") or {}, "ref") if use_ref else None
        if n is None or n not in holes:
            best = None
            for hn, h in holes.items():
                if not h.line:
                    continue
                d, along = cl.point_polyline_m(anchor(geom), h.line)
                if d <= TEE_LINK_M and along <= 0.5 and (best is None or d < best[0]):
                    best = (d, hn)
            n = best[1] if best else None
        if n is None:
            rest.append((el, geom))
            continue
        holes[n].tees.append(shape)
    return rest


def infer_order(lines: Sequence[Sequence[cl.LonLat]], start_near: Optional[cl.LonLat] = None) -> List[int]:
    """Playing order of unnumbered holes: the loop that walks least from each green to the next tee.

    Starts at the hole whose tee is nearest `start_near` (the clubhouse), or after the
    longest walk in the loop when no start is given. A guess: always confirm it.
    """
    n = len(lines)
    if n <= 1:
        return list(range(n))
    cost = [[cl.distance_m(lines[i][-1], lines[j][0]) for j in range(n)] for i in range(n)]
    if n <= 10:
        best: Optional[Tuple[float, Tuple[int, ...]]] = None
        for perm in itertools.permutations(range(1, n)):
            cyc = (0,) + perm
            c = sum(cost[cyc[k]][cyc[(k + 1) % n]] for k in range(n))
            if best is None or c < best[0]:
                best = (c, cyc)
        cyc_list = list(best[1])
    else:
        cyc_list = [0]
        while len(cyc_list) < n:
            last = cyc_list[-1]
            cyc_list.append(min((j for j in range(n) if j not in cyc_list), key=lambda j: cost[last][j]))
    if start_near is not None:
        k = min(range(n), key=lambda i: cl.distance_m(lines[cyc_list[i]][0], start_near))
    else:
        k = max(range(n), key=lambda i: cost[cyc_list[i - 1]][cyc_list[i]])
    return cyc_list[k:] + cyc_list[:k]


def apply_scorecard(course: cl.Course, card: dict, notes: BuildNotes) -> None:
    """Pars, handicaps, and tee yardages from a scorecard, by hole number (list index 0 is hole 1)."""
    par = card.get("par")
    hcp = card.get("handicap")
    tees: Dict[str, List[int]] = card.get("tees") or {}
    lengths = {len(v) for v in [par, hcp, *tees.values()] if v}
    if len(lengths) > 1:
        raise SystemExit(f"{course.name}: scorecard lists have different lengths: {sorted(lengths)}")
    if hcp and len(set(hcp)) != len(hcp):
        raise SystemExit(f"{course.name}: scorecard handicaps repeat a number")
    count = lengths.pop() if lengths else 0
    for i in range(count):
        n = i + 1
        h = course.holes.get(n)
        if h is None:
            notes.warnings.append(f"The scorecard has hole {n} but the map does not.")
            continue
        if par:
            if h.par and h.par != par[i]:
                notes.warnings.append(f"Hole {n}: OpenStreetMap says par {h.par}, the scorecard says {par[i]}; using the scorecard.")
            h.par = par[i]
        if hcp:
            h.handicap = hcp[i]
        if tees:
            h.yards = {name: int(yds[i]) for name, yds in tees.items()}
    course.tees = list(tees)
    course.scorecard = card.get("source")


def collect(elements: Sequence[dict], course_el: dict, boundary: Optional[List[cl.LonLat]], exclude: set, notes: BuildNotes):
    """Sort the elements inside the course into hole lines, greens, tees, pins, and drawn features."""

    def in_course(geom: dict) -> bool:
        return boundary is None or cl.point_ring_m(anchor(geom), boundary) <= COURSE_MARGIN_M

    numbered: List[Tuple[int, str, dict, List[cl.LonLat]]] = []
    unnumbered: List[Tuple[str, List[cl.LonLat]]] = []
    greens, tees, pins, drawn = [], [], [], []
    seen = set()
    for el in elements:
        key = ref_of(el)
        if key in seen or el is course_el:
            continue
        seen.add(key)
        etags = el.get("tags") or {}
        kind = kind_of(etags)
        if kind in (None, "course"):
            continue
        if key in exclude:
            notes.excluded += 1
            continue
        geom = element_geometry(el)
        if geom is None:
            continue
        if not in_course(geom):
            notes.skipped_outside += 1
            continue
        if kind == "hole":
            if geom["type"] != "LineString":
                notes.warnings.append(f"{key}: golf=hole should be a line from tee to green; skipped.")
                continue
            line = [tuple(p) for p in geom["coordinates"]]
            n = int_tag(etags, "ref")
            if n is None:
                unnumbered.append((key, line))
            else:
                numbered.append((n, key, etags, line))
        elif kind == "green":
            if geom["type"] not in ("Polygon", "MultiPolygon"):
                notes.warnings.append(f"{key}: green is not an area; skipped.")
                continue
            greens.append((el, geom))
        elif kind == "tee":
            tees.append((el, geom))
        elif kind == "pin":
            pins.append((el, geom))
        elif kind in DRAWN_KINDS:
            if kind != "cartpath" and geom["type"] not in ("Polygon", "MultiPolygon"):
                continue
            drawn.append(cl.Feature(kind, geom, key))
    return numbered, unnumbered, greens, tees, pins, drawn


def link_pins(holes: Dict[int, cl.Hole], pins: Sequence[Tuple[dict, dict]]) -> None:
    """Pins are shown on the map only. Center yardage stays the middle of the green."""
    for el, geom in pins:
        p = anchor(geom)
        n = int_tag(el.get("tags") or {}, "ref")
        if n is None:
            n = next((hn for hn, h in holes.items() if h.green and cl.contains(h.green, p)), None)
        if n is not None and n in holes:
            holes[n].fixed["pin"] = p


def build_short_course(spec: dict, parent: cl.Course, unnumbered, greens, tees, notes: BuildNotes):
    """A second course made of the parent's unnumbered holes. Returns (course, notes, used green refs, used tee refs)."""
    snotes = BuildNotes()
    numbering: Dict[str, int] = spec.get("numbering") or {}
    keys = [k for k, _ in unnumbered]
    if numbering and set(numbering) >= set(keys):
        order = sorted(range(len(keys)), key=lambda i: numbering[keys[i]])
        numbers = [numbering[keys[i]] for i in order]
    else:
        ref_tees = [parent.holes[n].line[0] for n in (1, 10) if n in parent.holes and parent.holes[n].line]
        start = (sum(p[0] for p in ref_tees) / len(ref_tees), sum(p[1] for p in ref_tees) / len(ref_tees)) if ref_tees else None
        order = infer_order([line for _, line in unnumbered], start)
        numbers = list(range(1, len(order) + 1))
        snotes.numbering_inferred = True
    short = cl.Course(name=spec.get("name") or f"{parent.name} short course", osm=parent.osm, built=parent.built,
                      expected_holes=len(unnumbered))
    for i, n in zip(order, numbers):
        key, line = unnumbered[i]
        short.holes[n] = cl.Hole(n, line=line, osm={"hole": key})
    green_rest = link_greens(short.holes, greens)
    tee_rest = link_tees(short.holes, tees, use_ref=False)
    used_greens = {ref_of(el) for el, _ in greens} - {ref_of(el) for el, _ in green_rest}
    used_tees = {ref_of(el) for el, _ in tees} - {ref_of(el) for el, _ in tee_rest}
    pts = [p for h in short.holes.values() for p in (h.line or []) + (h.green or []) + [q for t in h.tees for q in t]]
    short.boundary = cl.convex_hull(pts, margin_m=25)
    short.features = [f for f in parent.features if f.kind not in ("green", "tee") and cl.point_ring_m(anchor(f.geometry), short.boundary) == 0]
    if spec.get("scorecard"):
        apply_scorecard(short, spec["scorecard"], snotes)
    if snotes.numbering_inferred:
        snotes.warnings.append("Hole numbers were inferred from the routing. Confirm them, then record them under numbering in the overrides file.")
    return short, snotes, used_greens, used_tees


def build_course(elements: Sequence[dict], course_ref: Optional[str] = None, overrides: Optional[dict] = None) -> Tuple[cl.Course, BuildNotes]:
    """Build the course. Overrides (see docs/course_format.md) can add a scorecard, drop features, and
    turn unnumbered holes into a second course, returned in notes.extra_courses."""
    overrides = overrides or {}
    notes = BuildNotes()
    course_el = find_course_element(elements, course_ref)
    tags = course_el.get("tags") or {}
    boundary = outer_ring(element_geometry(course_el))
    course = cl.Course(
        name=overrides.get("name") or tags.get("name", "Unnamed course"),
        boundary=boundary,
        expected_holes=overrides.get("holes") or int_tag(tags, "holes"),
        osm=ref_of(course_el),
        built=dt.date.today().isoformat(),
    )
    if boundary is None:
        notes.warnings.append("The course boundary is not mapped as an area, so nothing is filtered by it.")

    numbered, unnumbered, greens, tees, pins, drawn = collect(elements, course_el, boundary, set(overrides.get("exclude") or []), notes)
    course.features = drawn
    for n, key, etags, line in numbered:
        if n in course.holes and course.holes[n].line:
            notes.warnings.append(f"Hole {n} has more than one line of play; kept the longer one.")
            if cl.polyline_length_m(line) <= cl.polyline_length_m(course.holes[n].line):
                continue
        h = course.holes.setdefault(n, cl.Hole(n))
        h.line = line
        h.par = int_tag(etags, "par") or h.par
        h.handicap = int_tag(etags, "handicap") or h.handicap
        h.osm["hole"] = key

    green_rest = link_greens(course.holes, greens)
    tee_rest = link_tees(course.holes, tees)
    link_pins(course.holes, pins)
    if overrides.get("scorecard"):
        apply_scorecard(course, overrides["scorecard"], notes)

    used_greens: set = set()
    used_tees: set = set()
    if unnumbered and overrides.get("short_course"):
        short, snotes, used_greens, used_tees = build_short_course(overrides["short_course"], course, unnumbered, green_rest, tee_rest, notes)
        notes.extra_courses.append((short, snotes))
    else:
        for key, _ in unnumbered:
            notes.warnings.append(f"{key}: hole line has no ref (hole number); skipped.")

    # Greens and tees with no hole of their own stay on the map as drawn shapes.
    for el, geom in green_rest:
        course.features.append(cl.Feature("green", {"type": "Polygon", "coordinates": [[list(p) for p in outer_ring(geom)]]}, ref_of(el)))
        if ref_of(el) not in used_greens:
            notes.unlinked_greens.append(ref_of(el))
    for el, geom in tee_rest:
        course.features.append(cl.Feature("tee", geom, ref_of(el)))
        if ref_of(el) not in used_tees:
            notes.unlinked_tees += 1
    return course, notes


# Report ----------------------------------------------------------------------------


def expected_count(course: cl.Course) -> int:
    if course.expected_holes:
        return course.expected_holes
    top = max(course.holes, default=0)
    return 9 if top <= 9 else 18 if top <= 18 else 27 if top <= 27 else top


def hole_checks(h: cl.Hole) -> Tuple[Optional[float], Optional[float], List[str]]:
    """(length yd, green depth yd, notes) for one hole."""
    notes = []
    length = None
    depth = None
    line = h.play_line()
    if h.line:
        length = cl.yards(cl.polyline_length_m(h.line))
    elif line:
        length = cl.yards(cl.polyline_length_m(line))
    if h.green and line:
        y = cl.green_yardage(line[0], h.green)
        if y.front is not None and y.back is not None:
            depth = y.back - y.front
            if not 8 <= depth <= 60:
                notes.append(f"green depth {depth:.0f} yd looks wrong")
        area = cl.area_m2(h.green)
        if area < 100:
            notes.append(f"green only {area:.0f} m², maybe not the real outline")
    if length is not None and h.par:
        ok = {3: (60, 270), 4: (230, 510), 5: (420, 700)}.get(h.par)
        if ok and not ok[0] <= length <= ok[1]:
            notes.append(f"{length:.0f} yd is unusual for a par {h.par}")
    return length, depth, notes


def coverage_report(course: cl.Course, notes: Optional[BuildNotes] = None) -> Tuple[List[str], bool]:
    """(Markdown lines, every expected hole has a green and a number)."""
    expected = expected_count(course)
    numbers = sorted(set(range(1, expected + 1)) | set(course.holes))
    lines = [f"## {course.name}", ""]
    if course.osm:
        lines.append(f"OpenStreetMap: https://www.openstreetmap.org/{course.osm}")
    center = course.boundary and cl.centroid(course.boundary)
    if not center:
        pts = [h.green_center() for h in course.holes.values() if h.green_center()]
        center = pts[0] if pts else None
    if center:
        lines.append(f"Edit: https://www.openstreetmap.org/edit?editor=id#map=17/{center[1]:.5f}/{center[0]:.5f}")
    lines.append("")
    rows = []
    ready = 0
    card_tee = course.tees[0] if course.tees else None  # the first tee listed, normally the longest
    for n in numbers:
        h = course.holes.get(n)
        if h is None:
            rows.append([str(n), "MISSING", "", "", "", "", "", "", "no line of play and no numbered green"])
            continue
        length, depth, hnotes = hole_checks(h)
        status = "ok" if h.complete else "NO GREEN"
        if h.complete:
            ready += 1
        if not h.line:
            hnotes.insert(0, "no line of play")
        if not h.tees:
            hnotes.append("no tee")
        rows.append(
            [
                str(n),
                status,
                str(h.par or ""),
                "yes" if h.line else "",
                "yes" if h.green else "",
                str(len(h.tees) or ""),
                "" if length is None else f"{length:.0f}",
                str(h.yards.get(card_tee, "")) if card_tee else "",
                ("" if depth is None else f"depth {depth:.0f} yd") + ("; " if depth is not None and hnotes else "") + "; ".join(hnotes),
            ]
        )
    card_head = f"Card yd ({card_tee})" if card_tee else "Card yd"
    lines.append(f"| Hole | Status | Par | Line | Green | Tees | Length yd | {card_head} | Notes |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    lines.append("")
    kinds = Counter(f.kind for f in course.features)
    drawn = ", ".join(f"{kinds[k]} {k}" for k in DRAWN_KINDS if kinds.get(k)) or "none"
    if kinds.get("green"):
        drawn += f", {kinds['green']} other greens (practice or unnumbered)"
    lines.append(f"Ready for yardage: {ready} of {expected} holes. Also mapped: {drawn}.")
    if course.scorecard:
        lines.append(f"Scorecard: {course.scorecard}. Tees: {', '.join(course.tees) or 'none'}.")
    if notes:
        if notes.excluded:
            lines.append(f"Left out {notes.excluded} features listed under exclude in the overrides file.")
        if notes.unlinked_greens:
            lines.append(f"Greens not linked to a hole: {len(notes.unlinked_greens)} ({', '.join(notes.unlinked_greens[:6])}). "
                         "Add ref=<hole number> to them, or draw the hole's line of play.")
        if notes.unlinked_tees:
            lines.append(f"Tees not linked to a hole: {notes.unlinked_tees}.")
        if notes.skipped_outside:
            lines.append(f"Ignored {notes.skipped_outside} golf features outside this course's boundary.")
        for w in notes.warnings:
            lines.append(f"Note: {w}")
    lines.append("")
    return lines, all(n in course.holes and course.holes[n].complete for n in range(1, expected + 1))


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "course"


# Commands --------------------------------------------------------------------------


def cmd_list(args) -> int:
    data = overpass(query_list(args.region, args.name), args.overpass_url)
    rows = []
    for e in data.get("elements", []):
        tags = e.get("tags") or {}
        c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
        rows.append((tags.get("name", "(no name)"), ref_of(e), tags.get("holes", ""), c.get("lat"), c.get("lon")))
    if not rows:
        print("No golf courses found.")
        return 1
    for name, ref, holes, lat, lon in sorted(rows):
        where = f"{lat:.4f},{lon:.4f}" if lat is not None else ""
        print(f"{ref:<22} {name:<45} holes={holes or '?':<3} {where}")
    return 0


def fetch_elements(args) -> Tuple[List[dict], str]:
    if args.osm_json:
        data = json.loads(Path(args.osm_json).read_text(encoding="utf-8"))
        return data.get("elements", []), args.osm_id or data.get("cartdash_course")
    if args.osm_id:
        course_ref = args.osm_id
    else:
        found = overpass(query_list(args.region, args.name), args.overpass_url).get("elements", [])
        if not found:
            raise SystemExit(f"No golf course named like {args.name!r}. Try: course_from_osm.py list --region {args.region or 'US-WY'}")
        if len(found) > 1:
            print("More than one course matches. Pick one with --osm-id:", file=sys.stderr)
            for e in found:
                print(f"  {ref_of(e):<22} {(e.get('tags') or {}).get('name', '?')}", file=sys.stderr)
            raise SystemExit(2)
        course_ref = ref_of(found[0])
    osm_type, osm_id = parse_ref(course_ref)
    course_els = overpass(query_course(osm_type, osm_id), args.overpass_url).get("elements", [])
    if not course_els:
        raise SystemExit(f"{course_ref} not found on OpenStreetMap")
    geom = element_geometry(course_els[0])
    if geom and geom["type"] != "Point":
        ring = outer_ring(geom) or [tuple(p) for p in geom.get("coordinates", [])]
    else:
        lon, lat = geom["coordinates"] if geom else (course_els[0]["lon"], course_els[0]["lat"])
        ring = [(lon - 0.015, lat - 0.011), (lon + 0.015, lat + 0.011)]  # about 1.2 km each way
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    pad = 0.001  # about 100 m
    bbox = (min(lats) - pad, min(lons) - pad, max(lats) + pad, max(lons) + pad)
    time.sleep(1)  # be gentle with the shared Overpass server
    feats = overpass(query_features(bbox), args.overpass_url).get("elements", [])
    return course_els + feats, course_ref


def overrides_path(out_dir: Path, name: str) -> Path:
    return out_dir / f"{slug(name)}.overrides.json"


def load_overrides(path: Optional[Path]) -> dict:
    """Scorecard, exclusions, and short course settings for a course. Missing file means none."""
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"{path}: not valid JSON ({exc})")


def cmd_build(args) -> int:
    if not (args.osm_json or args.osm_id or args.name):
        raise SystemExit("Give --name, --osm-id, or --osm-json")
    elements, course_ref = fetch_elements(args)
    if args.save_osm:
        Path(args.save_osm).write_text(json.dumps({"cartdash_course": course_ref, "elements": elements}) + "\n", encoding="utf-8")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    osm_name = (find_course_element(elements, course_ref).get("tags") or {}).get("name", "Unnamed course")
    opath = Path(args.overrides) if args.overrides else overrides_path(out_dir, osm_name)
    overrides = load_overrides(opath)
    if overrides:
        print(f"Using {opath}")
    course, notes = build_course(elements, course_ref, overrides)
    all_ready = True
    for c, n in [(course, notes)] + notes.extra_courses:
        path = out_dir / f"{slug(c.name)}.geojson"
        cl.write_course(c, path)
        lines, ready = coverage_report(c, n)
        all_ready = all_ready and ready
        print("\n".join(lines))
        print(f"Wrote {path}")
        print()
    return 0 if all_ready else 3


def cmd_report(args) -> int:
    course = cl.load_course(Path(args.file))
    lines, ready = coverage_report(course)
    print("\n".join(lines))
    return 0 if ready else 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--overpass-url", default=OVERPASS_URL)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("list", help="golf courses in a region")
    s.add_argument("--region", default="US-WY", help="ISO 3166-2 code (default US-WY), or '' for worldwide")
    s.add_argument("--name", help="only names matching this (case insensitive)")

    s = sub.add_parser("build", help="build a course file and report coverage")
    s.add_argument("--name", help="course name, or part of it")
    s.add_argument("--region", default="US-WY", help="ISO 3166-2 code used with --name (default US-WY)")
    s.add_argument("--osm-id", help="pick the course directly, like way/123 or relation/456")
    s.add_argument("--osm-json", help="build from a saved download instead of the network")
    s.add_argument("--save-osm", help="also save the raw download here, for rebuilding offline")
    s.add_argument("--overrides", help="overrides file (default <out>/<course name>.overrides.json if it exists)")
    s.add_argument("--out", default=str(DEFAULT_OUT), help=f"output folder (default {DEFAULT_OUT})")

    s = sub.add_parser("report", help="coverage report for an existing course file")
    s.add_argument("file")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "region", None) == "":
        args.region = None
    return {"list": cmd_list, "build": cmd_build, "report": cmd_report}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
