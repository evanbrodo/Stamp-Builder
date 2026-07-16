"""Geometry helpers: STL load, silhouette projection, transforms, and boolean helpers.

This module wraps trimesh and shapely utilities used by the application.
It keeps imports lazy and raises helpful errors if dependencies are missing.
"""
from pathlib import Path


def _require_trimesh_shapely():
    try:
        import trimesh
        from shapely.ops import unary_union
        from shapely.geometry import Polygon
    except Exception as e:
        raise ImportError(
            "Missing optional dependencies for geometry. Install requirements.txt (trimesh, shapely, numpy)."
        ) from e
    return trimesh, unary_union, Polygon


def load_mesh(path):
    """Load an STL (or other mesh) file and return a trimesh.Trimesh object."""
    trimesh, _, _ = _require_trimesh_shapely()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Mesh file not found: {path}")
    mesh = trimesh.load(p.as_posix(), force="mesh")
    # Ensure we have a Trimesh
    if mesh is None:
        raise RuntimeError(f"Failed to load mesh: {path}")
    # If scene returned (multiple geometries), combine
    if hasattr(mesh, "geometry") and isinstance(mesh, dict):
        mesh = trimesh.util.concatenate(tuple(mesh.values()))
    return mesh


def silhouette(mesh):
    """Compute a top-down silhouette (2D shapely Polygon or MultiPolygon) of the mesh.

    Approach:
    - Project each triangle face to XY plane and build a 2D polygon for the triangle.
    - Union all triangle polygons using shapely.ops.unary_union.

    This is not the most optimized approach for very large meshes but is
    simple and reliable for preview silhouettes.
    """
    trimesh, unary_union, Polygon = _require_trimesh_shapely()
    # Ensure we have faces and vertices
    if mesh.faces is None or len(mesh.faces) == 0:
        raise ValueError("Mesh has no faces")

    verts = mesh.vertices
    polys = []
    for f in mesh.faces:
        tri = verts[f][:, :2]  # take X,Y
        # Create polygon if valid (non-degenerate)
        try:
            poly = Polygon([(float(x), float(y)) for x, y in tri])
            if not poly.is_valid or poly.area == 0:
                continue
            polys.append(poly)
        except Exception:
            continue
    if not polys:
        # fallback to convex hull of vertex XY projection
        xy = verts[:, :2]
        try:
            hull = trimesh.points.PointCloud(xy).convex_hull
            coords = [(float(x), float(y)) for x, y in hull.vertices]
            return Polygon(coords)
        except Exception:
            raise RuntimeError("Failed to compute silhouette")

    merged = unary_union(polys)
    return merged
