"""Application entry point for Stamp Builder.

This is a minimal PySide6 starter that creates the main window and a preview area.
It intentionally keeps dependencies optional at import time — the real app will
import trimesh/shapely when needed.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt


ASSETS_DIR = Path(__file__).parent.parent / "assets"
STAMP_BASE = ASSETS_DIR / "StampBase.stl"
TRAY1 = ASSETS_DIR / "Tray1Slot.stl"
TRAY2 = ASSETS_DIR / "Tray2Slot.stl"


class PreviewView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(self.renderHints() | Qt.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

    def wheelEvent(self, event):
        # Simple zoom: scale by 1.25 per wheel step
        zoom_in_factor = 1.25
        zoom_out_factor = 1 / zoom_in_factor
        if event.angleDelta().y() > 0:
            scale_factor = zoom_in_factor
        else:
            scale_factor = zoom_out_factor
        self.scale(scale_factor, scale_factor)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stamp Builder")
        self.resize(1200, 800)

        self.preview = PreviewView(self)
        self.setCentralWidget(self.preview)

        self.statusBar().showMessage("Stamp Builder — ready")

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
            self.statusBar().showMessage("Assets loaded (placeholders) — full preview not implemented yet")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
