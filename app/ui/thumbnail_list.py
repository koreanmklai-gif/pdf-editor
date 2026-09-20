"""Thumbnail strip with multi-select and drag-drop reorder.

Rendering is lazy: :meth:`set_placeholder_pages` fills the widget with cheap
shared-placeholder items, and :meth:`set_thumbnail` swaps in real renderings
in place. The owner schedules fills via the :attr:`visible_range_changed`
signal so only rows the user can see (plus lookahead) are ever rendered.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPoint, Qt, Signal, QSize
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QWidget,
)

PLACEHOLDER_SIZE = (100, 140)
PLACEHOLDER_COLOR = QColor("#3f3f3f")


class ThumbnailList(QListWidget):
    """Horizontal or vertical thumbnail list with shift/ctrl selection + DnD."""

    selection_changed_custom = Signal(list)  # list[int]
    pages_reordered = Signal(list)  # new order as list[int] of old indices
    page_activated = Signal(int)
    visible_range_changed = Signal()  # scroll/resize; owner should schedule fills

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.TopToBottom)
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
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMinimumWidth(168)
        self.setMaximumWidth(240)

        self.itemSelectionChanged.connect(self._emit_selection)
        self.itemDoubleClicked.connect(self._on_double_click)

        self._drag_start_indices: List[int] = []
        self._placeholder: Optional[QIcon] = None

    # ------------------------------------------------------------------
    # Lazy thumbnail population
    # ------------------------------------------------------------------

    def placeholder_icon(self) -> QIcon:
        """A single shared placeholder icon for all unfilled rows."""
        if self._placeholder is None:
            pix = QPixmap(*PLACEHOLDER_SIZE)
            pix.fill(PLACEHOLDER_COLOR)
            self._placeholder = QIcon(pix)
        return self._placeholder

    def set_placeholder_pages(self, count: int) -> None:
        """Populate the list with ``count`` placeholder rows (cheap).

        Real thumbnails are swapped in later via :meth:`set_thumbnail`.
        """
        icon = self.placeholder_icon()
        self.blockSignals(True)
        self.clear()
        for i in range(count):
            item = QListWidgetItem(icon, f"{i + 1}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSizeHint(QSize(110, 160))
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
            )
            self.addItem(item)
        self.blockSignals(False)
        self._emit_selection()
        self._emit_visible()

    def set_thumbnail(self, index: int, pixmap: QPixmap) -> None:
        """Swap the real thumbnail into row ``index`` without rebuilding the list."""
        if 0 <= index < self.count():
            self.item(index).setIcon(QIcon(pixmap))

    def visible_range(self) -> Tuple[int, int]:
        """First and last (inclusive) row indices currently in the viewport.

        Samples the item column down the viewport (their left edge is
        indented by the frame margin, so hits happen at the column center).
        """
        n = self.count()
        if n == 0:
            return (0, 0)
        vp = self.viewport()
        if vp is None or vp.width() < 4 or vp.height() < 4:
            return (0, 0)
        x = vp.width() // 2
        seen: List[int] = []
        step = 40
        for y in range(2, vp.height(), step):
            idx = self.indexAt(QPoint(x, y))
            if idx.isValid():
                seen.append(idx.row())
        idx = self.indexAt(QPoint(x, vp.height() - 2))
        if idx.isValid():
            seen.append(idx.row())
        if not seen:
            return (0, 0)
        return (min(seen), max(seen))

    def _emit_visible(self) -> None:
        self.visible_range_changed.emit()

    def clear_thumbnails(self) -> None:
        self.clear()

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

    # ---- Scroll / resize → visible rows changed ----

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        super().scrollContentsBy(dx, dy)
        self._emit_visible()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._emit_visible()

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
