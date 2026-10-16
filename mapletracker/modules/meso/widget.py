"""Mesos panel on the Live tab."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from mapletracker.core import fmt
from mapletracker.modules.meso.tracker import MesoStats
from mapletracker.ui.widgets import ManualRow, StatGrid

ROWS = [
    ("rate", "Mesos / hour"),
    ("recent", "Last 10 min pace"),
    ("gained", "Mesos gained"),
    ("spent", "Mesos spent"),
    ("net", "Net change"),
    ("current", "Current mesos"),
]


class MesoPanel(QWidget):
    def __init__(self, module):
        super().__init__()
        self.module = module
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.grid = StatGrid("Mesos", ROWS)
        self.manual = ManualRow(["Current mesos, e.g. 1,234,567"], self._submit)
        self.grid.add_row_widget(self.manual)
        layout.addWidget(self.grid)

    def _submit(self) -> None:
        digits = "".join(ch for ch in self.manual.values()[0] if ch.isdigit())
        if not digits:
            QMessageBox.warning(self, "Manual mesos", "Enter your current meso total.")
            return
        self.module.add_manual(int(digits))
        self.manual.clear()

    def show_stats(self, s: MesoStats) -> None:
        g = self.grid
        g.set("rate", fmt.big_number(s.per_hour) if s.per_hour else "-")
        g.set("recent", fmt.big_number(s.recent_per_hour) if s.recent_per_hour else "-")
        g.set("gained", fmt.big_number(s.gained))
        g.set("spent", fmt.big_number(s.spent))
        g.set("net", ("+" if (s.net or 0) > 0 else "") + fmt.big_number(s.net) if s.net is not None else "-")
        g.set("current", fmt.big_number(s.current))
