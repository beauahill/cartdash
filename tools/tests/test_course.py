import json
import math

import pytest

import course_from_osm as osm
import courselib as cl

ORIGIN = (-105.50, 44.30)
F = cl.LocalFrame(ORIGIN)


def ll(x, y):
    """Local meters east and north of ORIGIN to (lon, lat)."""
    return F.lonlat(x, y)


def circle(cx, cy, r, n=64):
    pts = [ll(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return pts + [pts[0]]


def ellipse(cx, cy, rx, ry, n=64):
    pts = [ll(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return pts + [pts[0]]


def rect(x0, y0, x1, y1):
    pts = [ll(x0, y0), ll(x1, y0), ll(x1, y1), ll(x0, y1)]
    return pts + [pts[0]]


def yd(m):
    return m * cl.YARDS_PER_METER


# Geometry and yardage ------------------------------------------------------------


def test_distance_and_frame():
    a, b = (-105.5, 44.0), (-105.5, 45.0)
    assert cl.distance_m(a, b) == pytest.approx(111195, rel=1e-3)
    x, y = F.xy(ll(120.0, -80.0))
    assert (x, y) == (pytest.approx(120.0), pytest.approx(-80.0))
    assert cl.distance_m(ORIGIN, ll(300, 400)) == pytest.approx(500, rel=1e-3)


def test_centroid_area_contains():
    sq = rect(0, 0, 20, 10)
    c = F.xy(cl.centroid(sq))
    assert c == (pytest.approx(10, abs=0.01), pytest.approx(5, abs=0.01))
    assert cl.area_m2(sq) == pytest.approx(200, rel=1e-3)
    assert cl.contains(sq, ll(5, 5)) and not cl.contains(sq, ll(25, 5))
    assert cl.point_ring_m(ll(25, 5), sq) == pytest.approx(5, abs=0.01)
    assert cl.point_ring_m(ll(5, 5), sq) == 0


def test_front_center_back_straight_on():
    green = circle(0, 150, 15)
    y = cl.green_yardage(ORIGIN, green)
    assert y.center == pytest.approx(yd(150), abs=0.3)
    assert y.front == pytest.approx(yd(135), abs=0.3)
    assert y.back == pytest.approx(yd(165), abs=0.3)


def test_front_and_back_follow_the_angle_of_approach():
    green = ellipse(0, 0, 10, 20)  # 40 m deep north to south, 20 m wide east to west
    from_south = cl.green_yardage(ll(0, -150), green)
    from_east = cl.green_yardage(ll(150, 0), green)
    assert from_south.back - from_south.front == pytest.approx(yd(40), abs=0.3)
    assert from_east.back - from_east.front == pytest.approx(yd(20), abs=0.3)
    assert from_south.center == pytest.approx(from_east.center, abs=0.01)


def test_on_the_green_has_no_front():
    y = cl.green_yardage(ll(0, -5), circle(0, 0, 15))
    assert y.front is None
    assert y.center == pytest.approx(yd(5), abs=0.1)
    assert y.back == pytest.approx(yd(20), abs=0.2)


def test_fixed_points_win():
    green = circle(0, 150, 15)
    fixed = {"center": ll(0, 152), "front": ll(0, 140)}
    y = cl.green_yardage(ORIGIN, green, fixed)
    assert y.center == pytest.approx(yd(152), abs=0.2)
    assert y.front == pytest.approx(yd(140), abs=0.2)
    assert y.back == pytest.approx(yd(165), abs=0.3)  # computed along the line through the fixed center


def test_nearest_hole():
    course = cl.Course("t")
    course.holes[1] = cl.Hole(1, line=[ll(0, 0), ll(0, 300)], green=circle(0, 310, 12))
    course.holes[2] = cl.Hole(2, line=[ll(80, 300), ll(80, 0)], green=circle(80, -10, 12))
    assert cl.nearest_hole(ll(10, 150), course) == 1
    assert cl.nearest_hole(ll(70, 150), course) == 2


# Synthetic OpenStreetMap download --------------------------------------------------

_ids = iter(range(1000, 100000))


def way(pts, **tags):
    return {"type": "way", "id": next(_ids), "geometry": [{"lat": p[1], "lon": p[0]} for p in pts], "tags": tags}


def node(p, **tags):
    return {"type": "node", "id": next(_ids), "lat": p[1], "lon": p[0], "tags": tags}


def relation(outer_segments, **tags):
    members = [
        {"type": "way", "ref": next(_ids), "role": "outer", "geometry": [{"lat": p[1], "lon": p[0]} for p in seg]}
        for seg in outer_segments
    ]
    return {"type": "relation", "id": next(_ids), "members": members, "tags": tags}


def synthetic_download():
    """A 9 hole course with known gaps:
    hole 1: line, par 4, green found at the line's end, tee near the start
    hole 2: no line, green tagged ref=2
    hole 3: line, par 3, but no green anywhere near its end
    holes 4 to 9: not mapped
    plus one green with no hole, a fairway, a bunker, a pond as a two piece
    multipolygon, and a bunker on the course next door.
    """
    els = [
        way(rect(-100, -100, 400, 600), leisure="golf_course", name="Test Links", holes="9"),
        way([ll(0, 0), ll(10, 200), ll(0, 350)], golf="hole", ref="1", par="4", handicap="5"),
        way(circle(0, 362, 14), golf="green"),
        way(rect(-6, -6, 6, 6), golf="tee", **{"tee": "blue"}),
        node(ll(3, 60), golf="tee"),
        way(circle(200, 300, 12), golf="green", ref="2"),
        way([ll(300, 0), ll(300, 160)], golf="hole", ref="3", par="3"),
        way(circle(150, 500, 10), golf="green"),
        way(rect(-20, 100, 25, 320), golf="fairway"),
        way(circle(20, 340, 5), golf="bunker"),
        relation([[ll(250, 400), ll(290, 400), ll(290, 440)], [ll(290, 440), ll(250, 440), ll(250, 400)]], natural="water", type="multipolygon"),
        way(circle(2000, 2000, 6), golf="bunker"),
        node(ll(0, 362), golf="pin"),
    ]
    return els


def test_assemble_rings_joins_segments():
    a, b, c, d = (0, 0), (1, 0), (1, 1), (0, 1)
    rings = osm.assemble_rings([[a, b, c], [a, d, c]])  # second piece runs the other way
    assert len(rings) == 1 and rings[0][0] == rings[0][-1] and len(rings[0]) == 5
    assert osm.assemble_rings([[a, b, c]]) == []  # never closes


def test_build_course_links_and_gaps():
    course, notes = osm.build_course(synthetic_download())
    assert course.name == "Test Links" and course.expected_holes == 9
    assert sorted(course.holes) == [1, 2, 3]
    h1 = course.holes[1]
    assert h1.par == 4 and h1.handicap == 5 and h1.green is not None
    assert len(h1.tees) == 2  # the box at the start and the forward tee node
    assert "pin" in h1.fixed
    assert course.holes[2].green is not None and course.holes[2].line is None
    assert course.holes[3].green is None
    assert len(notes.unlinked_greens) == 1
    kinds = sorted(f.kind for f in course.features)
    assert kinds == ["bunker", "fairway", "water"]  # the next door bunker is dropped
    assert notes.skipped_outside == 1
    water = next(f for f in course.features if f.kind == "water")
    assert water.geometry["type"] == "Polygon"


def test_coverage_report():
    course, notes = osm.build_course(synthetic_download())
    lines, ready = osm.coverage_report(course, notes)
    text = "\n".join(lines)
    assert not ready
    assert "Ready for yardage: 2 of 9 holes" in text
    assert "| 3 | NO GREEN | 3 |" in text
    assert "| 9 |" in text and "MISSING" in text
    assert "openstreetmap.org/edit?editor=id#map=17/" in text
    assert "Greens not linked to a hole: 1" in text
    h1 = next(line for line in lines if line.startswith("| 1 |"))
    length = cl.yards(cl.polyline_length_m(course.holes[1].line))
    assert f"| {length:.0f} |" in h1 and "depth 31 yd" in h1


def test_course_file_round_trip(tmp_path):
    course, _ = osm.build_course(synthetic_download())
    path = tmp_path / "c.geojson"
    cl.write_course(course, path)
    data = json.loads(path.read_text())
    assert data["type"] == "FeatureCollection"
    head = data["features"][0]["properties"]
    assert head["kind"] == "course" and head["format"] == 1 and "OpenStreetMap" in head["attribution"]
    back = cl.load_course(path)
    assert sorted(back.holes) == [1, 2, 3]
    assert back.holes[1].par == 4 and len(back.holes[1].tees) == 2
    assert back.holes[1].line == course.holes[1].line
    a = cl.green_yardage(ORIGIN, course.holes[1].green)
    b = cl.green_yardage(ORIGIN, back.holes[1].green)
    assert (a.front, a.center, a.back) == pytest.approx((b.front, b.center, b.back))
    assert sorted(f.kind for f in back.features) == ["bunker", "fairway", "water"]


def test_build_command_offline(tmp_path, capsys):
    saved = tmp_path / "osm.json"
    saved.write_text(json.dumps({"elements": synthetic_download()}))
    rc = osm.main(["build", "--osm-json", str(saved), "--out", str(tmp_path / "courses")])
    assert rc == 3  # written, but not every hole is ready
    out = capsys.readouterr().out
    assert "## Test Links" in out
    path = tmp_path / "courses" / "test-links.geojson"
    assert path.exists()
    assert osm.main(["report", str(path)]) == 3


def test_queries():
    q = osm.query_list("US-WY", 'Bell "Nob"')
    assert 'area["ISO3166-2"="US-WY"]' in q and 'nwr["leisure"="golf_course"]["name"~"Bell \\"Nob\\"",i](area.r)' in q
    assert "out tags center;" in q
    assert osm.query_course("way", 42).strip().endswith("way(42);\nout geom;")
    fq = osm.query_features((44.0, -105.6, 44.1, -105.5))
    assert 'nwr["golf"](44.000000,-105.600000,44.100000,-105.500000)' in fq
    assert osm.parse_ref("relation/123") == ("relation", 123)
    with pytest.raises(SystemExit):
        osm.parse_ref("123")
    assert osm.slug("Bell Nob Golf Course") == "bell-nob-golf-course"
    assert osm._regex_escape("St. Mary's (East)") == "St\\. Mary's \\(East\\)"
