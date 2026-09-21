"""PDF service layer: open/save/render and page operations via PyMuPDF."""

from __future__ import annotations

import functools
import io
import logging
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def _synchronized(method: object) -> object:
    """Serialize document access across threads.

    PyMuPDF documents are not thread-safe. The background render worker and
    the UI thread both touch the document, so every document-touching entry
    point takes the same reentrant lock (safe for nested calls within one
    thread). ``is_open``/``page_count`` are deliberately lock-free mirrors
    (see ``__init__``) so the UI thread can bounds-check without waiting on
    a render in flight.
    """

    @functools.wraps(method)  # type: ignore[arg-type]
    def wrapper(self: "PdfService", *args: object, **kwargs: object) -> object:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class PdfError(Exception):
    """User-facing PDF error with a clear message."""

    def __init__(self, message: str, *, cause: Optional[BaseException] = None):
        super().__init__(message)
        self.cause = cause


@dataclass
class RenderedPage:
    """Raw RGB(A) pixel data of a rendered page (no PNG encoding).

    `samples` is a contiguous buffer of `width * height * n` bytes where
    `n` is the number of color components (3 for RGB, 4 for RGBA); the
    UI layer builds images from it directly, avoiding a PNG round-trip.
    """

    samples: bytes
    width: int
    height: int
    stride: int


@dataclass
class CropBox:
    """Crop margins in PDF points (1 pt = 1/72 inch), relative to media box."""

    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0

    def as_rect(self, page: fitz.Page) -> fitz.Rect:
        mb = page.mediabox
        x0 = mb.x0 + self.left
        y0 = mb.y0 + self.top
        x1 = mb.x1 - self.right
        y1 = mb.y1 - self.bottom
        if x1 <= x0 or y1 <= y0:
            raise PdfError("Invalid crop area: margins are too large, the page would become an empty rectangle.")
        return fitz.Rect(x0, y0, x1, y1)


