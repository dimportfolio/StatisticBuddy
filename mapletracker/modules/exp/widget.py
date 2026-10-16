"""EXP panel on the Live tab."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from mapletracker.core import fmt
from mapletracker.modules.exp.tracker import Stats
from mapletracker.ui.widgets import ManualRow, StatGrid

ROWS = [
    ("rate", "EXP / hour"),
    ("recent", "Last 10 min pace"),
    ("pct_rate", "% / hour"),
    ("eta", "Time to level"),
    ("gained", "EXP gained"),
    ("pct_gained", "% gained"),
    ("levels", "Levels gained"),
    ("current", "Current EXP"),
]


class ExpPanel(QWidget):
    def __init__(self, module):
        super().__init__()
        self.module = module
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.grid = StatGrid("EXP", ROWS)
        self.manual = ManualRow(["Current EXP, e.g. 12345678", "% (optional)"], self._submit)
        self.grid.add_row_widget(self.manual)
        layout.addWidget(self.grid)

    def _submit(self) -> None:
        exp_text, pct_text = self.manual.values()
        digits = "".join(ch for ch in exp_text if ch.isdigit())
        if not digits:
            QMessageBox.warning(self, "Manual EXP", "Enter your current EXP number.")
            return
        pct = None
        if pct_text:
            try:
                pct = float(pct_text.rstrip("%").replace(",", "."))
            except ValueError:
                QMessageBox.warning(self, "Manual EXP", "The % should be a number like 45.678.")
                return
            if not 0 <= pct < 100:
                QMessageBox.warning(self, "Manual EXP", "The % must be between 0 and 100.")
                return
        self.module.add_manual(int(digits), pct)
        self.manual.clear()

    def show_stats(self, s: Stats) -> None:
        cur = "-"
        if s.current_exp is not None:
            cur = fmt.big_number(s.current_exp)
            if s.current_pct is not None:
                cur += f" ({fmt.percent(s.current_pct)})"
        g = self.grid
        g.set("rate", fmt.big_number(s.exp_per_hour) if s.exp_per_hour else "-")
        g.set("recent", fmt.big_number(s.recent_exp_per_hour) if s.recent_exp_per_hour else "-")
        g.set("pct_rate", fmt.percent(s.pct_per_hour, 2))
        g.set("eta", fmt.eta(s.eta_seconds))
        g.set("gained", fmt.big_number(s.gained))
        g.set("pct_gained", fmt.percent(s.pct_gained, 2))
        g.set("levels", str(s.levels))
        g.set("current", cur)
