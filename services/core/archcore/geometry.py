"""Pure 2D geometry helpers. All units are model units (metres by default)."""
from __future__ import annotations
import math

Point = tuple[float, float]


def distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def signed_area(pts: list[Point]) -> float:
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def polygon_area(pts: list[Point]) -> float:
    if len(pts) < 3:
        raise ValueError("a polygon needs at least 3 points")
    return abs(signed_area(pts))


def perimeter(pts: list[Point]) -> float:
    return sum(distance(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))


def point_in_polygon(p: Point, pts: list[Point]) -> bool:
    x, y = p
    inside = False
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def point_along(start: Point, end: Point, d: float) -> Point:
    L = distance(start, end)
    if L == 0:
        raise ValueError("zero-length segment")
    t = d / L
    return (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)


def wall_footprint(start: Point, end: Point, thickness: float) -> list[Point]:
    """Rectangle around a wall centreline."""
    L = distance(start, end)
    if L == 0:
        raise ValueError("zero-length wall")
    dx, dy = (end[0] - start[0]) / L, (end[1] - start[1]) / L
    nx, ny, h = -dy, dx, thickness / 2.0
    return [
        (start[0] + nx * h, start[1] + ny * h),
        (end[0] + nx * h, end[1] + ny * h),
        (end[0] - nx * h, end[1] - ny * h),
        (start[0] - nx * h, start[1] - ny * h),
    ]


# ---------------------------------------------------------------- polygon validation
EPS = 1e-9  # absolute tolerance, appropriate for metre-scale models


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return (min(a[0], b[0]) - EPS <= p[0] <= max(a[0], b[0]) + EPS and
            min(a[1], b[1]) - EPS <= p[1] <= max(a[1], b[1]) + EPS)


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """True if closed segments ab and cd share any point (crossing, touching or overlapping)."""
    d1, d2, d3, d4 = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    if ((d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS)) and \
       ((d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS)):
        return True
    return ((abs(d1) <= EPS and _on_segment(a, b, c)) or (abs(d2) <= EPS and _on_segment(a, b, d)) or
            (abs(d3) <= EPS and _on_segment(c, d, a)) or (abs(d4) <= EPS and _on_segment(c, d, b)))


def validate_simple_polygon(pts: list[Point]) -> None:
    """Raise ValueError unless pts is a finite, non-degenerate, simple (non-self-intersecting) polygon."""
    n = len(pts)
    if n < 3:
        raise ValueError("a polygon needs at least 3 points")
    if not all(math.isfinite(c) for p in pts for c in p):
        raise ValueError("polygon has non-finite coordinates")
    for i in range(n):
        if distance(pts[i], pts[(i + 1) % n]) <= EPS:
            raise ValueError("polygon has duplicate consecutive points")
    for i in range(n):
        a, b, c = pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        if abs(_cross(a, b, c)) <= EPS and (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) < 0:
            raise ValueError("polygon boundary doubles back on itself")
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue  # adjacent edges legitimately share an endpoint
            if segments_intersect(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n]):
                raise ValueError("polygon boundary self-intersects")
    if polygon_area(pts) <= EPS:
        raise ValueError("polygon has zero area")
