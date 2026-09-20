"""Rotate Pages dialog: choose an angle and which pages to rotate."""

from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.scope_selector import PageScopeSelector, resolve_scope


class RotateDialog(QDialog):
    """Pick a rotation angle and a page scope to apply it to."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        page_count: int,
        selection: Sequence[int] = (),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rotate Pages")
        self.setModal(True)
        self.setMinimumWidth(380)
        self._page_count = page_count
        self._selection = sorted(
            {int(i) for i in selection if 0 <= i < page_count}
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        angle_box = QGroupBox("Rotation")
        angle_layout = QVBoxLayout(angle_box)
        self.angle_group = QButtonGroup(self)
        self.rb_cw = QRadioButton("Clockwise 90°")
        self.rb_ccw = QRadioButton("Counterclockwise 90°")
        self.rb_180 = QRadioButton("Rotate 180°")
        self.rb_cw.setChecked(True)
        for rb in (self.rb_cw, self.rb_ccw, self.rb_180):
            self.angle_group.addButton(rb)
            angle_layout.addWidget(rb)
        layout.addWidget(angle_box)

        self.scope = PageScopeSelector(selection_count=len(self._selection))
        layout.addWidget(self.scope)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Rotate")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def angle(self) -> int:
        if self.rb_ccw.isChecked():
            return -90
        if self.rb_180.isChecked():
            return 180
        return 90

    def target_pages(self) -> List[int]:
        pages = resolve_scope(self.scope.scope(), self._page_count, self._selection)
        return pages or []