"""Entry point: python -m mapletracker"""
from __future__ import annotations

import sys
import threading
import time
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from mapletracker.capture.ocr import OcrEngine
from mapletracker.core import fmt, session
from mapletracker.core.module import AppContext
from mapletracker.core.session import SessionController
from mapletracker.core.storage import Settings, data_dir, open_db
from mapletracker.modules import all_modules
from mapletracker.ui.main_window import MainWindow


def _log_errors_to(path) -> None:
    """Keep errors in app.log (appended, never wiped), so problems can be diagnosed later."""
    log = open(path, "a", buffering=1, encoding="utf-8")
    log.write(f"\n=== Maple Tracker started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
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


def main() -> int:
    root = data_dir()
    _log_errors_to(root / "app.log")
    app = QApplication(sys.argv)
    app.setApplicationName("Maple Tracker")
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
