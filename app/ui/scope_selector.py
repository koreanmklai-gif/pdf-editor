"""Reusable page-scope selector and scope resolver used by the tool dialogs."""

from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


def resolve_scope(
    scope: str,
    page_count: int,
    selection: Sequence[int],
) -> Optional[List[int]]:
    """Turn a scope keyword into 0-based page indices.

    ``scope`` is one of ``"all"``, ``"odd"``, ``"even"`` or ``"selected"``.
    ``selection`` is the current thumbnail selection (0-based).
    Returns ``None`` for an unknown scope keyword.
    """
    if scope == "all":
        return list(range(page_count))
    if scope == "odd":
        return list(range(0, page_count, 2))
    if scope == "even":
        return list(range(1, page_count, 2))
    if scope == "selected":
        return sorted({int(i) for i in selection if 0 <= i < page_count})
    return None


class PageScopeSelector(QGroupBox):
    """Radio group choosing which pages an operation applies to.

    Emits :attr:`scope_changed` whenever the active radio changes; the value is
    one of ``"selected"``, ``"all"``, ``"odd"`` or ``"even"``.
    """

    scope_changed = Signal(str)

    def __init__(
        self,
        title: str = "Apply to",
        parent: Optional[QWidget] = None,
        *,
        selection_count: int = 0,
    ) -> None:
        super().__init__(title, parent)
        layout = QVBoxLayout(self)
        self._group = QButtonGroup(self)
        self.rb_all = QRadioButton("All pages")
        self.rb_odd = QRadioButton("Odd pages (1, 3, 5…)")
        self.rb_even = QRadioButton("Even pages (2, 4, 6…)")
        self.rb_sel = QRadioButton(
            f"Selected pages ({selection_count} selected)"
            if selection_count > 0
            else "Selected pages (none selected)"
        )
        if selection_count <= 0:
            self.rb_sel.setEnabled(False)
        for rb in (self.rb_all, self.rb_odd, self.rb_even, self.rb_sel):
            self._group.addButton(rb)
            layout.addWidget(rb)
        if selection_count > 0:
            self.rb_sel.setChecked(True)
        else:
            self.rb_all.setChecked(True)
        self._group.buttonToggled.connect(self._on_button_toggled)

    def _on_button_toggled(self, _button: QRadioButton, _checked: bool) -> None:
        self.scope_changed.emit(self.scope())

    def set_selection_count(self, count: int) -> None:
        """Update the Selected-pages radio label and enable/disable it."""
        self.rb_sel.setText(
            f"Selected pages ({count} selected)"
            if count > 0
            else "Selected pages (none selected)"
        )
        self.rb_sel.setEnabled(count > 0)
        if not self.rb_sel.isEnabled() and self.rb_sel.isChecked():
            self.rb_all.setChecked(True)

    def scope(self) -> str:
        if self.rb_odd.isChecked():
            return "odd"
        if self.rb_even.isChecked():
            return "even"
        if self.rb_sel.isChecked():
            return "selected"
        return "all"