"""Set up which parts of the game window each tracker reads."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from statisticbuddy.capture.game import GameNotFound, RelRegion, grab_game_frame
from statisticbuddy.capture.window import find_game_window
from statisticbuddy.core.module import RegionSpec, TrackerModule
from statisticbuddy.core.session import SessionController, to_qimage
from statisticbuddy.ui.region_picker import RegionPicker


class _RegionRow(QGroupBox):
    def __init__(self, module: TrackerModule, spec: RegionSpec, tab: RegionsTab):
        super().__init__(spec.label)
        self.module, self.spec, self.tab = module, spec, tab
        grid = QGridLayout(self)
        # Left: what was captured. Right: hint, state, what it was read as, buttons.
        self.preview = QLabel("No capture yet")
        self.preview.setMinimumSize(90, 30)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#111;color:#aaa;padding:4px")
        grid.addWidget(self.preview, 0, 0, 4, 1, Qt.AlignTop)

        hint = QLabel(spec.hint)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray")
        grid.addWidget(hint, 0, 1)
        self.state = QLabel()
        self.state.setWordWrap(True)
        grid.addWidget(self.state, 1, 1)
        self.read_as = QLabel("<b>Read as:</b> - (click Test)")
        self.read_as.setWordWrap(True)
        self.read_as.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(self.read_as, 2, 1)

        buttons = QHBoxLayout()
        select = QPushButton("Select…")
        select.clicked.connect(lambda: tab.select(self))
        test = QPushButton("Test")
        test.clicked.connect(lambda: tab.controller.read_now(test=True))
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)
        buttons.addStretch(1)
        for b in (select, test, clear):
            buttons.addWidget(b)
        grid.addLayout(buttons, 3, 1)
        grid.setColumnStretch(1, 1)
        self.update_state()

    def update_state(self, frame_size: tuple[int, int] | None = None) -> None:
        r = self.tab.controller.region(self.spec.key)
        if r is None:
            self.state.setText("Not set. This tracker uses manual entry only.")
            return
        text = f"Set: {r.width}x{r.height} at ({r.x}, {r.y}) in the game window"
        if frame_size and frame_size != (r.frame_width, r.frame_height):
            text += (f"  ⚠ The game window size changed ({r.frame_width}x{r.frame_height} → "
                     f"{frame_size[0]}x{frame_size[1]}). Select it again.")
        self.state.setText(text)

    def _clear(self) -> None:
        self.tab.controller.set_region(self.spec.key, None)
        self.preview.setText("No capture yet")
        self.read_as.setText("<b>Read as:</b> -")
        self.update_state()

    def show_result(self, res: dict, frame_size) -> None:
        self.update_state(frame_size)
        if res.get("image") is not None:
            pix = QPixmap.fromImage(res["image"])
            if pix.width() > 180 or pix.height() > 140:
                pix = pix.scaled(180, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview.setPixmap(pix)
        if res.get("error"):
            text = res["error"]
        else:
            read = res["read"]
            raw = f"\"{read.text}\"  →  " if self.spec.ocr != "none" else ""
            text = raw + self.module.describe(self.spec.key, read)
        self.read_as.setText(f"<b>Read as:</b> {html.escape(text)}")


class RegionsTab(QWidget):
    def __init__(self, controller: SessionController):
        super().__init__()
        self.controller = controller
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.game_label = QLabel()
        self.game_label.setWordWrap(True)
        find = QPushButton("Find game window")
        find.clicked.connect(self.check_game)
        test = QPushButton("Test read all")
        test.clicked.connect(lambda: controller.read_now(test=True))
        top.addWidget(self.game_label, 1)
        top.addWidget(find)
        top.addWidget(test)
        root.addLayout(top)

        self.rows: dict[str, _RegionRow] = {}
        for module, spec in controller.region_specs():
            row = _RegionRow(module, spec, self)
            self.rows[spec.key] = row
            root.addWidget(row)
        root.addStretch(1)

        controller.read_done.connect(self._on_read)
        self.check_game()

    def check_game(self) -> None:
        win = find_game_window(self.controller.game_title)
        if win is None:
            self.game_label.setText("❌ MapleStory window not found. Open the game (windowed or borderless) "
                                    "and make sure it isn't minimized.")
        else:
            c = win.client
            self.game_label.setText(f"✅ Found \"{win.title}\": {c.width}x{c.height} at ({c.left}, {c.top})")

    def select(self, row: _RegionRow) -> None:
        # Get our window out of the way so it isn't in the screenshot.
        self.window().showMinimized()
        QTimer.singleShot(400, lambda: self._grab_and_pick(row))

    def _grab_and_pick(self, row: _RegionRow) -> None:
        try:
            frame = grab_game_frame(self.controller.game_title)
        except GameNotFound as e:
            self._restore()
            QMessageBox.warning(self, "Game not found", str(e))
            return
        except Exception as e:
            self._restore()
            QMessageBox.critical(self, "Screen capture failed", f"{type(e).__name__}: {e}")
            return
        self._restore()
        dlg = RegionPicker(to_qimage(frame.image), row.spec.hint, self)
        if dlg.exec() and dlg.rect_in_image is not None:
            r = dlg.rect_in_image
            w, h = frame.size
            region = RelRegion(r.x(), r.y(), r.width(), r.height(), w, h)
            clash = self._overlapping(row.spec.key, region)
            if clash and QMessageBox.question(
                    self, "Same spot selected twice",
                    f"This box is on the same spot as \"{clash}\". Each one should read something "
                    f"different (e.g. a different quickslot key), otherwise both track the same "
                    f"number.\n\nUse this box anyway?") != QMessageBox.Yes:
                self.check_game()
                return
            self.controller.set_region(row.spec.key, region)
            row.update_state()
            self.controller.read_now(test=True)
        self.check_game()

    def _overlapping(self, key: str, new: RelRegion) -> str | None:
        """Label of another region that mostly covers the same spot, if any."""
        for _, spec in self.controller.region_specs():
            other = self.controller.region(spec.key)
            if spec.key == key or other is None:
                continue
            ix = max(0, min(new.x + new.width, other.x + other.width) - max(new.x, other.x))
            iy = max(0, min(new.y + new.height, other.y + other.height) - max(new.y, other.y))
            smaller = min(new.width * new.height, other.width * other.height)
            if smaller and ix * iy / smaller > 0.5:
                return spec.label
        return None

    def _restore(self) -> None:
        self.window().showNormal()
        self.window().activateWindow()

    def _on_read(self, out: dict) -> None:
        if out["error"]:
            self.game_label.setText(f"❌ {out['error']}")
            return
        win = out["window"]
        c = win.client
        self.game_label.setText(f"✅ Found \"{win.title}\": {c.width}x{c.height} at ({c.left}, {c.top})")
        for key, res in out["results"].items():
            if key in self.rows:
                self.rows[key].show_result(res, out["size"])
