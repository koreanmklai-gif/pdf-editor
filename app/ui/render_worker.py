"""Background page renderer.

Pages are rendered off the UI thread so that initiating a render never
blocks the main window (real-world PDFs can take 50–200 ms to rasterize at
preview zoom). The worker is the only code that calls into the document
renderer, which serializes PyMuPDF access against page operations performed
on the UI thread. Note PyMuPDF holds the GIL during a native render, so a
single heavy render still stalls the UI thread for roughly its duration;
this module provides non-blocking dispatch, stale-result superseding, and a
seam for a future subprocess renderer that would avoid that stall entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from app.services.pdf_service import PdfService, RenderedPage


@dataclass(frozen=True)
class RenderRequest:
    """One requested render. ``nonce`` lets the UI drop superseded results."""

    nonce: int
    gen: int  # document generation; bumped on any structural change
    index: int
    zoom: float
    max_side: Optional[int]
    kind: str  # "thumb" | "preview"


class RenderWorker(QObject):
    """Serial renderer living in a dedicated QThread.

    Connecting ``request`` to ``_render`` (auto-queued) makes this the only
    code path that calls :meth:`PdfService.render_page_raw`, so the flaky
    PyMuPDF document is touched from at most one thread at a time.
    """

    request = Signal(object)  # RenderRequest
    result = Signal(object, object)  # (RenderRequest, RenderedPage | None)

    def __init__(self, service: PdfService) -> None:
        super().__init__()
        self._service = service
        self.request.connect(self._render)

    @Slot(object)
    def _render(self, req: RenderRequest) -> None:
        try:
            page = self._service.render_page_raw(
                req.index, zoom=req.zoom, max_side=req.max_side
            )
        except Exception:  # noqa: BLE001  (stale/bad request; UI drops it)
            page = None
        self.result.emit(req, page)