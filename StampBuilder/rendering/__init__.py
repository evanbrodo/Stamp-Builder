"""Rendering helpers for the 2D silhouette preview.

Contains utilities to convert shapely geometries to QPainterPath objects and
create QGraphicsPathItems for the scene.
"""
from PySide6.QtGui import QPainterPath, QBrush, QPen, QColor
from PySide6.QtWidgets import QGraphicsPathItem


def shapely_to_qpath(geom):
    """Convert a shapely Polygon or MultiPolygon to a QPainterPath."""
    path = QPainterPath()

    # shapely may be Polygon or MultiPolygon
    geoms = []
    try:
        # MultiPolygon has 'geoms'
        geoms = list(geom.geoms)
    except Exception:
        geoms = [geom]

    for g in geoms:
        # exterior
        exterior = g.exterior.coords
        first = True
        for x, y in exterior:
            if first:
                path.moveTo(x, -y)
                first = False
            else:
                path.lineTo(x, -y)
        path.closeSubpath()
        # interiors (holes)
        for interior in g.interiors:
            first = True
            for x, y in interior.coords:
                if first:
                    path.moveTo(x, -y)
                    first = False
                else:
                    path.lineTo(x, -y)
            path.closeSubpath()
    return path


def make_item_from_shapely(geom, pen_color="#333333", fill_color=None, z=0):
    """Return a QGraphicsPathItem for the given shapely geometry."""
    path = shapely_to_qpath(geom)
    item = QGraphicsPathItem(path)
    pen = QPen(QColor(pen_color))
    pen.setWidthF(0.3)
    item.setPen(pen)
    if fill_color:
        item.setBrush(QBrush(QColor(fill_color)))
    item.setZValue(z)
    return item


def make_item_from_polyline(points, pen_color="#003366", z=2.0, close=False, width=0.6):
    """
    Create a QGraphicsPathItem from an iterable of points.
    points: iterable of (x,y) or (x,y,z). Y is flipped internally like other rendering helpers (uses -y).
    pen_color: stroke color.
    z: QGraphics z-value for stacking.
    close: if True, closes the path.
    width: pen width in scene units (mm).
    Returns: QGraphicsPathItem (NOT added to any scene).
    """
    path = QPainterPath()
    first = True
    for p in points:
        if len(p) >= 2:
            x, y = float(p[0]), float(p[1])
        else:
            continue
        if first:
            path.moveTo(x, -y)
            first = False
        else:
            path.lineTo(x, -y)
    if close:
        path.closeSubpath()
    item = QGraphicsPathItem(path)
    pen = QPen(QColor(pen_color))
    pen.setWidthF(width)
    item.setPen(pen)
    item.setZValue(z)
    return item
