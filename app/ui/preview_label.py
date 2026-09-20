"""Preview label that can draw a live crop-rectangle overlay."""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QLabel

# Same highlight color used by the crop dialog's overlay.
CROP_LINE_COLOR = QColor("#3d7eff")
CROP_LINE_WIDTH = 2


class PreviewLabel(QLabel):
    """QLabel that can draw a crop rectangle over the rendered page.

    The margins are given in points relative to the page (l, t, r, b), plus the
    page size in points the preview was rendered at; the rectangle is scaled to
    the displayed pixmap on every paint. The overlay persists until it is
    cleared or replaced.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._crop_overlay: Optional[tuple[float, float, float, float]] = None
        self._page_w_pt: float = 0.0
        self._page_h_pt: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_crop_overlay(
        self,
        margins: Sequence[float],
        page_w_pt: float,
        page_h_pt: float,
    ) -> None:
        """Show the crop rectangle for ``margins`` = (left, top, right, bottom)."""
        self._crop_overlay = tuple(float(v) for v in margins)
        self._page_w_pt = float(page_w_pt)
        self._page_h_pt = float(page_h_pt)
        self.update()

    def clear_crop_overlay(self) -> None:
        """Hide the crop rectangle."""
        self._crop_overlay = None
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def _pixmap_origin(self) -> tuple[int, int]:
        """Where QLabel draws the pixmap inside this widget (alignment-aware)."""
        pix = self.pixmap()
        if pix is None:
            return (0, 0)
        free_w = self.width() - pix.width()
        free_h = self.height() - pix.height()
        align = self.alignment()
        if align & Qt.AlignmentFlag.AlignHCenter:
            ox = free_w // 2
        elif align & Qt.AlignmentFlag.AlignRight:
            ox = free_w
        else:
            ox = 0
        if align & Qt.AlignmentFlag.AlignVCenter:
            oy = free_h // 2
        elif align & Qt.AlignmentFlag.AlignBottom:
            oy = free_h
        else:
            oy = 0
        return (ox, oy)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)  # draws the pixmap or placeholder text
        if self._crop_overlay is None:
            return
        pix = self.pixmap()
        if pix is None or pix.isNull():
            return
        pw, ph = pix.width(), pix.height()
        if pw <= 0 or ph <= 0 or self._page_w_pt <= 0 or self._page_h_pt <= 0:
            return
        sx = pw / self._page_w_pt
        sy = ph / self._page_h_pt
        l, t, r, b = self._crop_overlay
        ox, oy = self._pixmap_origin()
        rect = QRectF(
            ox + l * sx,
            oy + t * sy,
            max(0.0, pw - (l + r) * sx),
            max(0.0, ph - (t + b) * sy),
        )
        if rect.width() <= 0 or rect.height() <= 0:
            return
        p = QPainter(self)
        p.setPen(QPen(CROP_LINE_COLOR, CROP_LINE_WIDTH))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect)
        p.end()