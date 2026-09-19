"""Crop margins dialog (Traditional Chinese UI).

Shows a live preview of the page with the crop region drawn on it. The region
can be adjusted by dragging the edges/corners of the overlay, or by editing the
four margin spinboxes — both stay in sync.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.services.pdf_service import CropBox

# Minimum kept region (pt) enforced while dragging, so the page can't be
# collapsed to nothing.
KEEP_MIN = 5.0
EDGE_TOL = 8  # px hit tolerance around an edge/corner


class CropPreview(QWidget):
    """Page preview with a live, drag-adjustable crop-region overlay."""

    margins_changed = Signal(float, float, float, float)  # left, top, right, bottom

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 240)
        self.setMouseTracking(True)
        self._pixmap = QPixmap()
        self._page_w_pt = 595.0
        self._page_h_pt = 842.0
        self._margins = (0.0, 0.0, 0.0, 0.0)  # (left, top, right, bottom)
        self._drag_edge: Optional[str] = None
        self._last_x = 0.0
        self._last_y = 0.0
        self._ppw = 1.0  # pixels per pt (x)
        self._pph = 1.0  # pixels per pt (y)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_page(self, pixmap: QPixmap, width_pt: float, height_pt: float) -> None:
        self._pixmap = pixmap
        self._page_w_pt = width_pt
        self._page_h_pt = height_pt
        self.update()

    def set_margins(self, left: float, top: float, right: float, bottom: float) -> None:
        self._margins = (left, top, right, bottom)
        self.update()

    def margins(self) -> tuple[float, float, float, float]:
        return self._margins

    # ------------------------------------------------------------------
    # Geometry: where the page is drawn, and the keep-rect in pixels
    # ------------------------------------------------------------------

    def _target_rect(self) -> QRect:
        if self._pixmap.isNull() or self._pixmap.height() <= 0:
            return QRect()
        avail = self.rect().adjusted(10, 10, -10, -10)
        ratio = self._pixmap.width() / self._pixmap.height()
        w = avail.width()
        h = int(w / ratio)
        if h > avail.height():
            h = avail.height()
            w = int(h * ratio)
        x = avail.x() + (avail.width() - w) // 2
        y = avail.y() + (avail.height() - h) // 2
        return QRect(x, y, w, h)

    def _update_scale(self, target: QRect) -> None:
        if self._page_w_pt > 0 and target.width() > 0:
            self._ppw = target.width() / self._page_w_pt
        if self._page_h_pt > 0 and target.height() > 0:
            self._pph = target.height() / self._page_h_pt

    def _keep_rect(self, target: QRect) -> QRect:
        l, t, r, b = self._margins
        x0 = int(target.left() + l * self._ppw)
        y0 = int(target.top() + t * self._pph)
        x1 = int(target.right() - r * self._ppw)
        y1 = int(target.bottom() - b * self._pph)
        if x1 < x0 or y1 < y0:
            return QRect()
        return QRect(x0, y0, x1 - x0, y1 - y0)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(45, 45, 45))

        if self._pixmap.isNull():
            p.setPen(QColor(180, 180, 180))
            p.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "（無法取得頁面預覽）",
            )
            return

        target = self._target_rect()
        self._update_scale(target)
        p.drawPixmap(target, self._pixmap)

        keep = self._keep_rect(target)
        if keep.isNull():
            return

        overlay = QColor(0, 0, 0, 150)
        # Four bands covering the margins that will be cut away.
        bands = [
            (  # top
                target.left(),
                target.top(),
                target.width(),
                keep.top() - target.top(),
            ),
            (  # bottom
                target.left(),
                keep.bottom(),
                target.width(),
                target.bottom() - keep.bottom() + 1,
            ),
            (  # left
                target.left(),
                keep.top(),
                keep.left() - target.left(),
                keep.height(),
            ),
            (  # right
                keep.right(),
                keep.top(),
                target.right() - keep.right() + 1,
                keep.height(),
            ),
        ]
        for x, y, w, h in bands:
            if w > 0 and h > 0:
                p.fillRect(x, y, w, h, overlay)

        p.setPen(QPen(QColor("#3d7eff"), 2))
        p.drawRect(keep)

        # Corner handles
        p.setBrush(QColor("#3d7eff"))
        for cx, cy in (
            (keep.left(), keep.top()),
            (keep.right(), keep.top()),
            (keep.left(), keep.bottom()),
            (keep.right(), keep.bottom()),
        ):
            p.drawRect(cx - 4, cy - 4, 8, 8)

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def _edge_at(self, x: float, y: float) -> Optional[str]:
        if self._pixmap.isNull():
            return None
        target = self._target_rect()
        self._update_scale(target)
        keep = self._keep_rect(target)
        if keep.isNull():
            return None
        tol = EDGE_TOL
        near_left = abs(x - keep.left()) <= tol
        near_right = abs(x - keep.right()) <= tol
        near_top = abs(y - keep.top()) <= tol
        near_bottom = abs(y - keep.bottom()) <= tol
        on_x = keep.left() - tol <= x <= keep.right() + tol
        on_y = keep.top() - tol <= y <= keep.bottom() + tol

        # Corners take priority.
        if near_left and near_top:
            return "tl"
        if near_right and near_top:
            return "tr"
        if near_left and near_bottom:
            return "bl"
        if near_right and near_bottom:
            return "br"
        if near_left and on_y:
            return "l"
        if near_right and on_y:
            return "r"
        if near_top and on_x:
            return "t"
        if near_bottom and on_x:
            return "b"
        return None

    def _cursor_for(self, edge: Optional[str]) -> Qt.CursorShape:
        if edge in ("l", "r"):
            return Qt.CursorShape.SizeHorCursor
        if edge in ("t", "b"):
            return Qt.CursorShape.SizeVerCursor
        if edge in ("tl", "br"):
            return Qt.CursorShape.SizeFDiagCursor
        if edge in ("tr", "bl"):
            return Qt.CursorShape.SizeBDiagCursor
        return Qt.CursorShape.ArrowCursor

    def _apply_drag(self, dx_px: float, dy_px: float) -> None:
        """Apply a pixel delta to the currently-dragged edge(s)."""
        edge = self._drag_edge
        if not edge:
            return
        dx = dx_px / self._ppw if self._ppw > 0 else 0.0
        dy = dy_px / self._pph if self._pph > 0 else 0.0
        l, t, r, b = self._margins
        w, h = self._page_w_pt, self._page_h_pt
        if "l" in edge:  # covers l, tl, bl
            l = max(0.0, min(w - r - KEEP_MIN, l + dx))
        if "r" in edge:  # covers r, tr, br
            r = max(0.0, min(w - l - KEEP_MIN, r - dx))
        if "t" in edge:  # covers t, tl, tr
            t = max(0.0, min(h - b - KEEP_MIN, t + dy))
        if "b" in edge:  # covers b, bl, br
            b = max(0.0, min(h - t - KEEP_MIN, b - dy))
        self.set_margins(l, t, r, b)
        self.margins_changed.emit(l, t, r, b)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        self._drag_edge = self._edge_at(pos.x(), pos.y())
        self._last_x = pos.x()
        self._last_y = pos.y()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        x, y = pos.x(), pos.y()
        if self._drag_edge and (event.buttons() & Qt.MouseButton.LeftButton):
            self._apply_drag(x - self._last_x, y - self._last_y)
            self._last_x = x
            self._last_y = y
        else:
            self.setCursor(self._cursor_for(self._edge_at(x, y)))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_edge = None


class CropDialog(QDialog):
    """Ask user for crop margins and which pages to apply them to."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        page_width: float = 595.0,
        page_height: float = 842.0,
        page_pixmap: Optional[QPixmap] = None,
        selection_count: int = 0,
        initial_box: Optional[CropBox] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("裁剪頁面")
        self.setModal(True)
        self.setMinimumWidth(480)
        self._page_width = page_width
        self._page_height = page_height

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.preview = CropPreview()
        if page_pixmap is not None:
            self.preview.set_page(page_pixmap, page_width, page_height)
        self.preview.margins_changed.connect(self._on_preview_margins)
        layout.addWidget(self.preview, stretch=1)

        hint = QLabel(
            "輸入四邊要裁去的邊界（單位：點 / pt，1 吋 = 72 pt），"
            "或在左側預覽直接拖曳邊緣。\n"
            f"目前頁面大約：{page_width:.0f} × {page_height:.0f} pt"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QGridLayout()
        self.left = self._spin()
        self.top = self._spin()
        self.right = self._spin()
        self.bottom = self._spin()
        form.addWidget(QLabel("左邊距 (Left)："), 0, 0)
        form.addWidget(self.left, 0, 1)
        form.addWidget(QLabel("上邊距 (Top)："), 0, 2)
        form.addWidget(self.top, 0, 3)
        form.addWidget(QLabel("右邊距 (Right)："), 1, 0)
        form.addWidget(self.right, 1, 1)
        form.addWidget(QLabel("下邊距 (Bottom)："), 1, 2)
        form.addWidget(self.bottom, 1, 3)
        layout.addLayout(form)

        scope_box = QGroupBox("套用範圍")
        scope_layout = QVBoxLayout(scope_box)
        self.scope_group = QButtonGroup(self)
        self.rb_all = QRadioButton("全部頁面")
        self.rb_odd = QRadioButton("單數頁（第 1、3、5…頁）")
        self.rb_even = QRadioButton("雙數頁（第 2、4、6…頁）")
        self.rb_sel = QRadioButton(f"選取頁面（已選取 {selection_count} 頁）")
        if selection_count <= 0:
            self.rb_sel.setEnabled(False)
        for rb in (self.rb_all, self.rb_odd, self.rb_even, self.rb_sel):
            self.scope_group.addButton(rb)
            scope_layout.addWidget(rb)
        # Default: selected pages if any, otherwise all pages.
        if selection_count > 0:
            self.rb_sel.setChecked(True)
        else:
            self.rb_sel.setText("選取頁面（無選取）")
            self.rb_all.setChecked(True)
        layout.addWidget(scope_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("套用")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Pre-fill margins from the page's current cropbox, if available.
        box = initial_box or CropBox()
        self._set_margins(
            box.left, box.top, box.right, box.bottom
        )
        for sp in (self.left, self.top, self.right, self.bottom):
            sp.valueChanged.connect(self._on_margin_value_changed)

    def _spin(self) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(0.0, 5000.0)
        sp.setDecimals(1)
        sp.setSingleStep(5.0)
        sp.setValue(0.0)
        sp.setSuffix(" pt")
        return sp

    # ------------------------------------------------------------------
    # Value sync: spinboxes <-> preview
    # ------------------------------------------------------------------

    def _current_margins(self) -> tuple[float, float, float, float]:
        return (
            self.left.value(),
            self.top.value(),
            self.right.value(),
            self.bottom.value(),
        )

    def _set_margins(self, left: float, top: float, right: float, bottom: float) -> None:
        for sp, val in (
            (self.left, left),
            (self.top, top),
            (self.right, right),
            (self.bottom, bottom),
        ):
            sp.blockSignals(True)
            sp.setValue(float(val))
            sp.blockSignals(False)
        self.preview.set_margins(left, top, right, bottom)

    def _on_margin_value_changed(self, *_: object) -> None:
        self.preview.set_margins(*self._current_margins())

    def _on_preview_margins(
        self, left: float, top: float, right: float, bottom: float
    ) -> None:
        self._set_margins(left, top, right, bottom)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def crop_box(self) -> CropBox:
        return CropBox(
            left=self.left.value(),
            top=self.top.value(),
            right=self.right.value(),
            bottom=self.bottom.value(),
        )

    def scope(self) -> str:
        if self.rb_odd.isChecked():
            return "odd"
        if self.rb_even.isChecked():
            return "even"
        if self.rb_sel.isChecked():
            return "selected"
        return "all"