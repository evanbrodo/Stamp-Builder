"""Main application entry point — import UI, preview rendering, and placement."""

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QGraphicsView,
    QGraphicsScene,
    QDockWidget,
    QListWidget,
    QFileDialog,
    QMessageBox,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QCheckBox,
    QSlider,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QAction

from StampBuilder import geometry
from StampBuilder import rendering


ASSETS_DIR = Path(__file__).parent.parent / "assets"
STAMP_BASE = ASSETS_DIR / "StampBase.stl"
TRAY1 = ASSETS_DIR / "Tray1Slot.stl"
TRAY2 = ASSETS_DIR / "Tray2Slot.stl"


class PreviewView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        # Use QPainter's Antialiasing render hint
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        self._panning = False
        self._last_pos = None

    def wheelEvent(self, event):
        # Simple zoom: scale by 1.25 per wheel step
        zoom_in_factor = 1.25
        zoom_out_factor = 1 / zoom_in_factor
        if event.angleDelta().y() > 0:
            scale_factor = zoom_in_factor
        else:
            scale_factor = zoom_out_factor
        self.scale(scale_factor, scale_factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton or (
            event.button() == Qt.LeftButton and event.modifiers() & Qt.ShiftModifier
        ):
            self._panning = True
            self.setCursor(Qt.ClosedHandCursor)
            self._last_pos = event.pos()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._last_pos:
            delta = event.pos() - self._last_pos
            self._last_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton or (
            event.button() == Qt.LeftButton and event.modifiers() & Qt.ShiftModifier
        ):
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            self._last_pos = None
        else:
            super().mouseReleaseEvent(event)

    def fit_view(self):
        if not self.scene().items():
            return
        self.scene().setSceneRect(self.scene().itemsBoundingRect())
        self.fitInView(self.scene().itemsBoundingRect(), Qt.KeepAspectRatio)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stamp Builder")
        self.resize(1200, 800)

        self.preview = PreviewView(self)
        self.setCentralWidget(self.preview)

        # Dock: pattern list
        self.patterns_dock = QDockWidget("Patterns", self)
        self.patterns_list = QListWidget()
        self.patterns_dock.setWidget(self.patterns_list)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.patterns_dock)

        # Dock: placement UI
        self.placement_dock = QDockWidget("Placement", self)
        self.placement_widget = QWidget()
        placement_layout = QVBoxLayout()
        h = QHBoxLayout()
        h.addWidget(QLabel("Sequence (e.g. AABBC):"))
        self.sequence_input = QLineEdit()
        h.addWidget(self.sequence_input)
        placement_layout.addLayout(h)
        place_btn = QPushButton("Place Sequence")
        place_btn.clicked.connect(self.place_sequence_clicked)
        placement_layout.addWidget(place_btn)
        clear_btn = QPushButton("Clear Placements")
        clear_btn.clicked.connect(self.clear_placements)
        placement_layout.addWidget(clear_btn)

        # New explicit controls for trays (visible in Placement panel)
        self.show_trays_cb = QCheckBox("Show Trays")
        self.show_trays_cb.setChecked(True)
        self.show_trays_cb.stateChanged.connect(self._toggle_show_trays)
        placement_layout.addWidget(self.show_trays_cb)

        self.tray_mode_btn = QPushButton("Tray: Double")
        self.tray_mode_btn.setCheckable(False)
        self.tray_mode_btn.clicked.connect(self._toggle_tray_mode)
        placement_layout.addWidget(self.tray_mode_btn)

        # Spacing slider: 0 => all stamps at center, 100 => current spacing
        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Spacing:"))
        self.spacing_slider = QSlider(Qt.Horizontal)
        self.spacing_slider.setMinimum(0)
        self.spacing_slider.setMaximum(100)
        self.spacing_slider.setValue(100)
        self.spacing_slider.setTickInterval(10)
        self.spacing_slider.valueChanged.connect(self._on_spacing_slider_changed)
        slider_row.addWidget(self.spacing_slider)
        self.spacing_value_label = QLabel("100%")
        slider_row.addWidget(self.spacing_value_label)
        placement_layout.addLayout(slider_row)

        self.placement_widget.setLayout(placement_layout)
        self.placement_dock.setWidget(self.placement_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.placement_dock)

        # Toolbar (kept for Import/Fit convenience)
        toolbar = self.addToolBar("Main")
        import_action = QAction("Import Pattern", self)
        import_action.triggered.connect(self.import_pattern)
        toolbar.addAction(import_action)

        fit_action = QAction("Fit View", self)
        fit_action.triggered.connect(self.preview.fit_view)
        toolbar.addAction(fit_action)

        self.statusBar().showMessage("Stamp Builder — ready")

        # Keep loaded pattern data (list of dicts)
        # each dict: {path, mesh, silhouette, prototype}
        self.patterns = []
        # placed instances (QGraphicsPathItems)
        self.placed_items = []

        # base cross-section cache
        self.base_cross = None
        self.tray1_cross = None
        self.tray2_cross = None

        # tray mode and visibility state
        self.tray_double = True
        self.show_trays = True

        # spacing control state
        self.spacing_factor = 1.0  # 0..1 where 0=center, 1=current spacing
        self._base_positions = None  # stored base positions for last placement (logical coords)

        # Try to auto-load assets if available (best-effort)
        self._try_load_assets()

    def _toggle_show_trays(self, state=None):
        # Checkbox calls this; state may be Qt.Checked/Unchecked or None
        try:
            self.show_trays = bool(self.show_trays_cb.isChecked())
        except Exception:
            self.show_trays = True
        self._try_load_assets()

    def _toggle_tray_mode(self):
        self.tray_double = not self.tray_double
        # update button text
        self.tray_mode_btn.setText("Tray: Double" if self.tray_double else "Tray: Single")
        self._try_load_assets()

    def _on_spacing_slider_changed(self, value):
        try:
            self.spacing_factor = max(0.0, min(1.0, float(value) / 100.0))
            self.spacing_value_label.setText(f"{int(self.spacing_factor*100)}%")
            # If we have placed items and base positions, update positions live
            if self._base_positions and self.placed_items:
                self._apply_spacing_factor_to_placed_items()
        except Exception:
            pass

    def _apply_spacing_factor_to_placed_items(self):
        # Reposition existing placed items by interpolating between center and base positions
        if not self._base_positions or not self.placed_items:
            return
        try:
            base = self._base_positions
            n = len(base)
            # compute center of base positions
            cx = sum(p[0] for p in base) / n
            cy = sum(p[1] for p in base) / n
            for item, (bx, by) in zip(self.placed_items, base):
                nx = cx + self.spacing_factor * (bx - cx)
                ny = cy + self.spacing_factor * (by - cy)
                # setPos uses (x, -y) due to coordinate inversion used elsewhere
                item.setPos(nx, -ny)
        except Exception as e:
            print("Failed to apply spacing factor:", e)

    def _compute_cross_section(self, mesh, axis='x', ratio=0.5):
        """Compute a 2D shapely geometry representing a vertical cross-section of `mesh`.
        axis: 'x' or 'y' determining the plane normal (slice perpendicular to X or Y axis).
        ratio: 0..1 position along the axis within the mesh bounding box.
        Returns a shapely geometry or None if no section found.
        """
        try:
            import trimesh
            from shapely.ops import unary_union
        except Exception as e:
            raise ImportError("trimesh and shapely are required for cross-section computation") from e

        try:
            bounds = mesh.bounds  # array [[minx,miny,minz],[maxx,maxy,maxz]]
            minb = bounds[0]
            maxb = bounds[1]
        except Exception:
            # if mesh has no bounds, fall back to silhouette
            return None

        origin = mesh.centroid.copy()
        # Force X-axis slice at ratio (user requested .5 on X)
        origin[0] = minb[0] + ratio * (maxb[0] - minb[0])
        normal = [1.0, 0.0, 0.0]

        try:
            section = mesh.section(plane_origin=origin, plane_normal=normal)
            if section is None:
                return None
            path2d = section.to_planar()
            # prefer polygons_full but accept polygons or converted paths if needed
            polys = getattr(path2d, 'polygons_full', None)
            if not polys:
                polys = getattr(path2d, 'polygons', None)
            if not polys:
                # try to construct polygons from path segments if available
                try:
                    raw = getattr(path2d, 'paths', None)
                    polys = []
                    if raw:
                        for p in raw:
                            coords = getattr(p, 'vertices', None)
                            if coords is not None and len(coords) >= 3:
                                from shapely.geometry import Polygon
                                polys.append(Polygon(coords))
                except Exception:
                    polys = None
            if not polys:
                return None
            geom = unary_union(polys)
            return geom
        except Exception as e:
            # any failure we treat as no cross-section available
            print("Cross-section compute error:", e)
            return None

    def _try_load_assets(self):
        # Rebuild the preview scene: clear and then render assets + pattern previews + placed items
        self.preview.scene().clear()

        missing = []
        present = []
        for p in (STAMP_BASE, TRAY1, TRAY2):
            if not p.exists():
                missing.append(p.name)
            else:
                present.append(p)

        if missing:
            self.statusBar().showMessage(f"Missing assets: {', '.join(missing)} — place them in assets/")

        loaded_any = False
        load_errors = []
        used_base_fallback = False

        # Load base first (but draw after trays so it's on top)
        base_geom = None
        if STAMP_BASE.exists():
            try:
                mesh = geometry.load_mesh(STAMP_BASE)
                # force vertical cross-section at X ratio=0.5
                cross = self._compute_cross_section(mesh, axis='x', ratio=0.5)
                if cross is None:
                    # fallback to top-down silhouette if no section
                    sil = geometry.silhouette(mesh)
                    cross = sil
                    used_base_fallback = True
                    print("Base: using silhouette fallback (no X=0.5 cross-section found)")
                self.base_cross = cross
                base_geom = cross
                loaded_any = True
            except ImportError as e:
                load_errors.append(f"{STAMP_BASE.name}: missing libs: {e}")
            except Exception as e:
                load_errors.append(f"{STAMP_BASE.name}: {e}")

        # Load tray(s) according to mode and visibility
        from shapely.affinity import translate as _shapely_translate
        base_centroid = None
        try:
            if base_geom is not None:
                base_centroid = base_geom.centroid
        except Exception:
            base_centroid = None

        if self.show_trays and TRAY1.exists():
            try:
                mesh = geometry.load_mesh(TRAY1)
                cross = self._compute_cross_section(mesh, axis='x', ratio=0.5)
                used_tray1_fallback = False
                if cross is None:
                    cross = geometry.silhouette(mesh)
                    used_tray1_fallback = True
                    print("Tray1: using silhouette fallback (no X=0.5 cross-section found)")
                # recenter relative to base so items appear together in preview
                try:
                    if base_centroid is not None:
                        tray_cent = cross.centroid
                        dx = base_centroid.x - tray_cent.x
                        dy = base_centroid.y - tray_cent.y
                        cross = _shapely_translate(cross, xoff=dx, yoff=dy)
                except Exception:
                    pass
                self.tray1_cross = cross
                # removed old filled tray visualization to keep only the new measurement outlines
                loaded_any = True
            except Exception as e:
                load_errors.append(f"{TRAY1.name}: {e}")

        if self.show_trays and self.tray_double and TRAY2.exists():
            try:
                mesh = geometry.load_mesh(TRAY2)
                cross = self._compute_cross_section(mesh, axis='x', ratio=0.5)
                used_tray2_fallback = False
                if cross is None:
                    cross = geometry.silhouette(mesh)
                    used_tray2_fallback = True
                    print("Tray2: using silhouette fallback (no X=0.5 cross-section found)")
                # recenter relative to base
                try:
                    if base_centroid is not None:
                        tray_cent = cross.centroid
                        dx = base_centroid.x - tray_cent.x
                        dy = base_centroid.y - tray_cent.y
                        cross = _shapely_translate(cross, xoff=dx, yoff=dy)
                except Exception:
                    pass
                self.tray2_cross = cross
                # removed old filled tray2 visualization to keep only the new measurement outlines
                loaded_any = True
            except Exception as e:
                load_errors.append(f"{TRAY2.name}: {e}")

        # Draw base on top of trays (higher z) so it visually overlays them
        if base_geom is not None:
            try:
                base_item = rendering.make_item_from_shapely(base_geom, pen_color="#000000", fill_color=None, z=3)
                self.preview.scene().addItem(base_item)
            except Exception as e:
                print("Failed to render base on top:", e)

        if load_errors:
            self.statusBar().showMessage("Some assets failed to render. Check console for details.")
            for msg in load_errors:
                print("Asset render error:", msg)

        # Re-create pattern preview items (stacked) so they remain visible after scene clear
