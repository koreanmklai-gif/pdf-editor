"""Delete Pages dialog: choose which pages to remove."""

from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui.scope_selector import PageScopeSelector, resolve_scope

# How many page numbers to show inline before truncating the list.
PREVIEW_LIMIT = 20


class DeleteDialog(QDialog):
    """Confirm deletion with a page-scope selector (defaults to the selection)."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        page_count: int,
        selection: Sequence[int] = (),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Delete Pages")
        self.setModal(True)
        self.setMinimumWidth(390)
        self._page_count = page_count
        self._selection = sorted(
            {int(i) for i in selection if 0 <= i < page_count}
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            f"This document has {page_count} pages. Choose which pages to "
            "delete; at least one page must remain."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.scope = PageScopeSelector(selection_count=len(self._selection))
        self.scope.scope_changed.connect(self._update_preview)
        layout.addWidget(self.scope)

        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.preview_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Delete")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_preview()

    def _update_preview(self) -> None:
        pages = self.target_pages()
        if not pages:
            self.preview_label.setText("No pages selected.")
            return
        nums = [str(i + 1) for i in pages]
        text = ", ".join(nums[:PREVIEW_LIMIT])
        if len(nums) > PREVIEW_LIMIT:
            text += f", … (+{len(nums) - PREVIEW_LIMIT} more)"
        self.preview_label.setText(f"Pages to delete: {text}")

    def target_pages(self) -> List[int]:
        pages = resolve_scope(self.scope.scope(), self._page_count, self._selection)
        return pages or []