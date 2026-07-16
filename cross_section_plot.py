# cross_section_plot.py
# Enhanced export: PNG (high-res) and SVG, with CLI options and console reporting.

from pathlib import Path
import argparse
import trimesh
from shapely.ops import unary_union
from shapely.geometry import Polygon, MultiPolygon
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ASSETS = Path("assets")
BASE_P = ASSETS / "StampBase.stl"
TRAY1_P = ASSETS / "Tray1Slot.stl"
TRAY2_P = ASSETS / "Tray2Slot.stl"


def load_mesh(p: Path):
    if not p.exists():
        raise FileNotFoundError(f"Missing asset: {p}")
    return trimesh.load_mesh(str(p), force='mesh')


def compute_x_section(mesh, ratio=0.5, try_offsets=3, offset_step=0.005):
    """
    Attempt vertical X-axis slice at center (ratio=0.5).
    If section is None, try nearby offsets (left/right) to find a non-empty slice.
    Returns tuple (geom, used_offset)
    geom: shapely geometry (Polygon or MultiPolygon) or None
    used_offset: offset applied (0.0 means exact ratio)
    """
    bounds = mesh.bounds
    minb = bounds[0]
    maxb = bounds[1]
    base_x = minb[0] + ratio * (maxb[0] - minb[0])
    normals = (1.0, 0.0, 0.0)

    # try offsets around base_x
    offsets = [0.0]
    for i in range(1, try_offsets + 1):
        offsets.append(i * offset_step)
        offsets.append(-i * offset_step)

    for off in offsets:
        origin = mesh.centroid.copy()
        origin[0] = base_x + off
        section = mesh.section(plane_origin=origin, plane_normal=normals)
        if section is None:
            continue
        p2 = section.to_planar()
        # prefer polygons_full, fall back to polygons
        raw_polys = getattr(p2, "polygons_full", None) or getattr(p2, "polygons", None)
        if raw_polys:
            try:
                geom = unary_union(raw_polys)
                if isinstance(geom, (Polygon, MultiPolygon)):
                    return geom, off
            except Exception:
                pass
        # else try constructing from paths
        paths = getattr(p2, "paths", None)
        polys = []
        if paths:
            for path in paths:
                coords = getattr(path, "vertices", None)
                if coords is not None and len(coords) >= 3:
                    try:
                        polys.append(Polygon(coords))
                    except Exception:
                        pass
            if polys:
                return unary_union(polys), off
    return None, None


def silhouette(mesh):
    # fallback: top-down silhouette using convex hull of XY vertices
    pts = mesh.vertices[:, :2]
    try:
        from shapely.geometry import MultiPoint
        hull = MultiPoint(list(map(tuple, pts))).convex_hull
        return hull
    except Exception:
        return None


def geom_to_patches(geom, facecolor="#bda87c", edgecolor="#000000", linewidth=1.2, zorder=3):
    patches = []
    if geom is None:
        return patches
    if isinstance(geom, Polygon):
        polys = [geom]
    else:
        polys = [p for p in geom.geoms]
    for poly in polys:
        exterior = list(poly.exterior.coords)
        patch = mpatches.Polygon(exterior, closed=True,
                                facecolor=facecolor, edgecolor=edgecolor,
                                linewidth=linewidth, zorder=zorder)
        patches.append(patch)
        for hole in poly.interiors:
            hole_coords = list(hole.coords)
            hole_patch = mpatches.Polygon(hole_coords, closed=True,
                                          facecolor="white", edgecolor=edgecolor,
                                          linewidth=linewidth, zorder=zorder+1)
            patches.append(hole_patch)
    return patches


