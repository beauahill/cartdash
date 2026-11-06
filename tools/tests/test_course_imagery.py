import io
import json
import urllib.parse

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

import course_imagery as ci  # noqa: E402
import courselib as cl  # noqa: E402

ORIGIN = (-105.50, 44.30)
F = cl.LocalFrame(ORIGIN)


def ll(x, y):
    return F.lonlat(x, y)


def square_course(tmp_path, size_m=1500.0):
    c = cl.Course("Square Links")
    c.boundary = [ll(0, 0), ll(size_m, 0), ll(size_m, size_m), ll(0, size_m), ll(0, 0)]
    c.holes[1] = cl.Hole(1, line=[ll(100, 100), ll(100, 400)], green=[ll(90, 400), ll(110, 400), ll(110, 420), ll(90, 420), ll(90, 400)])
    path = tmp_path / "square-links.geojson"
    cl.write_course(c, path)
    return path


class FakeService:
    """Behaves like the ArcGIS exportImage endpoint, including its habit of growing the
    asked area until pixels are square in degrees. Renders white dots at known places."""

    def __init__(self, dots=(), blank=False, broken=False):
        self.dots = list(dots)  # (lon, lat)
        self.blank = blank
        self.broken = broken
        self.json_calls = []
        self.images = {}

    def __call__(self, url, params):
        if url.startswith("fake://"):
            return self.images[url]
        self.json_calls.append(params)
        if self.broken:
            return b'{"error":{"code":500,"message":"Error exporting image"}}'
        w, h = (int(v) for v in params["size"].split(","))
        west, south, east, north = (float(v) for v in params["bbox"].split(","))
        px = max((east - west) / w, (north - south) / h)  # square degree pixels, like the real service
        cx, cy = (west + east) / 2, (south + north) / 2
        ext = {"xmin": cx - px * w / 2, "xmax": cx + px * w / 2, "ymin": cy - px * h / 2, "ymax": cy + px * h / 2}
        img = Image.new("RGB", (w, h), (120, 120, 120) if self.blank else (30, 80, 30))
        d = ImageDraw.Draw(img)
        if not self.blank:
            d.point((0, 0), fill=(200, 200, 200))
        for lon, lat in self.dots:
            x = (lon - ext["xmin"]) / px
            y = (ext["ymax"] - lat) / px
            d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        href = f"fake://image/{len(self.json_calls)}"
        self.images[href] = buf.getvalue()
        return json.dumps({"href": href, "width": w, "height": h, "extent": ext}).encode()


def white_centroid(img, box):
    xs = ys = n = 0
    x0, y0, x1, y1 = box
    for y in range(max(0, y0), min(img.height, y1)):
        for x in range(max(0, x0), min(img.width, x1)):
            if sum(img.getpixel((x, y))) > 600:
                xs += x
                ys += y
                n += 1
    return (xs / n, ys / n) if n else None


def test_grid_is_pixel_aligned_and_tiles_exactly():
    g = ci.make_grid([ll(0, 0), ll(1500, 1200)], mpp=0.5, margin_m=40)
    assert g.width == pytest.approx((1500 + 80) / 0.5, abs=2)
    assert g.height == pytest.approx((1200 + 80) / 0.5, abs=2)
    chunks = g.chunks(1000)
    assert sum(w * h for _, _, w, h, _ in chunks) == g.width * g.height
    by_pos = {(c, r): bbox for c, r, _, _, bbox in chunks}
    for (c, r), (west, south, east, north) in by_pos.items():
        if (c + 1000, r) in by_pos:
            assert by_pos[(c + 1000, r)][0] == pytest.approx(east, abs=1e-12)
        if (c, r + 1000) in by_pos:
            assert by_pos[(c, r + 1000)][3] == pytest.approx(south, abs=1e-12)


