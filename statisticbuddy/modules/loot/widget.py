"""Loot panel on the Live tab: grid size, and a table of items with editable name and NPC price."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from statisticbuddy.core import fmt

COLUMNS = ["", "Item", "NPC price", "Start", "Have", "Held value", "This session", "Session value"]
COL_NAME, COL_PRICE = 1, 2


class LootPanel(QWidget):
    def __init__(self, module):
        super().__init__()
        self.module = module
        self._filling = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Loot (ETC tab)")
        layout = QVBoxLayout(box)
        outer.addWidget(box)

        top = QHBoxLayout()
        cols, rows = module.grid_size
        top.addWidget(QLabel("Grid"))
        self.cols = QSpinBox()
        self.cols.setRange(1, 12)
        self.cols.setValue(cols)
        self.cols.setSuffix(" columns")
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 12)
        self.rows_spin.setValue(rows)
        self.rows_spin.setSuffix(" rows")
        for s in (self.cols, self.rows_spin):
            s.valueChanged.connect(lambda _: module.set_grid_size(self.cols.value(), self.rows_spin.value()))
            top.addWidget(s)
        top.addStretch(1)
        self.total = QLabel()
        f = self.total.font()
        f.setBold(True)
        f.setPointSize(11)
        self.total.setFont(f)
        top.addWidget(self.total)
        layout.addLayout(top)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setIconSize(QSize(28, 28))
        self.table.setMinimumHeight(180)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._edited)
        layout.addWidget(self.table)

        self.last_read = QLabel()
        self.last_read.setStyleSheet("color: gray")
        layout.addWidget(self.last_read)

        bottom = QHBoxLayout()
        hint = QLabel("New items appear automatically. Double-click a name or price to edit it.")
        hint.setStyleSheet("color: gray")
        forget = QPushButton("Forget selected item")
        forget.clicked.connect(self._forget)
        bottom.addWidget(hint, 1)
        bottom.addWidget(forget)
        layout.addLayout(bottom)
        self.update_items()

    def update_items(self) -> None:
        self.last_read.setText(self.module.last_read)
        if self.table.state() == QAbstractItemView.EditingState:
            return  # don't disturb an edit in progress; the next read refreshes it
        self._filling = True
        rows = self.module.rows()
        self.table.setRowCount(len(rows))
        for r, (item_id, info, start, have, held, change, value) in enumerate(rows):
            icon = QTableWidgetItem()
            if info.get("png"):
                pix = QPixmap()
                pix.loadFromData(info["png"])
                icon.setIcon(QIcon(pix))
            cells = [
                icon,
                QTableWidgetItem(info["name"]),
                QTableWidgetItem(f"{info['price']:,.0f}"),
                QTableWidgetItem("-" if start is None else f"{start:,}"),
                QTableWidgetItem("-" if have is None else f"{have:,}"),
                QTableWidgetItem(fmt.big_number(held) if held else "0"),
                QTableWidgetItem(f"{change:+,}" if change else "0"),
                QTableWidgetItem(fmt.signed(value) if value else "0"),
            ]
            for c, cell in enumerate(cells):
                cell.setData(Qt.UserRole, item_id)
                if c not in (COL_NAME, COL_PRICE):
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if c >= COL_PRICE:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, cell)
        self._filling = False
        session = self.module.total_value()
        self.total.setText(f"ETC held: {fmt.big_number(self.module.held_value())}"
                           f"  ·  This session: {fmt.signed(session) if session else '0'}")

    def _edited(self, cell: QTableWidgetItem) -> None:
        if self._filling:
            return
        item_id = cell.data(Qt.UserRole)
        if cell.column() == COL_NAME:
            name = cell.text().strip()
            if name:
                self.module.rename(item_id, name)
        elif cell.column() == COL_PRICE:
            try:
                price = float(cell.text().replace(",", "").strip() or 0)
            except ValueError:
                QMessageBox.warning(self, "NPC price", "Enter the NPC sell price as a number, e.g. 25.")
                price = None
            if price is not None and price >= 0:
                self.module.set_price(item_id, price)
        self.update_items()

    def _forget(self) -> None:
        rows = {i.row() for i in self.table.selectedItems()}
        if not rows:
            return
        item_id = self.table.item(next(iter(rows)), 0).data(Qt.UserRole)
        name = self.module.items[item_id]["name"]
        if QMessageBox.question(self, "Forget item",
                                f"Forget \"{name}\"? Its name and price are removed; it'll be "
                                "re-detected as a new item if it shows up again.") == QMessageBox.Yes:
            self.module.forget(item_id)
            self.update_items()
