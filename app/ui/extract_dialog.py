"""Extract Pages dialog: choose which pages to export and a destination file."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.scope_selector import PageScopeSelector, resolve_scope


class ExtractDialog(QDialog):
    """Export a subset of pages to a new PDF (the current document is kept)."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        page_count: int,
        selection: Sequence[int] = (),
        default_path: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Extract Pages")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._page_count = page_count
        self._selection = sorted(
            {int(i) for i in selection if 0 <= i < page_count}
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.scope = PageScopeSelector(selection_count=len(self._selection))
        layout.addWidget(self.scope)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Save to:"))
        self.dest_edit = QLineEdit(str(default_path or "extracted.pdf"))
        dest_row.addWidget(self.dest_edit, stretch=1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        dest_row.addWidget(browse)
        layout.addLayout(dest_row)

        hint = QLabel(
            "The selected pages are exported to a new PDF; the current "
            "document is left unchanged."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Extract")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Extracted Pages",
            self.dest_edit.text(),
            "PDF Files (*.pdf)",
        )
        if path:
            self.dest_edit.setText(path)

    def target_pages(self) -> List[int]:
        pages = resolve_scope(self.scope.scope(), self._page_count, self._selection)
        return pages or []

    def destination(self) -> Path:
        path = Path(self.dest_edit.text().strip() or "extracted.pdf")
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        return path