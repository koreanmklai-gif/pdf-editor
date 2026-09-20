"""Reorder Pages dialog: arrange the page order with move buttons."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ReorderDialog(QDialog):
    """Reorder the list of pages; the new page order is read via new_order()."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        page_count: int,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reorder Pages")
        self.setModal(True)
        self.setMinimumWidth(360)
        self._page_count = page_count

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        label = QLabel(
            "Select pages and use the buttons to move them, or drag thumbnails "
            "in the sidebar. The order shown here is the new document order."
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        for i in range(page_count):
            item = QListWidgetItem(f"Page {i + 1}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget, stretch=1)

        btn_row = QHBoxLayout()
        up = QPushButton("Move Up ▲")
        down = QPushButton("Move Down ▼")
        reverse = QPushButton("Reverse Order")
        up.clicked.connect(self._move_up)
        down.clicked.connect(self._move_down)
        reverse.clicked.connect(self._reverse)
        btn_row.addWidget(up)
        btn_row.addWidget(down)
        btn_row.addStretch(1)
        btn_row.addWidget(reverse)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Reordering helpers
    # ------------------------------------------------------------------

    def _selected_values(self) -> List[int]:
        """Old page indices currently selected in the list."""
        return sorted(
            int(item.data(Qt.ItemDataRole.UserRole))
            for item in self.list_widget.selectedItems()
        )

    def _set_order(
        self,
        order: List[int],
        *,
        select: Optional[List[int]] = None,
    ) -> None:
        select = select or []
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for old in order:
            item = QListWidgetItem(f"Page {old + 1}")
            item.setData(Qt.ItemDataRole.UserRole, old)
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)
        for i, old in enumerate(order):
            if old in select:
                self.list_widget.item(i).setSelected(True)

    def _move_up(self) -> None:
        order = self._order()
        sel = self._selected_values()
        for old in sorted(sel):
            i = order.index(old)
            if i == 0 or order[i - 1] in sel:
                continue
            order[i - 1], order[i] = order[i], order[i - 1]
        self._set_order(order, select=sel)

    def _move_down(self) -> None:
        order = self._order()
        sel = self._selected_values()
        for old in sorted(sel, reverse=True):
            i = order.index(old)
            if i >= len(order) - 1 or order[i + 1] in sel:
                continue
            order[i], order[i + 1] = order[i + 1], order[i]
        self._set_order(order, select=sel)

    def _reverse(self) -> None:
        order = self._order()[::-1]
        self._set_order(order, select=self._selected_values())

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def _order(self) -> List[int]:
        return [
            int(self.list_widget.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self.list_widget.count())
        ]

    def new_order(self) -> List[int]:
        """The arrangement where position k holds old page index order[k]."""
        return self._order()