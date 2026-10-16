"""Potions panel on the Live tab: repot estimate, plus a row per potion quickslot."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGroupBox, QHeaderView, QLabel, QMessageBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from statisticbuddy.core import fmt
from statisticbuddy.modules.potions import KINDS

COLUMNS = ["Name", "Type", "Price each", "Start", "Have", "Used", "Cost", "Use / hour", "Runs out in"]
COL_NAME, COL_KIND, COL_PRICE = 0, 1, 2


class PotionPanel(QWidget):
    def __init__(self, module):
        super().__init__()
        self.module = module
        self._filling = False
        self._keys: list[str] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Potions")
        outer.addWidget(box)
        layout = QVBoxLayout(box)

        self.repot = QLabel()
        f = self.repot.font()
        f.setPointSize(12)
        f.setBold(True)
        self.repot.setFont(f)
        layout.addWidget(self.repot)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._edited)
        layout.addWidget(self.table)

        self.hint = QLabel()
        self.hint.setStyleSheet("color: gray")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.show_rows()

    def show_rows(self) -> None:
        m = self.module
        keys = m.active_slots()
        self._show_repot()
        if not keys:
            self.table.hide()
            self.hint.setText("Select your potion quickslot keys on the Regions tab "
                              "(\"Potion quickslot 1\" to 4) to track potion use and repot time.")
            return
        self.table.show()
        self.hint.setText("Double-click a name or price to edit it. Price = what you pay per potion at the shop.")
        if self.table.state() == QAbstractItemView.EditingState:
            return

        self._filling = True
        if keys != self._keys:
            self.table.setRowCount(len(keys))
            for r, key in enumerate(keys):
                combo = QComboBox()
                combo.addItems(KINDS)
                combo.currentTextChanged.connect(lambda kind, k=key: self._kind_changed(k, kind))
                self.table.setCellWidget(r, COL_KIND, combo)
            self._keys = keys
        t = m.tracker
        for r, key in enumerate(keys):
            info = m.slot_info(key)
            have = t.current(key)
            used = t.used.get(key, 0)
            rate = t.rate_per_hour(key)
            eta = t.runs_out_in([key])
            start = t.start_count(key)
            cells = {
                COL_NAME: info["name"],
                COL_PRICE: f"{float(info['price']):,.0f}",
                3: "-" if start is None else f"{start:,}",
                4: "-" if have is None else f"{have:,}",
                5: f"{used:,}",
                6: fmt.big_number(used * float(info["price"])),
                7: "-" if rate is None else f"{rate:,.0f}",
                8: fmt.eta(eta),
            }
            for c, text in cells.items():
                item = self.table.item(r, c)
                if item is None:
                    item = QTableWidgetItem()
                    item.setData(Qt.UserRole, key)
                    if c not in (COL_NAME, COL_PRICE):
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if c >= COL_PRICE:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table.setItem(r, c, item)
                if item.text() != text:
                    item.setText(text)
            combo = self.table.cellWidget(r, COL_KIND)
            if combo.currentText() != info["kind"]:
                combo.blockSignals(True)
                combo.setCurrentText(info["kind"])
                combo.blockSignals(False)
        self._filling = False

    def _show_repot(self) -> None:
        etas = self.module.repot_eta()
        known = {k: v for k, v in etas.items() if v is not None}
        if not known:
            self.repot.setText("Repot: estimate appears after a few minutes of potion use"
                               if etas else "Repot: no HP/MP potion keys set")
            self.repot.setStyleSheet("")
            return
        kind, soonest = min(known.items(), key=lambda kv: kv[1])
        parts = "  ·  ".join(f"{k} in ~{fmt.eta(v)}" for k, v in known.items())
        self.repot.setText(f"Repot: {parts}")
        if soonest < 5 * 60:
            self.repot.setStyleSheet("color: #c0392b")
        elif soonest < 15 * 60:
            self.repot.setStyleSheet("color: #d68910")
        else:
            self.repot.setStyleSheet("color: #2e8b57")

    def _kind_changed(self, key: str, kind: str) -> None:
        self.module.update_slot(key, kind=kind)
        self._show_repot()

    def _edited(self, item: QTableWidgetItem) -> None:
        if self._filling:
            return
        key = item.data(Qt.UserRole)
        if item.column() == COL_NAME and item.text().strip():
            self.module.update_slot(key, name=item.text().strip())
        elif item.column() == COL_PRICE:
            try:
                price = float(item.text().replace(",", "").strip() or 0)
            except ValueError:
                QMessageBox.warning(self, "Potion price", "Enter the price per potion as a number, e.g. 50.")
                return
            if price >= 0:
                self.module.update_slot(key, price=price)
        self.show_rows()