def draw_cross_sections(base_geom, tray_geoms, out_base, out_svg=False, dpi=300, width_inches=10):
    # unify bounds
    all_geoms = [g for g in ([base_geom] + tray_geoms) if g is not None]
    union = unary_union(all_geoms)
    minx, miny, maxx, maxy = union.bounds
    margin_x = (maxx - minx) * 0.06
    margin_y = (maxy - miny) * 0.06
    figw = width_inches
    figh = max(3, figw * ((maxy - miny + 2 * margin_y) / (maxx - minx + 2 * margin_x)))
    fig, ax = plt.subplots(figsize=(figw, figh))
    ax.set_facecolor("#fff0e6")
    plt.xlim(minx - margin_x, maxx + margin_x)
    plt.ylim(miny - margin_y, maxy + margin_y)
    ax.set_aspect('equal', adjustable='box')
    ax.axis('off')

    # draw hatched frame rectangle behind everything
    frame = mpatches.Rectangle((minx - margin_x, miny - margin_y),
                               (maxx - minx) + 2 * margin_x, (maxy - miny) + 2 * margin_y,
                               facecolor="#ffece6", edgecolor="#000000", linewidth=1.6,
                               hatch='////', zorder=0)
    ax.add_patch(frame)

    # draw trays (under base): lighter fills
    tray_color = "#d6b98d"
    for g in tray_geoms:
        if g is None:
            continue
        for p in geom_to_patches(g, facecolor=tray_color, edgecolor="#333333", linewidth=1.0, zorder=1):
            ax.add_patch(p)

    # draw base ON TOP with stronger edge and slightly different color
    if base_geom is not None:
        base_patches = geom_to_patches(base_geom, facecolor="#bda87c", edgecolor="#000000", linewidth=1.6, zorder=5)
        for p in base_patches:
            ax.add_patch(p)

    plt.tight_layout()
    png_out = f"{out_base}.png"
    svg_out = f"{out_base}.svg"
    fig.savefig(png_out, dpi=dpi)
    print(f"Saved PNG: {png_out} @ {dpi} DPI")
    if out_svg:
        fig.savefig(svg_out, format='svg')
        print(f"Saved SVG: {svg_out}")
    plt.close(fig)


def report_meta(label, geom, used_offset):
    if geom is None:
        print(f"{label}: NO GEOMETRY")
        return
    b = geom.bounds
    c = geom.centroid
    print(f"{label}: bounds={b}, centroid=({c.x:.4f}, {c.y:.4f}), used_offset={used_offset}")


def main():
    parser = argparse.ArgumentParser(description="Export X=0.5 vertical cross-sections as PNG/SVG and report metrics")
    parser.add_argument("--out", default="cross_section_result", help="Base filename for outputs (without extension)")
    parser.add_argument("--svg", action='store_true', help="Also save an SVG")
    parser.add_argument("--dpi", type=int, default=600, help="DPI for PNG export (default 600)")
    parser.add_argument("--width", type=float, default=12.0, help="Width in inches for PNG/SVG layout (default 12.0)")
    parser.add_argument("--ratio", type=float, default=0.5, help="X-axis ratio to slice at (0..1). Default 0.5)")
    args = parser.parse_args()

    base_mesh = load_mesh(BASE_P)
    tray1_mesh = load_mesh(TRAY1_P)
    tray2_mesh = load_mesh(TRAY2_P)

    base_sec, base_off = compute_x_section(base_mesh, ratio=args.ratio)
    if base_sec is None:
        print("Base: X section missing, using silhouette fallback")
        base_sec = silhouette(base_mesh)
        base_off = None

    tray1_sec, t1_off = compute_x_section(tray1_mesh, ratio=args.ratio)
    if tray1_sec is None:
        print("Tray1: X section missing, using silhouette fallback")
        tray1_sec = silhouette(tray1_mesh)
        t1_off = None

    tray2_sec, t2_off = compute_x_section(tray2_mesh, ratio=args.ratio)
    if tray2_sec is None:
        print("Tray2: X section missing, using silhouette fallback")
        tray2_sec = silhouette(tray2_mesh)
        t2_off = None

    # report pre-recenter metrics
    print("--- Pre-recenter metrics ---")
    report_meta("Base", base_sec, base_off)
    report_meta("Tray1", tray1_sec, t1_off)
    report_meta("Tray2", tray2_sec, t2_off)

    # recenter trays to base centroid for display
    try:
        bx, by = base_sec.centroid.x, base_sec.centroid.y
        from shapely.affinity import translate as from_shapely_translate
        def recenter(g):
            if g is None:
                return None
            gx, gy = g.centroid.x, g.centroid.y
            return from_shapely_translate(g, bx - gx, by - gy)
    except Exception:
        recenter = lambda g: g

    tray1_sec = recenter(tray1_sec)
    tray2_sec = recenter(tray2_sec)

    # report post-recenter metrics
    print("--- Post-recenter metrics (trays moved to base centroid) ---")
    report_meta("Tray1 recentered", tray1_sec, t1_off)
    report_meta("Tray2 recentered", tray2_sec, t2_off)

    draw_cross_sections(base_sec, [tray1_sec, tray2_sec], out_base=args.out, out_svg=args.svg, dpi=args.dpi, width_inches=args.width)

if __name__ == "__main__":
    main()
