"""Dialog showing a frozen screenshot of the game window; drag a box to select a region."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget


class _Canvas(QWidget):
    selected = Signal(QRect)  # in image pixels

    def __init__(self, pix: QPixmap):
        super().__init__()
        self.pix = pix
        self.origin: QPoint | None = None
        self.sel = QRect()
        self.setCursor(Qt.CrossCursor)
        self.setMinimumSize(200, 150)

    def _target(self) -> QRect:
        pw, ph = self.pix.width(), self.pix.height()
        scale = min(self.width() / pw, self.height() / ph)
        w, h = round(pw * scale), round(ph * scale)
        return QRect((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def _to_image(self, r: QRect) -> QRect:
        t = self._target()
        s = self.pix.width() / max(1, t.width())
        out = QRect(round((r.x() - t.x()) * s), round((r.y() - t.y()) * s),
                    round(r.width() * s), round(r.height() * s))
        return out.intersected(self.pix.rect())

    def _clamp(self, p: QPoint) -> QPoint:
        t = self._target()
        return QPoint(min(max(p.x(), t.left()), t.right()), min(max(p.y(), t.top()), t.bottom()))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(20, 20, 20))
        t = self._target()
        p.drawPixmap(t, self.pix)
        p.fillRect(t, QColor(0, 0, 0, 110))
        if not self.sel.isNull():
            p.drawPixmap(self.sel, self.pix, self._to_image(self.sel))
            p.setPen(QPen(QColor(255, 200, 0), 2))
            p.drawRect(self.sel)

    def mousePressEvent(self, e) -> None:
        self.origin = self._clamp(e.position().toPoint())
        self.sel = QRect(self.origin, self.origin)
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self.origin is not None:
            self.sel = QRect(self.origin, self._clamp(e.position().toPoint())).normalized()
            self.update()

    def mouseReleaseEvent(self, _e) -> None:
        if self.origin is None:
            return
        self.origin = None
        if self.sel.width() > 3 and self.sel.height() > 3:
            self.selected.emit(self._to_image(self.sel))


class RegionPicker(QDialog):
    def __init__(self, image: QImage, hint: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Select region")
        self.rect_in_image: QRect | None = None
        layout = QVBoxLayout(self)
        label = QLabel(f"<b>{hint}</b><br>This is a frozen screenshot of the game window. Esc cancels.")
        label.setWordWrap(True)
        layout.addWidget(label)
        canvas = _Canvas(QPixmap.fromImage(image))
        canvas.selected.connect(self._done)
        layout.addWidget(canvas, 1)

        # Show the screenshot at 1:1 when it fits, otherwise as large as the screen allows.
        avail = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        dpr = (self.screen() or QGuiApplication.primaryScreen()).devicePixelRatio()
        w = min(round(image.width() / dpr) + 24, int(avail.width() * 0.95))
        h = min(round(image.height() / dpr) + 90, int(avail.height() * 0.95))
        self.resize(w, h)

    def _done(self, r: QRect) -> None:
        self.rect_in_image = r
        self.accept()
