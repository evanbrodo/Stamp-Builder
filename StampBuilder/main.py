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
        self.placement_widget.setLayout(placement_layout)
        self.placement_dock.setWidget(self.placement_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.placement_dock)

        # Toolbar
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

        # base silhouette cache
        self.base_silhouette = None

        # Try to auto-load assets if available (best-effort)
        self._try_load_assets()

    def _try_load_assets(self):
        # Check which asset files are present
        missing = []
        present = []
        for p in (STAMP_BASE, TRAY1, TRAY2):
            if not p.exists():
                missing.append(p.name)
            else:
                present.append(p)

        if missing:
            # Inform user which files are absent (non-fatal)
            self.statusBar().showMessage(f"Missing assets: {', '.join(missing)} — place them in assets/")

        loaded_any = False
        load_errors = []
        # Attempt to load and render any asset that exists
        for p in present:
            try:
                mesh = geometry.load_mesh(p)
                sil = geometry.silhouette(mesh)
                # Choose visual style: base darker, trays lighter
                if p == STAMP_BASE:
                    self.base_silhouette = sil
                    pen_color = "#000000"
                    fill_color = "#e8e8e8"
                    z = 0
                else:
                    pen_color = "#444444"
                    fill_color = "#f6f6f6"
                    z = 1
                item = rendering.make_item_from_shapely(sil, pen_color=pen_color, fill_color=fill_color, z=z)
                self.preview.scene().addItem(item)
                loaded_any = True
            except Exception as e:
                # Record but keep trying other assets
                load_errors.append(f"{p.name}: {e}")

        if load_errors:
            # Show a condensed error message if any asset failed to render
            self.statusBar().showMessage("Some assets failed to render (requires trimesh/shapely). Check console for details.")
            for msg in load_errors:
                print("Asset render error:", msg)

        if loaded_any:
            # Fit the view to whatever was added
            self.preview.fit_view()
            if not missing and not load_errors:
                self.statusBar().showMessage("Assets loaded — silhouettes shown")
            else:
                # If some were missing/errored we already set a message above; ensure it's visible
                pass

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
            prototype = rendering.make_item_from_shapely(sil, pen_color="#003366", fill_color="#88ccee", z=1)
            # store pattern with prototype
            self.patterns.append({"path": path, "mesh": mesh, "silhouette": sil, "prototype": prototype})
            self.patterns_list.addItem(Path(path).name)
            # show a small representative item at top-left for preview
            x, y = self._next_preview_offset()
            preview_item = rendering.make_item_from_shapely(sil, pen_color="#003366", fill_color="#cfeff6", z=1)
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
            self.preview.scene().removeItem(it)
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
        if self.base_silhouette is not None:
            minx, miny, maxx, maxy = self.base_silhouette.bounds
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
