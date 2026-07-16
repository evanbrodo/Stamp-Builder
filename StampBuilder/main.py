"""Main application entry point — extended with import UI and preview rendering.

This file is a superset of the earlier minimal starter app. It adds a toolbar to
import pattern STLs and show their silhouettes in the preview.
"""

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
    QAction,
    QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter

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
        if event.button() in (Qt.MiddleButton,) or (
            event.button() == Qt.LeftButton and event.modifiers() & Qt.ShiftModifier
        ):
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            self._last_pos = None
        else:
            super().mouseReleaseEvent(event)

    def fit_view(self):
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

        # Toolbar
        toolbar = self.addToolBar("Main")
        import_action = QAction("Import Pattern", self)
        import_action.triggered.connect(self.import_pattern)
        toolbar.addAction(import_action)

        fit_action = QAction("Fit View", self)
        fit_action.triggered.connect(self.preview.fit_view)
        toolbar.addAction(fit_action)

        self.statusBar().showMessage("Stamp Builder — ready")

        # Keep loaded pattern data
        self.patterns = []  # list of dicts: {path, mesh, silhouette, item}

        # Try to auto-load assets if available (best-effort)
        self._try_load_assets()

    def _try_load_assets(self):
        missing = []
        for p in (STAMP_BASE, TRAY1, TRAY2):
            if not p.exists():
                missing.append(p.name)
        if missing:
            self.statusBar().showMessage(f"Missing assets: {', '.join(missing)} — place them in assets/")
        else:
            # attempt to load and render base/trays silhouettes
            try:
                base_mesh = geometry.load_mesh(STAMP_BASE)
                base_sil = geometry.silhouette(base_mesh)
                item = rendering.make_item_from_shapely(base_sil, pen_color="#000000", fill_color="#e8e8e8", z=0)
                self.preview.scene().addItem(item)
                self.preview.fit_view()
                self.statusBar().showMessage("Assets loaded — base silhouette shown")
            except Exception:
                # non-fatal; just notify
                self.statusBar().showMessage("Assets present but failed to render silhouette (requires trimesh/shapely)")

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

        # Create a graphics item and add to scene
        try:
            item = rendering.make_item_from_shapely(sil, pen_color="#003366", fill_color="#88ccee", z=1)
            self.preview.scene().addItem(item)
            # store pattern
            self.patterns.append({"path": path, "mesh": mesh, "silhouette": sil, "item": item})
            self.patterns_list.addItem(Path(path).name)
            self.preview.fit_view()
            self.statusBar().showMessage(f"Imported pattern: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Render Error", f"Pattern loaded but failed to render: {e}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
