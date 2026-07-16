"""
create_stamp_from_stl.py

Create a stamp STL from one or more input STL meshes (relief) by placing the relief on
(top of) a rectangular base and exporting a combined STL.

Usage example:
.venv\Scripts\python create_stamp_from_stl.py --input relief.stl --out Stamp.stl

Options allow setting base size, base thickness, desired relief height (scales input in Z),
padding, and inversion (recessed).

This script attempts a boolean union if trimesh supports it; otherwise it concatenates meshes.
"""

import argparse
import os
import sys

try:
    import trimesh
    import numpy as np
except Exception as e:
    print("Missing dependency:", e)
    print("Install dependencies in your venv: python -m pip install trimesh numpy")
    sys.exit(1)


def load_combined_mesh(paths):
    meshes = []
    for p in paths:
        if not os.path.exists(p):
            raise FileNotFoundError(p)
        m = trimesh.load(p, force='mesh')
        if isinstance(m, trimesh.Scene):
            # take all geometries and concatenate
            geoms = [g for g in m.geometry.values()]
            if geoms:
                meshes.extend(geoms)
        elif isinstance(m, trimesh.Trimesh):
            meshes.append(m)
        else:
            # try to coerce
            meshes.append(trimesh.util.concatenate(m))
    if not meshes:
        raise RuntimeError("No mesh data loaded from inputs")
    if len(meshes) == 1:
        return meshes[0]
    return trimesh.util.concatenate(meshes)


def main():
    p = argparse.ArgumentParser(description="Create a stamp STL from input STL relief meshes.")
    p.add_argument('--input', '-i', nargs='+', required=True, help='Input STL file(s) used as relief')
    p.add_argument('--out', '-o', default='Stamp.stl', help='Output STL filename')
    p.add_argument('--base-x', type=float, default=40.0, help='Base X size (mm)')
    p.add_argument('--base-y', type=float, default=40.0, help='Base Y size (mm)')
    p.add_argument('--base-thickness', type=float, default=5.0, help='Base thickness (mm)')
    p.add_argument('--relief-height', type=float, default=1.0, help='Desired relief height (mm)')
    p.add_argument('--pad', type=float, default=5.0, help='Padding around relief inside base (mm)')
    p.add_argument('--invert', action='store_true', help='Invert relief (make recessed)')
    p.add_argument('--no-boolean', action='store_true', help='Do not attempt boolean union; concatenate only')
    args = p.parse_args()

    print('Loading input mesh(es):', args.input)
    mesh = load_combined_mesh(args.input)
    print('Loaded mesh vertices:', len(mesh.vertices), 'faces:', len(mesh.faces))

    bounds = mesh.bounds  # (min, max) 2x3
    min_z = float(bounds[0, 2])
    max_z = float(bounds[1, 2])
    input_height = max_z - min_z
    if input_height <= 0:
        print('Warning: input mesh has zero height in Z. Treating as 1.0 mm for scaling.')
        input_height = 1.0

    # Determine scaling in Z so the relief maps to desired relief height
    scale_z = args.relief_height / input_height
    print(f'Input height: {input_height:.3f} mm, scaling Z by {scale_z:.6f} to reach {args.relief_height} mm')

    # Scale only in Z (preserve X/Y)
    transform = np.eye(4)
    transform[2, 2] = scale_z

    mesh.apply_translation(-mesh.bounds[0])  # move min to origin for predictable scaling
    mesh.apply_transform(transform)

    # After scaling, recompute bounds and center
    bounds2 = mesh.bounds
    size_xy = bounds2[1, :2] - bounds2[0, :2]
    center_xy = (bounds2[0, :2] + bounds2[1, :2]) / 2.0

    # Determine base size: at least provided base size, but expand if relief is larger+padding
    min_base_x = max(args.base_x, float(size_xy[0] + args.pad * 2.0))
    min_base_y = max(args.base_y, float(size_xy[1] + args.pad * 2.0))

    base_x = min_base_x
    base_y = min_base_y
    base_thickness = args.base_thickness

    print(f'Base dimension XxY: {base_x:.3f} x {base_y:.3f} mm (thickness {base_thickness} mm)')

    # Create base box centered at origin in X/Y, from z=0..base_thickness
    box_extents = (base_x, base_y, base_thickness)
    base = trimesh.creation.box(extents=box_extents)
    # box is centered at origin; move so base bottom is at z=0
    base.apply_translation((0.0, 0.0, base_thickness / 2.0))

    # Move relief to sit centered on base top
    # Current mesh is positioned with min at z=0 due to earlier translate
    # Compute mesh min z again
    mesh_min_z = float(mesh.bounds[0, 2])
    # translate so bottom sits at base_thickness
    mesh.apply_translation((- (center_xy[0]), - (center_xy[1]), base_thickness - mesh_min_z))

    # Center relief in X/Y relative to base
    # base is centered at origin, so mesh already centered by subtracting center_xy

    # If invert (recessed), we push mesh downward into base by relief height
    if args.invert:
        print('Inverting relief (making recessed). Translating relief into base.)')
        mesh.apply_translation((0.0, 0.0, -args.relief_height))

    # Attempt boolean union (may require external engines). Fallback to concatenation
    combined = None
    if not args.no_boolean:
        try:
            print('Attempting boolean union to produce a single solid (this may take some time)')
            # trimesh.boolean.union expects a list of meshes
            combined = trimesh.boolean.union([base, mesh], engine=None)
            if combined is None:
                raise RuntimeError('Boolean union returned None')
            print('Boolean union succeeded')
        except Exception as e:
            print('Boolean union failed:', e)
            print('Falling back to concatenating meshes (may result in overlapping geometry)')

    if combined is None:
        combined = trimesh.util.concatenate([base, mesh])

    out_path = args.out
    print('Exporting STL to:', out_path)
    combined.export(out_path)
    print('Done. Output written to', out_path)


if __name__ == '__main__':
    main()
