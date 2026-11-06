import json

import pytest

pytest.importorskip("matplotlib")
Image = pytest.importorskip("PIL.Image")

import course_from_osm as osm  # noqa: E402
import course_preview as cp  # noqa: E402
import courselib as cl  # noqa: E402
from test_course import synthetic_download  # noqa: E402


@pytest.fixture
def course_file(tmp_path):
    course, _ = osm.build_course(synthetic_download())
    path = tmp_path / "test-links.geojson"
    cl.write_course(course, path)
    return path


def test_drawn_previews(course_file, tmp_path):
    out = tmp_path / "preview"
    assert cp.main([str(course_file), "--out", str(out)]) == 0
    names = sorted(p.name for p in out.iterdir())
    # Hole 2 has no tee or line of play to point the view along, and hole 3 has no green, so only hole 1 is drawn.
    assert names == ["hole-01.png", "overview.png"]
    assert Image.open(out / "hole-01.png").size[1] > Image.open(out / "hole-01.png").size[0]  # portrait, tee at the bottom


def test_photo_previews(course_file, tmp_path):
    course = cl.load_course(course_file)
    lons = [p[0] for p in course.boundary]
    lats = [p[1] for p in course.boundary]
    Image.new("RGB", (400, 500), (60, 110, 50)).save(tmp_path / "test-links.photo.jpg")
    meta = {"image": "test-links.photo.jpg", "bounds": [min(lons), min(lats), max(lons), max(lats)],
            "width": 400, "height": 500, "attribution": "test imagery"}
    (tmp_path / "test-links.photo.json").write_text(json.dumps(meta))
    out = tmp_path / "preview"
    assert cp.main([str(course_file), "--photo", "--hole", "1", "--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["photo-hole-01.png", "photo-overview.png"]


def test_photo_mode_without_a_photo_explains(course_file, tmp_path):
    with pytest.raises(SystemExit) as exc:
        cp.main([str(course_file), "--photo", "--out", str(tmp_path / "p")])
    assert "course_imagery.py" in str(exc.value)
