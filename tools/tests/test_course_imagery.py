import io
import json
import urllib.parse

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

import course_imagery as ci  # noqa: E402
import courselib as cl  # noqa: E402

ORIGIN = (-105.50, 44.30)
F = cl.LocalFrame(ORIGIN)


def ll(x, y):
    return F.lonlat(x, y)


def square_course(tmp_path, size_m=1500.0):
    c = cl.Course("Square Links")
    pts = [ll(0, 0), ll(size_m, 0), ll(size_m, size_m), ll(0, size_m), ll(0, 0)]
    c.boundary = pts
    c.holes[1] = cl.Hole(1, line=[ll(100, 100), ll(100, 400)], green=[ll(90, 400), ll(110, 400), ll(110, 420), ll(90, 420), ll(90, 400)])
    path = tmp_path / "square-links.geojson"
    cl.write_course(c, path)
    return path


class FakeService:
    """Returns a JPEG of the requested size whose color encodes the request's west edge."""

    def __init__(self, blank=False, broken=False):
        self.calls = []
        self.blank = blank
        self.broken = broken

    def __call__(self, url, params):
        self.calls.append(params)
        if self.broken:
            return b'{"error":{"code":500,"message":"Error exporting image"}}'
        w, h = (int(v) for v in params["size"].split(","))
        color = (120, 120, 120) if self.blank else (40 + len(self.calls) * 20 % 200, 140, 60)
        img = Image.new("RGB", (w, h), color)
        if not self.blank:
            img.putpixel((0, 0), (255, 255, 255))  # some contrast so it is not seen as blank
        buf = io.BytesIO()
        img.save(buf, "JPEG")
        return buf.getvalue()


def test_grid_is_pixel_aligned_and_tiles_exactly():
    pts = [ll(0, 0), ll(1500, 1200)]
    g = ci.make_grid(pts, mpp=0.5, margin_m=40)
    assert g.width == pytest.approx((1500 + 80) / 0.5, abs=2)
    assert g.height == pytest.approx((1200 + 80) / 0.5, abs=2)
    chunks = g.chunks(1000)
    assert sum(w * h for _, _, w, h, _ in chunks) == g.width * g.height
    # Neighbouring chunks share edges exactly, so the stitched photo has no gaps or overlaps.
    by_pos = {(c, r): bbox for c, r, _, _, bbox in chunks}
    for (c, r), (west, south, east, north) in by_pos.items():
        if (c + 1000, r) in by_pos:
            assert by_pos[(c + 1000, r)][0] == pytest.approx(east, abs=1e-12)
        if (c, r + 1000) in by_pos:
            assert by_pos[(c, r + 1000)][3] == pytest.approx(south, abs=1e-12)
    assert max(w for _, _, w, _, _ in chunks) <= ci.MAX_REQUEST_PX


def test_build_writes_photo_and_bounds(tmp_path):
    path = square_course(tmp_path)
    fake = FakeService()
    meta = ci.build(path, mpp=1.0, margin_m=40, fetch=fake, pause_s=0, log=lambda s: None)
    jpg, meta_path = ci.photo_paths(path)
    assert jpg.name == "square-links.photo.jpg" and meta_path.name == "square-links.photo.json"
    img = Image.open(jpg)
    assert img.size == (meta["width"], meta["height"])
    assert json.loads(meta_path.read_text()) == meta
    west, south, east, north = meta["bounds"]
    # The bounds cover the boundary plus the margin, and the pixels are about 1 m square.
    assert cl.distance_m((west, south), (east, south)) == pytest.approx(1580, abs=3)
    assert cl.distance_m((west, south), (west, north)) == pytest.approx(1580, abs=3)
    assert len(fake.calls) == 1  # 1580 px fits in one request
    p = fake.calls[0]
    assert p["bboxSR"] == "4326" and p["imageSR"] == "4326" and p["f"] == "image"
    assert meta["crs"] == "EPSG:4326" and "public domain" in meta["attribution"]


def test_big_courses_are_split_and_stitched(tmp_path):
    path = square_course(tmp_path, size_m=1500)
    fake = FakeService()
    meta = ci.build(path, mpp=0.5, margin_m=40, fetch=fake, pause_s=0, log=lambda s: None)
    assert meta["width"] > ci.CHUNK_PX and len(fake.calls) == 4
    img = Image.open(ci.photo_paths(path)[0]).convert("RGB")
    # Each quarter came from a different request, so each has its own color.
    q = [img.getpixel((x, y)) for x, y in ((10, 10), (img.width - 10, 10), (10, img.height - 10), (img.width - 10, img.height - 10))]
    assert len({c[0] // 10 for c in q}) == 4


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
    p = ci.export_params((-105.6, 44.2, -105.5, 44.3), 2000, 1500)
    q = urllib.parse.parse_qs(urllib.parse.urlencode(p))
    assert q["size"] == ["2000,1500"] and q["format"] == ["jpg"]
    assert [float(v) for v in q["bbox"][0].split(",")] == [-105.6, 44.2, -105.5, 44.3]