def test_requests_use_square_degree_pixels_under_the_limit():
    g = ci.make_grid([ll(0, 0), ll(1500, 1500)], mpp=0.5, margin_m=0)
    rw, rh = ci.request_size(g, 2000, 2000)
    assert rh == 2000 and rw > 2000 and rw <= ci.MAX_REQUEST_PX
    assert (g.dlon * 2000) / rw == pytest.approx(g.dlat, rel=1e-3)


@pytest.mark.parametrize("size_m", [700.0, 1500.0])
def test_photo_lines_up_with_the_ground(tmp_path, size_m):
    """Dots placed at known spots, including near chunk edges, land on the right pixels."""
    path = square_course(tmp_path, size_m)
    spots = [ll(50, 50), ll(size_m - 60, size_m - 60), ll(size_m / 2, size_m - 30), ll(30, size_m / 2), ll(size_m * 0.7, 40)]
    fake = FakeService(dots=spots)
    meta = ci.build(path, mpp=0.5, margin_m=40, fetch=fake, pause_s=0, log=lambda s: None)
    img = Image.open(ci.photo_paths(path)[0]).convert("RGB")
    west, south, east, north = meta["bounds"]
    for lon, lat in spots:
        ex = (lon - west) / (east - west) * meta["width"]
        ey = (north - lat) / (north - south) * meta["height"]
        got = white_centroid(img, (int(ex) - 40, int(ey) - 40, int(ex) + 40, int(ey) + 40))
        assert got is not None, (lon, lat)
        assert got[0] == pytest.approx(ex, abs=2) and got[1] == pytest.approx(ey, abs=2), (lon, lat)


def test_build_writes_photo_and_bounds(tmp_path):
    path = square_course(tmp_path)
    fake = FakeService()
    meta = ci.build(path, mpp=1.0, margin_m=40, fetch=fake, pause_s=0, log=lambda s: None)
    jpg, meta_path = ci.photo_paths(path)
    assert jpg.name == "square-links.photo.jpg" and meta_path.name == "square-links.photo.json"
    assert Image.open(jpg).size == (meta["width"], meta["height"])
    assert json.loads(meta_path.read_text()) == meta
    west, south, east, north = meta["bounds"]
    assert cl.distance_m((west, south), (east, south)) == pytest.approx(1580, abs=3)
    assert cl.distance_m((west, south), (west, north)) == pytest.approx(1580, abs=3)
    assert len(fake.json_calls) == 1
    p = fake.json_calls[0]
    assert p["bboxSR"] == "4326" and p["imageSR"] == "4326" and p["f"] == "json"
    assert meta["crs"] == "EPSG:4326" and "public domain" in meta["attribution"]


def test_big_courses_are_split(tmp_path):
    path = square_course(tmp_path, size_m=1500)
    fake = FakeService()
    meta = ci.build(path, mpp=0.5, margin_m=40, fetch=fake, pause_s=0, log=lambda s: None)
    assert meta["width"] > ci.CHUNK_PX and len(fake.json_calls) == 4


def test_blank_chunks_are_reported(tmp_path):
    path = square_course(tmp_path, size_m=500)
    said = []
    ci.build(path, mpp=1.0, margin_m=0, fetch=FakeService(blank=True), pause_s=0, log=said.append)
    assert any("blank" in s for s in said)


def test_service_errors_stop_with_the_message(tmp_path):
    path = square_course(tmp_path, size_m=500)
    with pytest.raises(SystemExit) as exc:
        ci.build(path, mpp=1.0, margin_m=0, fetch=FakeService(broken=True), pause_s=0, log=lambda s: None)
    assert "Error exporting image" in str(exc.value)


def test_export_params_round_trip():
    q = urllib.parse.parse_qs(urllib.parse.urlencode(ci.export_params((-105.6, 44.2, -105.5, 44.3), 2000, 1500)))
    assert q["size"] == ["2000,1500"] and q["f"] == ["json"]
    assert [float(v) for v in q["bbox"][0].split(",")] == [-105.6, 44.2, -105.5, 44.3]