class PdfService:
    """In-memory PDF document with undo-friendly page ops and rendering."""

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._doc: Optional[fitz.Document] = None
        self._path: Optional[Path] = None
        self._dirty: bool = False
        # Lock-free mirrors of document state, refreshed under ``_lock``.
        # They let the UI thread do cheap bounds checks without contending
        # with a long background render (which holds the lock). They are
        # only ever written by the main thread (which also owns the lock
        # when writing), so reads from the GUI and worker threads are safe
        # and always current.
        self._is_open: bool = False
        self._page_count: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def path(self) -> Optional[Path]:
        return self._path

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def page_count(self) -> int:
        return self._page_count

    def mark_dirty(self, value: bool = True) -> None:
        self._dirty = value

    def _refresh_page_count(self) -> None:
        """Re-sync the lock-free page-count mirror. Caller holds ``_lock``."""
        if self._doc is not None and not self._doc.is_closed:
            self._page_count = int(self._doc.page_count)

    # ------------------------------------------------------------------
    # Open / close / save
    # ------------------------------------------------------------------

    @_synchronized
    def new_empty(self) -> None:
        self.close()
        self._doc = fitz.open()
        self._path = None
        self._dirty = True
        self._is_open = True
        self._page_count = 0

    @_synchronized
    def open(self, path: Union[str, Path], password: str = "") -> None:
        path = Path(path)
        if not path.exists():
            raise PdfError(f"File not found: {path}")
        try:
            doc = fitz.open(path)
        except Exception as exc:  # noqa: BLE001
            raise PdfError(
                f"Cannot open PDF (it may be corrupted or the format is unsupported): {path.name}",
                cause=exc,
            ) from exc

        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                doc.close()
                raise PdfError("This PDF is encrypted and requires a valid password to open.")

        if doc.is_encrypted and doc.permissions == 0:
            # Still locked somehow
            doc.close()
            raise PdfError("This PDF is encrypted and its content cannot be read.")

        self.close()
        self._doc = doc
        self._path = path
        self._dirty = False
        self._is_open = True
        self._page_count = int(doc.page_count)

    @_synchronized
    def close(self) -> None:
        if self._doc is not None and not self._doc.is_closed:
            self._doc.close()
        self._doc = None
        self._path = None
        self._dirty = False
        self._is_open = False
        self._page_count = 0

    def _save_incremental(self, target: Path) -> None:
        """Append changed objects to the existing file (fast on large docs).

        ``incremental=True`` requires the open document to be tied to the file
        on disk (i.e. opened via :meth:`open`) — after an in-memory rebuild
        (e.g. :meth:`merge_pdf` with ``insert_at``) it raises and the caller
        falls back to a full rewrite. ``encryption=KEEP`` is required even for
        unencrypted files, otherwise MuPDF rejects the incremental write.
        """
        doc = self._doc
        assert doc is not None
        doc.save(
            str(target),
            incremental=True,
            encryption=fitz.PDF_ENCRYPT_KEEP,
        )

    @_synchronized
    def save(self, path: Optional[Union[str, Path]] = None) -> Path:
        self._ensure_open()
        target = Path(path) if path is not None else self._path
        if target is None:
            raise PdfError("No save path specified. Use Save As.")

        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        same_file = self._path is not None and target.resolve() == self._path.resolve()

        if same_file and not self._dirty:
            # Nothing changed: a no-op write to the same file would emit an
            # empty incremental update, which MuPDF cannot parse back cleanly.
            return target

        if same_file:
            # Stage 4b fast path: append only the changed bytes, so saving a
            # huge file costs O(change) instead of O(file). Any failure (e.g.
            # the in-memory doc isn't tied to the file after a merge) falls
            # back to the full rewrite below.
            try:
                self._save_incremental(target)
                self._dirty = False
                return target
            except PdfError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    "Incremental save unavailable (%s); falling back to full rewrite", exc
                )

        # Full rewrite (temp + replace for the same file, plain write for new paths).
        try:
            if same_file:
                with tempfile.NamedTemporaryFile(
                    suffix=".pdf", delete=False, dir=str(target.parent)
                ) as tmp:
                    tmp_path = Path(tmp.name)
                self._doc.save(  # type: ignore[union-attr]
                    tmp_path,
                    garbage=4,
                    deflate=True,
                    clean=True,
                )
                self._doc.close()  # type: ignore[union-attr]
                tmp_path.replace(target)
                self._doc = fitz.open(target)
            else:
                self._doc.save(  # type: ignore[union-attr]
                    target,
                    garbage=4,
                    deflate=True,
                    clean=True,
                )
        except PdfError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PdfError(f"Save failed: {exc}", cause=exc) from exc

        self._path = target
        self._dirty = False
        return target

    def save_as(self, path: Union[str, Path]) -> Path:
        return self.save(path)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    @_synchronized
    def render_page(
        self,
        index: int,
        *,
        zoom: float = 1.5,
        max_side: Optional[int] = None,
    ) -> bytes:
        """Render page to PNG bytes (RGB)."""
        pix = self._render_pixmap(index, zoom=zoom, max_side=max_side)
        return pix.tobytes("png")

    @_synchronized
    def render_page_raw(
        self,
        index: int,
        *,
        zoom: float = 1.5,
        max_side: Optional[int] = None,
    ) -> RenderedPage:
        """Render page to raw RGB bytes (no PNG encoding).

        Much cheaper than :meth:`render_page` for hot paths such as
        thumbnails and previews; the UI builds a QImage from the samples.
        """
        pix = self._render_pixmap(index, zoom=zoom, max_side=max_side)
        return RenderedPage(
            samples=bytes(pix.samples),
            width=pix.width,
            height=pix.height,
            stride=pix.stride,
        )

    @_synchronized
    def _render_pixmap(self, index: int, *, zoom: float, max_side: Optional[int]) -> fitz.Pixmap:
        """Shared render core: compute the zoom matrix and get the pixmap."""
        self._ensure_open()
        self._ensure_index(index)
        page = self._doc.load_page(index)  # type: ignore[union-attr]
        mat = fitz.Matrix(zoom, zoom)
        if max_side is not None:
            rect = page.rect
            longest = max(rect.width, rect.height) * zoom
            if longest > max_side and longest > 0:
                scale = max_side / longest
                mat = fitz.Matrix(zoom * scale, zoom * scale)
        return page.get_pixmap(matrix=mat, alpha=False)

    @_synchronized
    def render_page_media_box(
        self,
        index: int,
        *,
        zoom: float = 0.8,
        max_side: Optional[int] = None,
    ) -> bytes:
        """Render the page's full, unrotated media box as PNG bytes.

        Ignores any current cropbox/rotation so the crop dialog can draw its
        overlay in the same coordinate space (media box) that margins are
        defined against by :class:`CropBox`.
        """
        self._ensure_open()
        self._ensure_index(index)
        page = self._doc.load_page(index)  # type: ignore[union-attr]
        saved_crop = page.cropbox
        saved_rotation = page.rotation
        try:
            page.set_cropbox(page.mediabox)
            if saved_rotation:
                page.set_rotation(0)
            mat = fitz.Matrix(zoom, zoom)
            rect = page.rect
            if max_side is not None:
                longest = max(rect.width, rect.height) * zoom
                if longest > max_side and longest > 0:
                    scale = max_side / longest
                    mat = fitz.Matrix(zoom * scale, zoom * scale)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            return pix.tobytes("png")
        finally:
            if saved_rotation:
                page.set_rotation(saved_rotation)
            page.set_cropbox(saved_crop)

    @_synchronized
    def page_size(self, index: int) -> Tuple[float, float]:
        self._ensure_open()
        self._ensure_index(index)
        r = self._doc.load_page(index).rect  # type: ignore[union-attr]
        return float(r.width), float(r.height)

    @_synchronized
    def page_media_size(self, index: int) -> Tuple[float, float]:
        """Return the page's media box size in points (unrotated)."""
        self._ensure_open()
        self._ensure_index(index)
        r = self._doc.load_page(index).mediabox  # type: ignore[union-attr]
        return float(r.width), float(r.height)

    @_synchronized
    def page_cropbox(self, index: int) -> CropBox:
        """Return the page's current crop as margin values (relative to media box)."""
        self._ensure_open()
        self._ensure_index(index)
        page = self._doc.load_page(index)  # type: ignore[union-attr]
        mb = page.mediabox
        cb = page.cropbox
        return CropBox(
            left=cb.x0 - mb.x0,
            top=cb.y0 - mb.y0,
            right=mb.x1 - cb.x1,
            bottom=mb.y1 - cb.y1,
        )

    # ------------------------------------------------------------------
    # Page operations
    # ------------------------------------------------------------------

    @_synchronized
    def delete_pages(self, indices: Sequence[int]) -> None:
        self._ensure_open()
        if not indices:
            return
        unique = sorted({int(i) for i in indices})
        for i in unique:
            self._ensure_index(i)
        if len(unique) >= self.page_count:
            raise PdfError("Cannot delete all pages; at least one page must remain.")
        # PyMuPDF delete_pages accepts a list (descending is safer for some versions)
        self._doc.delete_pages(unique)  # type: ignore[union-attr]
        self._dirty = True
        self._refresh_page_count()

    @_synchronized
    def crop_pages(self, indices: Sequence[int], crop: CropBox) -> None:
        self._ensure_open()
        for i in sorted({int(x) for x in indices}):
            self._ensure_index(i)
            page = self._doc.load_page(i)  # type: ignore[union-attr]
            rect = crop.as_rect(page)
            page.set_cropbox(rect)
        self._dirty = True
        self._refresh_page_count()

    @_synchronized
    def rotate_pages(self, indices: Sequence[int], degrees: int) -> None:
        self._ensure_open()
        if degrees % 90 != 0:
            raise PdfError("Rotation angle must be a multiple of 90.")
        for i in sorted({int(x) for x in indices}):
            self._ensure_index(i)
            page = self._doc.load_page(i)  # type: ignore[union-attr]
            page.set_rotation((page.rotation + degrees) % 360)
        self._dirty = True
        self._refresh_page_count()

    @_synchronized
    def extract_pages(self, indices: Sequence[int], dest: Union[str, Path]) -> Path:
        self._ensure_open()
        if not indices:
            raise PdfError("Select the pages to extract first.")
        ordered = [int(i) for i in indices]
        for i in ordered:
            self._ensure_index(i)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            # insert_pdf range is contiguous; insert one-by-one to preserve selection order
            new_doc = fitz.open()
            for i in ordered:
                new_doc.insert_pdf(self._doc, from_page=i, to_page=i)
            new_doc.save(dest, garbage=4, deflate=True)
            new_doc.close()
        except PdfError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PdfError(f"Export failed: {exc}", cause=exc) from exc
        return dest

    @_synchronized
    def merge_pdf(
        self,
        other_path: Union[str, Path],
        *,
        insert_at: Optional[int] = None,
        password: str = "",
    ) -> None:
        """Append or insert all pages from another PDF.

        insert_at=None means append at end.
        insert_at=k means insert before current page k.
        """
        self._ensure_open()
        other_path = Path(other_path)
        if not other_path.exists():
            raise PdfError(f"File to merge not found: {other_path}")
        try:
            other = fitz.open(other_path)
        except Exception as exc:  # noqa: BLE001
            raise PdfError(
                f"Cannot open the PDF to merge: {other_path.name}",
                cause=exc,
            ) from exc

        try:
            if other.needs_pass:
                if not password or not other.authenticate(password):
                    raise PdfError("The PDF to merge is encrypted and requires a valid password.")
            if other.page_count == 0:
                raise PdfError("The PDF to merge has no pages.")

            if insert_at is None:
                self._doc.insert_pdf(other)  # type: ignore[union-attr]
            else:
                if insert_at < 0 or insert_at > self.page_count:
                    raise PdfError("Insert position is out of range.")
                # Rebuild: [0..insert_at) + other + [insert_at..end)
                new_doc = fitz.open()
                if insert_at > 0:
                    new_doc.insert_pdf(
                        self._doc, from_page=0, to_page=insert_at - 1
                    )
                new_doc.insert_pdf(other)
                if insert_at < self.page_count:
                    new_doc.insert_pdf(
                        self._doc, from_page=insert_at, to_page=self.page_count - 1
                    )
                # Preserve path, replace doc
                path = self._path
                self._doc.close()  # type: ignore[union-attr]
                self._doc = new_doc
                self._path = path
        finally:
            other.close()

        self._dirty = True
        self._refresh_page_count()

    @_synchronized
    def reorder_pages(self, new_order: Sequence[int]) -> None:
        """Reorder pages. new_order is a permutation of 0..n-1."""
        self._ensure_open()
        n = self.page_count
        order = [int(i) for i in new_order]
        if len(order) != n or sorted(order) != list(range(n)):
            raise PdfError("Invalid page order: it must be a complete arrangement of the pages.")
        if order == list(range(n)):
            return
        # select() reorders in place in recent PyMuPDF
        try:
            self._doc.select(order)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            # Fallback: rebuild document
            new_doc = fitz.open()
            for i in order:
                new_doc.insert_pdf(self._doc, from_page=i, to_page=i)
            self._doc.close()  # type: ignore[union-attr]
            self._doc = new_doc
            # keep path
        self._dirty = True
        self._refresh_page_count()

    @_synchronized
    def move_page(self, from_index: int, to_index: int) -> None:
        """Move a single page from from_index to to_index (0-based)."""
        self._ensure_open()
        n = self.page_count
        self._ensure_index(from_index)
        if to_index < 0 or to_index >= n:
            raise PdfError("Target position is out of range.")
        if from_index == to_index:
            return
        order = list(range(n))
        item = order.pop(from_index)
        order.insert(to_index, item)
        self.reorder_pages(order)

    @_synchronized
    def move_pages_up(self, indices: Sequence[int]) -> List[int]:
        """Move selected pages one step toward the start. Returns new selection."""
        self._ensure_open()
        selected = sorted({int(i) for i in indices})
        if not selected:
            return []
        order = list(range(self.page_count))
        for i in selected:
            self._ensure_index(i)
            if i == 0:
                continue
            # Don't swap past another selected page
            if i - 1 in selected:
                continue
            order[i - 1], order[i] = order[i], order[i - 1]
        self.reorder_pages(order)
        # Map old indices to new
        inv = {old: new for new, old in enumerate(order)}
        # After select, page at position k came from order[k]
        # New index of original page p is the position where order[pos]==p
        new_sel = [order.index(i) for i in selected]
        # Wait - after reorder_pages(order), the document pages are rearranged
        # so that new_page[k] = old_page[order[k]].
        # Original page `i` is now at position where order[pos] == i, i.e. order.index(i)
        return sorted(new_sel)

    @_synchronized
    def move_pages_down(self, indices: Sequence[int]) -> List[int]:
        self._ensure_open()
        selected = sorted({int(i) for i in indices}, reverse=True)
        if not selected:
            return []
        order = list(range(self.page_count))
        n = self.page_count
        for i in selected:
            self._ensure_index(i)
            if i >= n - 1:
                continue
            if i + 1 in selected:
                continue
            order[i + 1], order[i] = order[i], order[i + 1]
        self.reorder_pages(order)
        new_sel = [order.index(i) for i in sorted(set(indices))]
        return sorted(new_sel)

    @_synchronized
    def create_blank_pdf(
        self,
        pages: int = 3,
        width: float = 595,  # A4
        height: float = 842,
        *,
        labels: bool = True,
    ) -> None:
        """Create a simple multi-page PDF (useful for tests)."""
        self.close()
        doc = fitz.open()
        for i in range(pages):
            page = doc.new_page(width=width, height=height)
            if labels:
                text = f"Page {i + 1}"
                page.insert_text(
                    (72, 72),
                    text,
                    fontsize=24,
                    color=(0, 0, 0),
                )
                # Distinct marker rectangle per page
                color = ((i * 40) % 256 / 255, 0.2, 0.6)
                page.draw_rect(
                    fitz.Rect(72, 120, 200, 200),
                    color=color,
                    fill=color,
                )
        self._doc = doc
        self._path = None
        self._dirty = True
        self._is_open = True
        self._refresh_page_count()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_open(self) -> None:
        if not self.is_open:
            raise PdfError("No PDF is open.")

    def _ensure_index(self, index: int) -> None:
        if index < 0 or index >= self.page_count:
            raise PdfError(f"Page number out of range: {index + 1} (total {self.page_count} pages)")