-        for i, pat in enumerate(self.patterns):
-            try:
-                preview_item = rendering.make_item_from_shapely(pat['silhouette'], pen_color="#003366", fill_color="#cfeff6", z=4)
-                x, y = (-50 * i, 0)
-                preview_item.setPos(x, y)
-                self.preview.scene().addItem(preview_item)
-            except Exception:
-                pass
+        # (preview items removed — don't show imported patterns until placed)
 
         # Re-add placed items (they were removed by clear) so layout persists
         for it in list(self.placed_items):
             try:
                 self.preview.scene().addItem(it)
             except Exception:
                 pass
@@
-        # Create a graphics prototype item (not placed directly)
-        try:
-            prototype = rendering.make_item_from_shapely(sil, pen_color="#003366", fill_color="#88ccee", z=2)
-            # store pattern with prototype
-            self.patterns.append({"path": path, "mesh": mesh, "silhouette": sil, "prototype": prototype})
-            self.patterns_list.addItem(Path(path).name)
-            # show a small representative item at top-left for preview
-            x, y = self._next_preview_offset()
-            preview_item = rendering.make_item_from_shapely(sil, pen_color="#003366", fill_color="#cfeff6", z=4)
-            preview_item.setPos(x, y)
-            self.preview.scene().addItem(preview_item)
-            self.preview.fit_view()
-            self.statusBar().showMessage(f"Imported pattern: {Path(path).name}")
-        except Exception as e:
-            QMessageBox.critical(self, "Render Error", f"Pattern loaded but failed to render: {e}")
+        # Create a normalized prototype (origin at bottom-center) and store it; do not preview
+        from shapely.affinity import translate as _shapely_translate
+        try:
+            minx, miny, maxx, maxy = sil.bounds
+            center_x = (minx + maxx) / 2.0
+            baseline = miny
+            norm_sil = _shapely_translate(sil, xoff=-center_x, yoff=-baseline)
+            prototype = rendering.make_item_from_shapely(norm_sil, pen_color="#003366", fill_color=None, z=2)
+            self.patterns.append({"path": path, "mesh": mesh, "silhouette": sil, "normalized": norm_sil, "prototype": prototype})
+            self.patterns_list.addItem(Path(path).name)
+            self.preview.fit_view()
+            self.statusBar().showMessage(f"Imported pattern: {Path(path).name}")
+        except Exception as e:
+            QMessageBox.critical(self, "Render Error", f"Pattern loaded but failed to process: {e}")
@@
-        # For each sequence letter, create a new graphics item for that pattern silhouette
-        for pos, ch in zip(applied_positions, sequence):
-            pat_idx = mapping[ch]
-            pat = self.patterns[pat_idx]
-            sil = pat['silhouette']
-            # make an item
-            item = rendering.make_item_from_shapely(sil, pen_color="#003366", fill_color="#88ccee", z=2)
-            # QGraphics coordinates: our rendering earlier inverted Y when creating path
-            # We used -y in conversion, so placing at (x, y) requires setting pos to (x, -y)
-            item.setPos(pos[0], -pos[1])
-            self.preview.scene().addItem(item)
-            self.placed_items.append(item)
+        # For each sequence letter, create a new graphics item for that pattern silhouette
+        for pos, ch in zip(applied_positions, sequence):
+            pat_idx = mapping[ch]
+            pat = self.patterns[pat_idx]
+            sil_to_render = pat.get("normalized", pat["silhouette"])
+            # make an item (normalized silhouette has origin at bottom-center)
+            item = rendering.make_item_from_shapely(sil_to_render, pen_color="#003366", fill_color="#88ccee", z=2)
+            # QGraphics coordinates: our rendering earlier inverted Y when creating path
+            # placing at (x, y) will put the bottom-center of the stamp at that position
+            item.setPos(pos[0], -pos[1])
+            self.preview.scene().addItem(item)
+            self.placed_items.append(item)
