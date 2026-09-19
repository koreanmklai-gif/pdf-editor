"""Crop margins dialog (Traditional Chinese UI)."""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.services.pdf_service import CropBox


class CropDialog(QDialog):
    """Ask user for crop margins in PDF points."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        page_width: float = 595.0,
        page_height: float = 842.0,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("裁剪頁面")
        self.setModal(True)
        self._page_width = page_width
        self._page_height = page_height

        layout = QVBoxLayout(self)
        hint = QLabel(
            "輸入四邊要裁去的邊界（單位：點 / pt，1 吋 = 72 pt）。\n"
            f"目前頁面大約：{page_width:.0f} × {page_height:.0f} pt"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.left = self._spin()
        self.top = self._spin()
        self.right = self._spin()
        self.bottom = self._spin()
        form.addRow("左邊距 (Left)：", self.left)
        form.addRow("上邊距 (Top)：", self.top)
        form.addRow("右邊距 (Right)：", self.right)
        form.addRow("下邊距 (Bottom)：", self.bottom)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("套用")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _spin(self) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(0.0, 5000.0)
        sp.setDecimals(1)
        sp.setSingleStep(5.0)
        sp.setValue(0.0)
        sp.setSuffix(" pt")
        return sp

    def crop_box(self) -> CropBox:
        return CropBox(
            left=self.left.value(),
            top=self.top.value(),
            right=self.right.value(),
            bottom=self.bottom.value(),
        )
