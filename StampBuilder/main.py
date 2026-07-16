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
        if axis == 'x':
            origin[0] = minb[0] + ratio * (maxb[0] - minb[0])
            normal = [1.0, 0.0, 0.0]
        else:
            origin[1] = minb[1] + ratio * (maxb[1] - minb[1])
            normal = [0.0, 1.0, 0.0]

        try:
            section = mesh.section(plane_origin=origin, plane_normal=normal)
            if section is None:
                return None
            path2d = section.to_planar()
            polys = getattr(path2d, 'polygons_full', None)
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

        # Load base first
        if STAMP_BASE.exists():
            try:
                mesh = geometry.load_mesh(STAMP_BASE)
                # try vertical cross-section first
                cross = self._compute_cross_section(mesh, axis='x', ratio=0.5)
                if cross is None:
                    # fallback to top-down silhouette if no section
                    sil = geometry.silhouette(mesh)
                    cross = sil
                self.base_cross = cross
                item = rendering.make_item_from_shapely(cross, pen_color="#000000", fill_color="#ffefe0", z=0)
                self.preview.scene().addItem(item)
                loaded_any = True
            except ImportError as e:
                load_errors.append(f"{STAMP_BASE.name}: missing libs: {e}")
            except Exception as e:
                load_errors.append(f"{STAMP_BASE.name}: {e}")

        # Load tray(s) according to mode and visibility
        from shapely.affinity import translate as _shapely_translate
        base_centroid = None
        try:
            if self.base_cross is not None:
                base_centroid = self.base_cross.centroid
        except Exception:
            base_centroid = None

        if self.show_trays and TRAY1.exists():
            try:
                mesh = geometry.load_mesh(TRAY1)
                cross = self._compute_cross_section(mesh, axis='x', ratio=0.5)
                if cross is None:
                    cross = geometry.silhouette(mesh)
                # recentre relative to base so items appear together in preview
                try:
                    if base_centroid is not None:
                        tray_cent = cross.centroid
                        dx = base_centroid.x - tray_cent.x
                        dy = base_centroid.y - tray_cent.y
                        cross = _shapely_translate(cross, xoff=dx, yoff=dy)
                except Exception:
                    pass
                self.tray1_cross = cross
                item = rendering.make_item_from_shapely(cross, pen_color="#444444", fill_color="#ffe6e6", z=1)
                self.preview.scene().addItem(item)
                loaded_any = True
            except Exception as e:
                load_errors.append(f"{TRAY1.name}: {e}")

        if self.show_trays and self.tray_double and TRAY2.exists():
            try:
                mesh = geometry.load_mesh(TRAY2)
                cross = self._compute_cross_section(mesh, axis='x', ratio=0.5)
                if cross is None:
                    cross = geometry.silhouette(mesh)
                # recentre relative to base
                try:
                    if base_centroid is not None:
                        tray_cent = cross.centroid
                        dx = base_centroid.x - tray_cent.x
                        dy = base_centroid.y - tray_cent.y
                        cross = _shapely_translate(cross, xoff=dx, yoff=dy)
                except Exception:
                    pass
                self.tray2_cross = cross
                item = rendering.make_item_from_shapely(cross, pen_color="#444444", fill_color="#e6ffe6", z=1)
                self.preview.scene().addItem(item)
                loaded_any = True
            except Exception as e:
                load_errors.append(f"{TRAY2.name}: {e}")

        if load_errors:
            self.statusBar().showMessage("Some assets failed to render. Check console for details.")
            for msg in load_errors:
                print("Asset render error:", msg)

        # Re-create pattern preview items (stacked) so they remain visible after scene clear
        for i, pat in enumerate(self.patterns):
            try:
                preview_item = rendering.make_item_from_shapely(pat['silhouette'], pen_color="#003366", fill_color="#cfeff6", z=2)
                x, y = (-50 * i, 0)
                preview_item.setPos(x, y)
                self.preview.scene().addItem(preview_item)
            except Exception:
                pass

        # Re-add placed items (they were removed by clear) so layout persists
        for it in list(self.placed_items):
            try:
                self.preview.scene().addItem(it)
            except Exception:
                pass

        if loaded_any:
            self.preview.fit_view()
            if not missing and not load_errors:
                self.statusBar().showMessage("Assets loaded — cross-sections shown")

    def import_pattern(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Pattern STL", "", "STL Files (*.stl);;All Files (*)")
        if not path:
            return
        try:
            mesh = geometry.load_mesh(path)
            sil = geometry.silhouette(mesh)
        except ImportError as e:
            QMessageBox.critical(self, "Missing Dependencies", str(e) + "\nInstall requirements.txt and try again.")
            return
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load mesh: {e}")
            return

        # Create a graphics prototype item (not placed directly)
        try:
            prototype = rendering.make_item_from_shapely(sil, pen_color="#003366", fill_color="#88ccee", z=2)
            # store pattern with prototype
            self.patterns.append({"path": path, "mesh": mesh, "silhouette": sil, "prototype": prototype})
            self.patterns_list.addItem(Path(path).name)
            # show a small representative item at top-left for preview
            x, y = self._next_preview_offset()
            preview_item = rendering.make_item_from_shapely(sil, pen_color="#003366", fill_color="#cfeff6", z=2)
            preview_item.setPos(x, y)
            self.preview.scene().addItem(preview_item)
            self.preview.fit_view()
            self.statusBar().showMessage(f"Imported pattern: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Render Error", f"Pattern loaded but failed to render: {e}")

    def _next_preview_offset(self):
        # stack small previews horizontally so user sees imported items
        count = len(self.patterns) - 1 if self.patterns else 0
        x = -50 * count
        y = 0
        return x, y

    def clear_placements(self):
        for it in list(self.placed_items):
            try:
                self.preview.scene().removeItem(it)
            except Exception:
                pass
        self.placed_items = []
        self.statusBar().showMessage("Placements cleared")

    def place_sequence_clicked(self):
        seq = self.sequence_input.text().strip().upper()
        if not seq:
            QMessageBox.information(self, "No sequence", "Enter a sequence like AABBC")
            return
        try:
            self.place_sequence(seq)
        except Exception as e:
            QMessageBox.critical(self, "Placement Error", str(e))

    def place_sequence(self, sequence):
        # Map letters A,B,C... to imported patterns in order
        if not self.patterns:
            raise RuntimeError("No patterns imported. Import at least one pattern before placing.")

        # build mapping
        mapping = {}
        for i, pat in enumerate(self.patterns):
            letter = chr(ord('A') + i)
            mapping[letter] = i

        # validate sequence
        for ch in sequence:
            if ch < 'A' or ch > 'Z':
                raise ValueError(f"Invalid character in sequence: {ch}")
            if ch not in mapping:
                raise ValueError(
                    f"Sequence references pattern '{ch}' but only {len(self.patterns)} patterns imported (A..{chr(ord('A')+len(self.patterns)-1)})"
                )

        # clear prior placements
        self.clear_placements()

        # compute usable area from base silhouette bounding box (fallback to a default rect)
        if self.base_cross is not None:
            try:
                minx, miny, maxx, maxy = self.base_cross.bounds
            except Exception:
                # if bounds not available, fallback
                ux0, uy0, ux1, uy1 = -30.0, -10.0, 30.0, 10.0
            else:
                # inset by 10% margin
                margin_x = (maxx - minx) * 0.1
                margin_y = (maxy - miny) * 0.1
                ux0 = minx + margin_x
                uy0 = miny + margin_y
                ux1 = maxx - margin_x
                uy1 = maxy - margin_y
        else:
            ux0, uy0, ux1, uy1 = -30.0, -10.0, 30.0, 10.0

        usable_width = ux1 - ux0
        usable_height = uy1 - uy0
        long_axis = 'x' if usable_width >= usable_height else 'y'

        n = len(sequence)
        if n == 1:
            positions = [((ux0 + ux1) / 2.0, (uy0 + uy1) / 2.0)]
        elif n == 2:
            if long_axis == 'x':
                positions = [(ux0, (uy0 + uy1) / 2.0), (ux1, (uy0 + uy1) / 2.0)]
            else:
                positions = [((ux0 + ux1) / 2.0, uy0), ((ux0 + ux1) / 2.0, uy1)]
        else:
            # evenly distribute along long axis
            positions = []
            for i in range(n):
                t = i / (n - 1)
                if long_axis == 'x':
                    x = ux0 + t * usable_width
                    y = (uy0 + uy1) / 2.0
                else:
                    x = (ux0 + ux1) / 2.0
                    y = uy0 + t * usable_height
                positions.append((x, y))

        # For each sequence letter, create a new graphics item for that pattern silhouette
        for pos, ch in zip(positions, sequence):
            pat_idx = mapping[ch]
            pat = self.patterns[pat_idx]
            sil = pat['silhouette']
            # make an item
            item = rendering.make_item_from_shapely(sil, pen_color="#003366", fill_color="#88ccee", z=2)
            # QGraphics coordinates: our rendering earlier inverted Y when creating path
            # We used -y in conversion, so placing at (x, y) requires setting pos to (x, -y)
            item.setPos(pos[0], -pos[1])
            self.preview.scene().addItem(item)
            self.placed_items.append(item)

        self.preview.fit_view()
        self.statusBar().showMessage(f"Placed sequence: {sequence}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
