"""Entry point: python -m statisticbuddy"""
from __future__ import annotations

import sys
import threading
import time
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from statisticbuddy.capture.ocr import OcrEngine
from statisticbuddy.core import fmt, session
from statisticbuddy.core.module import AppContext
from statisticbuddy.core.session import SessionController
from statisticbuddy.core.storage import Settings, data_dir, open_db
from statisticbuddy.modules import all_modules
from statisticbuddy.ui.main_window import MainWindow


def _log_errors_to(path) -> None:
    """Keep errors in app.log (appended, never wiped), so problems can be diagnosed later."""
    log = open(path, "a", buffering=1, encoding="utf-8")
    log.write(f"\n=== StatisticBuddy started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    sys.stderr = log

    def hook(kind, value, tb):
        log.write(f"[{time.strftime('%H:%M:%S')}] unhandled error:\n")
        traceback.print_exception(kind, value, tb, file=log)

    sys.excepthook = hook


def _offer_to_continue(win, ctx: AppContext) -> None:
    """If the app closed mid-session, offer to pick that session up again."""
    row = session.latest_unfinished(ctx.db)
    keep = None
    if row is not None and (row["active_seconds"] or 0) >= 30:
        started = time.strftime("%H:%M", time.localtime(row["started_at"]))
        answer = QMessageBox.question(
            win, "Continue your session?",
            f"Your session from {started} ({fmt.duration(row['active_seconds'])} tracked) didn't finish, "
            "probably because the app closed while it was running.\n\n"
            "Continue it? Its totals so far are kept. Press Resume when you're back in the game.",
        )
        if answer == QMessageBox.Yes:
            ctx.session.continue_session(row)
            keep = row["id"]
    session.close_unfinished(ctx.db, keep=keep)


def _selftest() -> int:
    """`StatisticBuddy.exe --selftest`: check the packaged OCR and digit reader work. Writes to app.log."""
    import cv2
    import numpy as np

    from statisticbuddy.modules.exp.parser import parse_exp_text
    from statisticbuddy.modules.loot.digits import BUILTIN_TEMPLATES, DigitReader, to_bitmap

    img = np.full((14, 190, 3), (40, 30, 20), np.uint8)
    cv2.putText(img, "EXP. 12345678901 [45.678%]", (2, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.33,
                (235, 235, 235), 1, cv2.LINE_AA)
    exp = parse_exp_text(OcrEngine().read_text(img))

    slot = np.full((32, 32, 3), (213, 223, 225), np.uint8)
    stroke = np.zeros((32, 32), bool)
    x = 1
    for ch in "4385":
        g = to_bitmap(BUILTIN_TEMPLATES[ch][0])
        stroke[21:30, x:x + g.shape[1]] |= g
        x += g.shape[1] + 2
    outline = cv2.dilate(stroke.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & ~stroke
    slot[outline], slot[stroke] = (0, 0, 0), (255, 255, 255)
    count = DigitReader().read(slot)

    ok = exp is not None and exp.exp == 12345678901 and count is not None and count.value == 4385
    print(f"selftest: ocr={exp} digits={count.value if count else None} -> {'OK' if ok else 'FAILED'}",
          file=sys.stderr)
    return 0 if ok else 1


def main() -> int:
    root = data_dir()
    _log_errors_to(root / "app.log")
    if "--selftest" in sys.argv:
        return _selftest()
    app = QApplication(sys.argv)
    app.setApplicationName("StatisticBuddy")
    ctx = AppContext(db=open_db(root / "tracker.db"),
                     settings=Settings(root / "settings.json"),
                     ocr=OcrEngine())
    session.init_schema(ctx.db)
    modules = all_modules()
    for module in modules:
        module.init_schema(ctx.db)
    ctx.session = SessionController(ctx, modules)
    win = MainWindow(ctx, modules, ctx.session)
    win.show()
    _offer_to_continue(win, ctx)
    threading.Thread(target=ctx.ocr.warm_up, daemon=True).start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
