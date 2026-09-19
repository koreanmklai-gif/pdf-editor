"""Thumbnail strip with multi-select and drag-drop reorder."""

from __future__ import annotations

from typing import List, Optional, Set

from PySide6.QtCore import Qt, Signal, QSize, QMimeData, QByteArray
from PySide6.QtGui import QPixmap, QIcon, QDrag, QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QWidget,
)


MIME_TYPE = "application/x-pdf-editor-pages"


class ThumbnailList(QListWidget):
    """Horizontal or vertical thumbnail list with shift/ctrl selection + DnD."""

    selection_changed_custom = Signal(list)  # list[int]
    pages_reordered = Signal(list)  # new order as list[int] of old indices
    page_activated = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListWidget.Movement.Snap)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setIconSize(QSize(100, 140))
        self.setSpacing(8)
        self.setUniformItemSizes(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMaximumHeight(190)
        self.setMinimumHeight(160)

        self.itemSelectionChanged.connect(self._emit_selection)
        self.itemDoubleClicked.connect(self._on_double_click)

        self._drag_start_indices: List[int] = []

    def clear_thumbnails(self) -> None:
        self.clear()

    def set_thumbnails(self, pixmaps: List[QPixmap], labels: Optional[List[str]] = None) -> None:
        self.clear()
        for i, pix in enumerate(pixmaps):
            label = labels[i] if labels else f"{i + 1}"
            item = QListWidgetItem(QIcon(pix), label)
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSizeHint(QSize(110, 160))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self.addItem(item)

    def selected_indices(self) -> List[int]:
        rows = sorted({self.row(i) for i in self.selectedItems()})
        return rows

    def set_selected_indices(self, indices: List[int]) -> None:
        self.blockSignals(True)
        self.clearSelection()
        for i in indices:
            if 0 <= i < self.count():
                self.item(i).setSelected(True)
        self.blockSignals(False)
        self._emit_selection()

    def current_index(self) -> int:
        return self.currentRow()

    def _emit_selection(self) -> None:
        self.selection_changed_custom.emit(self.selected_indices())

    def _on_double_click(self, item: QListWidgetItem) -> None:
        self.page_activated.emit(self.row(item))

    # ---- Drag & drop reorder ----

    def startDrag(self, supportedActions) -> None:  # noqa: N802
        self._drag_start_indices = self.selected_indices()
        super().startDrag(supportedActions)

    def dropEvent(self, event) -> None:  # noqa: N802
        if event.source() is not self:
            event.ignore()
            return
        # Capture order before drop
        before = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        super().dropEvent(event)
        # After InternalMove, rebuild UserRole to match visual order and emit
        new_order: List[int] = []
        for i in range(self.count()):
            item = self.item(i)
            old_idx = item.data(Qt.ItemDataRole.UserRole)
            new_order.append(int(old_idx))
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setText(str(i + 1))
        if new_order != list(range(len(new_order))):
            # new_order[k] = old page index now at position k
            self.pages_reordered.emit(new_order)
