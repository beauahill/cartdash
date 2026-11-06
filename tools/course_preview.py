#!/usr/bin/env python3
"""Draw a course file as PNG images, to check course data by eye.

    overview.png      the whole course: every hole numbered, unlinked greens
                      and tees outlined in magenta and orange
    hole-NN.png       one hole the way the course screen shows it: tee at the
                      bottom, green at the top, with front, center, and back
                      yardage from a cart 150 yards out on the line of play

With --photo, the aerial photo from course_imagery.py goes underneath and the
shapes become outlines, the way the app's photo view looks (files are named
photo-overview.png and photo-hole-NN.png).

Needs matplotlib (pip install matplotlib), and Pillow for --photo.

Examples:
    python3 tools/course_preview.py courses/bell-nob-golf-course.geojson
    python3 tools/course_preview.py courses/bell-nob-golf-course.geojson --hole 7
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import courselib as cl  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

COLORS = {
    "background": "#d9e8c4",
    "rough": "#bcd69a",
    "fairway": "#7cc576",
    "range": "#a9cf8c",
    "water": "#4a90d9",
    "bunker": "#ecdcae",
    "green": "#2f9e44",
    "tee": "#58a463",
    "cartpath": "#9a9a9a",
    "line": "#ffffff",
    "text": "#111111",
}
DRAW_ORDER = ("rough", "range", "fairway", "water", "bunker")


def rings_of(geom: dict) -> List[List[cl.LonLat]]:
    """Outer rings of a Polygon or MultiPolygon (islands are skipped in a preview)."""
    if geom["type"] == "Polygon":
        return [[tuple(p) for p in geom["coordinates"][0]]]
    if geom["type"] == "MultiPolygon":
        return [[tuple(p) for p in poly[0]] for poly in geom["coordinates"]]
    return []


class Photo:
    """An aerial photo from course_imagery.py: a JPEG plus its lon/lat bounds."""

    def __init__(self, course_path: Path, max_px: int = 4000):
        from PIL import Image

        base = course_path.with_suffix("")
        meta_path = base.with_name(base.name + ".photo.json")
        if not meta_path.exists():
            raise SystemExit(f"No photo for this course. Run: python3 tools/course_imagery.py {course_path}")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        Image.MAX_IMAGE_PIXELS = None
        img = Image.open(meta_path.with_name(self.meta["image"])).convert("RGB")
        if max(img.size) > max_px:
            img.thumbnail((max_px, max_px))
        self.image = img
        self.west, self.south, self.east, self.north = self.meta["bounds"]

    def draw(self, ax, view: "View") -> None:
        """The photo is linear in lon/lat, and so is the view before rotation, so one affine transform places it."""
        import numpy as np
        from matplotlib.transforms import Affine2D

        f = view.f
        x0, y0 = f.xy((self.west, self.south))
        x1, y1 = f.xy((self.east, self.north))
        im = ax.imshow(np.asarray(self.image), extent=(x0, x1, y0, y1), origin="upper", zorder=0, interpolation="bilinear")
        im.set_transform(Affine2D().rotate(view.angle) + ax.transData)


class View:
    """Projects lon/lat to flat meters, optionally rotated so `up` points up the page."""

    def __init__(self, origin: cl.LonLat, up_deg: float = 0.0):
        self.f = cl.LocalFrame(origin)
        self.angle = math.radians(up_deg)
        self.c, self.s = math.cos(self.angle), math.sin(self.angle)

    def xy(self, p: cl.LonLat) -> Tuple[float, float]:
        x, y = self.f.xy(p)
        return x * self.c - y * self.s, x * self.s + y * self.c

    def many(self, pts: Sequence[cl.LonLat]) -> Tuple[List[float], List[float]]:
        xy = [self.xy(p) for p in pts]
        return [p[0] for p in xy], [p[1] for p in xy]


def draw_base(ax, course: cl.Course, view: View, photo: Optional[Photo] = None) -> None:
    if photo:
        photo.draw(ax, view)
        draw_outlines(ax, course, view)
        return
    ax.set_facecolor(COLORS["background"])
    for kind in DRAW_ORDER:
        for ft in course.features:
            if ft.kind == kind:
                for ring in rings_of(ft.geometry):
                    ax.fill(*view.many(ring), color=COLORS[kind], lw=0, zorder=1)
    for ft in course.features:
        if ft.kind == "cartpath" and ft.geometry["type"] == "LineString":
            ax.plot(*view.many([tuple(p) for p in ft.geometry["coordinates"]]), color=COLORS["cartpath"], lw=0.8, zorder=2)
        elif ft.kind in ("green", "tee"):  # not linked to a hole
            edge = "#d6336c" if ft.kind == "green" else "#f08c00"
            for ring in rings_of(ft.geometry):
                ax.fill(*view.many(ring), facecolor=COLORS[ft.kind], edgecolor=edge, lw=1.6, zorder=3)
            if ft.geometry["type"] == "Point":
                ax.plot(*view.xy(tuple(ft.geometry["coordinates"])), "o", ms=4, mfc="none", mec=edge, zorder=3)
    if course.boundary:
        ax.plot(*view.many(course.boundary), color="#555555", lw=1, ls="--", zorder=2)
    for n, h in course.holes.items():
        for tee in h.tees:
            if len(tee) == 1:
                ax.plot(*view.xy(tee[0]), "s", ms=4, color=COLORS["tee"], zorder=4)
            else:
                ax.fill(*view.many(tee), color=COLORS["tee"], ec="#2b6b35", lw=0.6, zorder=4)
        if h.green:
            ax.fill(*view.many(h.green), color=COLORS["green"], ec="#1b5e2a", lw=0.8, zorder=4)
        line = h.play_line()
        if line:
            ax.plot(*view.many(line), color=COLORS["line"], lw=1.2, ls=(0, (4, 3)), zorder=5)
        if "pin" in h.fixed:
            ax.plot(*view.xy(h.fixed["pin"]), marker="v", ms=5, color="#c92a2a", zorder=6)


def draw_outlines(ax, course: cl.Course, view: View) -> None:
    """Photo view: the photo shows the course, so only greens, tees, and lines of play are drawn."""
    for ft in course.features:
        if ft.kind in ("green", "tee"):
            edge = "#ff4fa3" if ft.kind == "green" else "#ffa94d"
            for ring in rings_of(ft.geometry):
                ax.plot(*view.many(ring), color=edge, lw=1.4, zorder=3)
    if course.boundary:
        ax.plot(*view.many(course.boundary), color="white", lw=0.8, ls="--", zorder=2)
    for n, h in course.holes.items():
        for tee in h.tees:
            if len(tee) > 1:
                ax.plot(*view.many(tee), color="white", lw=0.8, zorder=4)
        if h.green:
            ax.plot(*view.many(h.green), color="#fff200", lw=1.6, zorder=4)
        line = h.play_line()
        if line:
            ax.plot(*view.many(line), color="white", lw=1.2, ls=(0, (4, 3)), zorder=5)


def overview(course: cl.Course, out: Path, photo: Optional[Photo] = None) -> Path:
    import matplotlib.pyplot as plt

    pts = list(course.boundary or [])
    for h in course.holes.values():
        pts += (h.line or []) + (h.green or [])
    origin = cl.centroid(course.boundary) if course.boundary else pts[0]
    view = View(origin)
    fig, ax = plt.subplots(figsize=(12, 12))
    draw_base(ax, course, view, photo)
    for n, h in sorted(course.holes.items()):
        line = h.play_line()
        anchor_pt = line[0] if line else h.green_center()
        if anchor_pt:
            x, y = view.xy(anchor_pt)
            ax.text(x, y, str(n), fontsize=11, weight="bold", ha="center", va="center", zorder=7,
                    bbox=dict(boxstyle="circle,pad=0.25", fc="white", ec="black", lw=0.8))
        if h.green_center():
            gx, gy = view.xy(h.green_center())
            ax.text(gx, gy, str(n), fontsize=7, color="white", weight="bold", ha="center", va="center", zorder=7)
    ready = sum(1 for h in course.holes.values() if h.complete)
    ax.set_title(f"{course.name}: {ready} holes ready. Magenta = green not linked to a hole, orange = tee not linked.", fontsize=11)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    if photo:
        xs, ys = view.many(course_extent_pts(course))
        ax.set_xlim(min(xs) - 30, max(xs) + 30)
        ax.set_ylim(min(ys) - 30, max(ys) + 30)
    ax.text(0.99, 0.005, attribution(course, photo), transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
            color="white" if photo else "black")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def course_extent_pts(course: cl.Course) -> List[cl.LonLat]:
    pts = list(course.boundary or [])
    for h in course.holes.values():
        pts += (h.line or []) + (h.green or [])
    return pts


def attribution(course: cl.Course, photo: Optional[Photo]) -> str:
    return course.attribution + ("; " + photo.meta.get("attribution", "") if photo else "")


def point_back_along(line: Sequence[cl.LonLat], target: cl.LonLat, meters: float) -> cl.LonLat:
    """The point on the line of play that is `meters` straight-line distance from the target."""
    f = cl.LocalFrame(target)
    best = line[0]
    for a, b in zip(line, line[1:]):
        for i in range(41):
            u = i / 40
            p = f.lonlat(*(pa + u * (pb - pa) for pa, pb in zip(f.xy(a), f.xy(b))))
            if abs(cl.distance_m(p, target) - meters) < abs(cl.distance_m(best, target) - meters):
                best = p
    return best


def hole_view(course: cl.Course, n: int, out: Path, cart_yards: float = 150.0, photo: Optional[Photo] = None) -> Optional[Path]:
    import matplotlib.pyplot as plt

    h = course.holes.get(n)
    line = h.play_line() if h else None
    gc = h.green_center() if h else None
    if not h or not line or not gc or not h.green:
        return None
    f = cl.LocalFrame(line[0])
    gx, gy = f.xy(gc)
    up_deg = 90 - math.degrees(math.atan2(gy, gx))  # rotate so tee to green points straight up
    view = View(line[0], up_deg)

    cart = point_back_along(line, gc, cart_yards / cl.YARDS_PER_METER)
    y = cl.green_yardage(cart, h.green, h.fixed)

    fig, ax = plt.subplots(figsize=(7, 10))
    draw_base(ax, course, view, photo)
    for p, label in ((y.front_point, "F"), (y.center_point, "C"), (y.back_point, "B")):
        if p:
            ax.plot(*view.xy(p), "o", ms=4, color="black", zorder=8)
    ax.plot([view.xy(cart)[0], view.xy(gc)[0]], [view.xy(cart)[1], view.xy(gc)[1]], color="white" if photo else "black", lw=0.8, zorder=7)
    ax.plot(*view.xy(cart), "o", ms=12, color="#1971c2", mec="white", mew=2, zorder=9)

    xs, ys = view.many(line + h.green)
    pad = 45
    ax.set_xlim(min(xs) - pad - 40, max(xs) + pad + 40)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    par = f", par {h.par}" if h.par else ""
    ax.set_title(f"{course.name}: hole {n}{par}", fontsize=12)
    txt = "\n".join(f"{k} {v:.0f}" if v is not None else f"{k} --" for k, v in (("B", y.back), ("C", y.center), ("F", y.front)))
    ax.text(0.03, 0.97, txt, transform=ax.transAxes, va="top", ha="left", fontsize=26, weight="bold",
            family="monospace", zorder=10, bbox=dict(fc="white", ec="black", alpha=0.9))
    ax.text(0.99, 0.005, attribution(course, photo), transform=ax.transAxes, ha="right", va="bottom", fontsize=6,
            color="white" if photo else "black")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("course", help="course .geojson file")
    p.add_argument("--hole", type=int, action="append", help="only this hole view (repeatable); default every hole")
    p.add_argument("--out", help="output folder (default courses/preview/<course file name>)")
    p.add_argument("--no-overview", action="store_true")
    p.add_argument("--photo", action="store_true", help="draw on the aerial photo from course_imagery.py")
    args = p.parse_args(argv)
    try:
        import matplotlib

        matplotlib.use("Agg")
    except ImportError:
        raise SystemExit("matplotlib is needed: pip install matplotlib")
    path = Path(args.course)
    course = cl.load_course(path)
    out = Path(args.out) if args.out else REPO_ROOT / "courses" / "preview" / path.stem
    out.mkdir(parents=True, exist_ok=True)
    photo = Photo(path) if args.photo else None
    prefix = "photo-" if photo else ""
    if not args.no_overview:
        print(f"wrote {overview(course, out / f'{prefix}overview.png', photo)}")
    for n in args.hole or sorted(course.holes):
        written = hole_view(course, n, out / f"{prefix}hole-{n:02d}.png", photo=photo)
        print(f"wrote {written}" if written else f"hole {n}: no green or line of play to draw")
    return 0


if __name__ == "__main__":
    sys.exit(main())
