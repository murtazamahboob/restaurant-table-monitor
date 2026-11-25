"""Geometry helpers for the restaurant floor: zones are polygons, a person
belongs to a table when their foot point (bottom centre of the box) is
inside the zone. Pure stdlib, deterministic."""

from __future__ import annotations

Point = tuple[float, float]
Polygon = list[Point]


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """Ray-casting point-in-polygon. Points exactly on an edge count as inside."""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        # On-segment check (collinear and within the bounding box).
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) < 1e-9 and min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9 \
                and min(y1, y2) - 1e-9 <= y <= max(y1, y2) + 1e-9:
            return True
        if (y1 > y) != (y2 > y):
            x_int = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_int:
                inside = not inside
    return inside


def rect_polygon(x: float, y: float, w: float, h: float) -> Polygon:
    """Axis-aligned rectangle as a polygon (clockwise from top-left)."""
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def expand_polygon(polygon: Polygon, margin: float) -> Polygon:
    """Expand an axis-aligned rectangle polygon by ``margin`` on all sides."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return rect_polygon(min(xs) - margin, min(ys) - margin,
                        max(xs) - min(xs) + 2 * margin,
                        max(ys) - min(ys) + 2 * margin)


def foot_point(bbox: tuple[float, float, float, float]) -> Point:
    """Bottom centre of a detection box (x, y, w, h) -> foot point."""
    x, y, w, h = bbox
    return (x + w / 2.0, y + h)
