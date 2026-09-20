"""Merge PDF dialog: choose a source PDF and where to insert its pages."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
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


class MergeDialog(QDialog):
    """Pick a PDF to merge into the current document, plus an insert position."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        page_count: int,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Merge PDF")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._page_count = page_count

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("PDF to merge:"))
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("Choose a PDF file…")
        src_row.addWidget(self.src_edit, stretch=1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        src_row.addWidget(browse)
        layout.addLayout(src_row)

        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("Insert at:"))
        self.position = QComboBox()
        self.position.addItem("Append to end")
        for i in range(page_count):
            self.position.addItem(f"Before page {i + 1}")
        pos_row.addWidget(self.position, stretch=1)
        layout.addLayout(pos_row)

        hint = QLabel(
            "All pages of the chosen PDF are inserted at the selected position."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Merge")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a PDF to merge",
            "",
            "PDF Files (*.pdf);;All Files (*)",
        )
        if path:
            self.src_edit.setText(path)

    def source_path(self) -> str:
        return self.src_edit.text().strip()

    def insert_at(self) -> Optional[int]:
        """Return the 0-based insert position, or None to append at the end."""
        if self.position.currentIndex() == 0:
            return None
        return self.position.currentIndex() - 1