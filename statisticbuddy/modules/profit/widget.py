"""Profit panel on the Live tab."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from statisticbuddy.core import fmt


class ProfitPanel(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Profit")
        outer.addWidget(box)
        layout = QVBoxLayout(box)
        self.parts = QGridLayout()
        layout.addLayout(self.parts)
        self.verdict = QLabel()
        f = self.verdict.font()
        f.setPointSize(13)
        f.setBold(True)
        self.verdict.setFont(f)
        layout.addWidget(self.verdict)
        self.worth = QLabel()
        self.worth.setWordWrap(True)
        self.worth.setToolTip("Everything you hold, at the prices you entered (last known counts). "
                              "Profit above only counts what changed this session.")
        layout.addWidget(self.worth)
        self._shown: list[tuple[str, str]] = []

    def show_profit(self, parts: list[tuple[str, float]], total: float, rate: float | None,
                    holdings: list[tuple[str, float]] = ()) -> None:
        if holdings:
            items = " + ".join(f"{label} {fmt.big_number(v)}" for label, v in holdings)
            self.worth.setText(f"Net worth: <b>{fmt.big_number(sum(v for _, v in holdings))}</b>"
                               f"  <span style='color:gray'>({items})</span>")
        else:
            self.worth.setText("<span style='color:gray'>Net worth appears after the first read.</span>")

        rows = [(label, fmt.signed(v) if v else "0") for label, v in parts]
        if rows != self._shown:
            while self.parts.count():
                self.parts.takeAt(0).widget().deleteLater()
            for i, (label, value) in enumerate(rows):
                v = QLabel(value)
                v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.parts.addWidget(QLabel(label), i, 0)
                self.parts.addWidget(v, i, 1)
            self._shown = rows

        if not parts:
            self.verdict.setText("Start a session to see profit.")
            self.verdict.setStyleSheet("")
            return
        per_hour = f"  ({fmt.signed(rate)} / hour)" if rate is not None else "  (rate after 1 min)"
        if total > 0:
            mark, color = "✅ Meso-positive", "#2e8b57"
        elif total < 0:
            mark, color = "❌ Losing mesos", "#c0392b"
        else:
            mark, color = "➖ Breaking even", ""
        self.verdict.setText(f"{mark}: {fmt.signed(total) if total else '0'}{per_hour}")
        self.verdict.setStyleSheet(f"color: {color}" if color else "")
