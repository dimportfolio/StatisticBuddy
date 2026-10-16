"""Small widgets shared by tracker panels."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget


class StatGrid(QGroupBox):
    """Title/value pairs laid out in two columns."""

    def __init__(self, title: str, rows: list[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(title, parent)
        grid = QGridLayout(self)
        big = QFont()
        big.setPointSize(12)
        big.setBold(True)
        self._values: dict[str, QLabel] = {}
        for i, (key, label) in enumerate(rows):
            value = QLabel("-")
            value.setFont(big)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row, col = divmod(i, 2)
            grid.addWidget(QLabel(label), row, col * 2)
            grid.addWidget(value, row, col * 2 + 1)
            self._values[key] = value
        self._layout = grid

    def set(self, key: str, text: str) -> None:
        self._values[key].setText(text)

    def add_row_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget, self._layout.rowCount(), 0, 1, 4)


class ManualRow(QWidget):
    """'Type a value' row used as a backup to OCR."""

    def __init__(self, placeholders: list[str], on_submit, parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Manual:"))
        self.fields: list[QLineEdit] = []
        for i, text in enumerate(placeholders):
            f = QLineEdit()
            f.setPlaceholderText(text)
            f.returnPressed.connect(on_submit)
            row.addWidget(f, 2 if i == 0 else 1)
            self.fields.append(f)
        add = QPushButton("Add")
        add.clicked.connect(on_submit)
        row.addWidget(add)

    def values(self) -> list[str]:
        return [f.text().strip() for f in self.fields]

    def clear(self) -> None:
        for f in self.fields:
            f.clear()
