"""Past sessions, with columns contributed by each tracker module."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from mapletracker.core import fmt, session
from mapletracker.core.module import AppContext, TrackerModule

BASE_COLUMNS = ["Started", "Character", "Active time"]


class HistoryTab(QWidget):
    def __init__(self, ctx: AppContext, modules: list[TrackerModule]):
        super().__init__()
        self.ctx, self.modules = ctx, modules
        headers = BASE_COLUMNS + [h for m in modules for h in m.history_headers]
        root = QVBoxLayout(self)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        root.addWidget(self.table)

        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self._delete)
        buttons.addStretch(1)
        buttons.addWidget(refresh)
        buttons.addWidget(delete)
        root.addLayout(buttons)
        self.refresh()

    def showEvent(self, e) -> None:
        self.refresh()
        super().showEvent(e)

    def refresh(self) -> None:
        rows = session.list_sessions(self.ctx.db)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cells = [
                time.strftime("%Y-%m-%d %H:%M", time.localtime(r["started_at"])),
                r["character"] or "-",
                fmt.duration(r["active_seconds"]),
            ]
            for m in self.modules:
                cells += m.history_values(self.ctx.db, r["id"])
            for j, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if j >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setData(Qt.UserRole, r["id"])
                self.table.setItem(i, j, item)

    def _delete(self) -> None:
        ids = {self.table.item(idx.row(), 0).data(Qt.UserRole)
               for idx in self.table.selectionModel().selectedRows()}
        current = self.ctx.session.session_id if self.ctx.session else None
        ids.discard(current)
        if not ids:
            return
        if QMessageBox.question(self, "Delete sessions",
                                f"Delete {len(ids)} session(s) and their readings?") != QMessageBox.Yes:
            return
        for sid in ids:
            session.delete_session(self.ctx.db, sid)
        self.refresh()
