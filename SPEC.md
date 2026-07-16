# Stamp Builder Specification

This repository contains the specification and initial scaffold for Stamp Builder, a focused Windows desktop CAD tool to automate creation of manufacturing stamp models.

## Project overview

Stamp Builder is a purpose-built Python application (PySide6) for composing and exporting watertight STL stamp assemblies for a proprietary manufacturing process. The app is intentionally narrow in scope: it loads a fixed Stamp Base, accepts one or more Stamp Pattern STLs, arranges repeated instances of the patterns inside the raised usable area of the Stamp Base, and exports a single merged STL suitable for 3D printing.

Key constraints
- Written in Python
- GUI using PySide6
- Final deliverable packaged as a standalone Windows executable
- Preview is a clean top-down silhouette (no raw triangle rendering)
- Export output is a single watertight STL that merges the Stamp Base and repeated patterns

## Manufacturing model

Every finished stamp package exported by the app consists of:
- One immutable StampBase STL (provided in assets/)
- One or more uploaded Stamp Pattern STLs
- Patterns are repeated along the raised center section of the Stamp Base
- The final result exported as one watertight STL

The included assets (StampBase.stl, Tray1Slot.stl, Tray2Slot.stl) should auto-load on app startup (the stl files are treated as assets/ and may be large binaries).

## User workflow (summary)
1. Open application → Stamp Base + tray visualizers auto-load
2. Import pattern STLs
3. Choose a pattern and preview
4. Adjust transforms or manual placement
5. Export a single watertight STL

## Preview & UX
- Top-down silhouette preview (no triangle cloud)
- Show base outline, usable raised area, imported pattern silhouettes, and trays
- Fit automatically to view, supports zoom/pan (mouse wheel, middle-drag, Shift+left-drag), Fit View and Home View
- Grid auto-scales with zoom

## Placement and patterns
- Repeat sequences expressed by letters (A, B, C, ...)
- Support automatic layouts: AAAAAA, ABABAB, ABCABC and arbitrary sequences like ABBC, ABCDE, AABCC
- Manual placement allowed
- Placement rules:
  - 1 stamp: center
  - 2 stamps: one at each end
  - 3+: evenly distribute across usable area

## Transformations
- Per-pattern and per-instance: Rotate (X/Y/Z), Mirror (X/Y/Z), Flip (X/Y/Z)
- Scope: selected instance / all instances of a type / entire pattern / whole layout

## Height rules
- Target overall stamp height: 26.924 mm
- If imported STL exceeds height: show difference and offer "Scale Height Only" (scale Z only, preserve X/Y)
- Imported stamp bottom sits flush on top of raised section of Stamp Base

## Tray visualizer
- Visual-only trays to verify fit
- Display options: Stamp only, Stamp inside Tray 1, Stamp inside Tray 2
- Indications: Fits / Too long / Too wide / Outside tray / Centered / Off center

## Project saving
- Save project as a JSON file that records imported STL paths, pattern sequence, repeat count, transforms, visibility, usable area, and settings
- Exported STL is separate from project file

## STL export
- Export single watertight manifold STL
- Merge base + repeated stamps and perform boolean unions
- Validate manifoldness

## Architecture (recommended)
Top-level layout:

StampBuilder/
  assets/           # StampBase.stl, Tray1Slot.stl, Tray2Slot.stl
  core/             # app bootstrap, config, lifecycle
  geometry/         # STL loading, silhouette projection, transforms, boolean helpers
  rendering/        # preview widgets and rendering helpers
  ui/               # higher-level widgets & dialogs
  projects/         # project serialization & management
  exports/          # export pipeline & validation
  main.py           # app entry point

Libraries and choices
- PySide6 for GUI
- trimesh for STL load/transform/export
- shapely for 2D polygon (silhouette) operations
- numpy (mesh & numeric ops)
- Optional: use Blender headless as fallback for robust boolean operations

Project file format: JSON with keys for assets, patterns, layout, usable_area, and settings.

## Prioritized backlog (initial issues)
1. Add SPEC.md (this document)
2. Scaffold repository layout + starter main.py (PySide6 placeholder)
3. Asset loader: auto-load StampBase and trays
4. STL loader + silhouette projection (trimesh + shapely)
5. 2D preview widget (QGraphicsView-based) rendering silhouettes, grid, and basic camera
6. Automatic placer + sequence parser
7. Transform controls and scope application
8. Export pipeline + boolean union (trimesh + fallback to Blender)
9. Project save/load (JSON)
10. Tray visualizer fit indicators
11. Packaging instructions (PyInstaller) for Windows build

## Future features
- Undo/Redo, pattern presets, snap-to-grid, collision detection, STL repair, boolean preview, drag-and-drop editing, etc.

---

This SPEC.md was generated from the provided project specification and a short implementation plan. If you want, I can:
- Commit this SPEC.md to the repository (done now),
- Create the issue backlog in GitHub issues, and
- Add an initial scaffold with a runnable PySide6 starter (I will add the scaffold next).

If you'd like a different format (MARKDOWN sections reorganized, or JSON schema for project files), tell me and I will update the spec.
