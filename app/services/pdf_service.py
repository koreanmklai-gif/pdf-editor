"""PDF service layer: open/save/render and page operations via PyMuPDF."""

from __future__ import annotations

import io
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import fitz  # PyMuPDF


class PdfError(Exception):
    """User-facing PDF error with a clear Traditional Chinese message."""

    def __init__(self, message: str, *, cause: Optional[BaseException] = None):
        super().__init__(message)
        self.cause = cause


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
        y0 = mb.y0 + self.bottom
        x1 = mb.x1 - self.right
        y1 = mb.y1 - self.top
        if x1 <= x0 or y1 <= y0:
            raise PdfError("裁剪範圍無效：邊界過大，頁面會變成空矩形。")
        return fitz.Rect(x0, y0, x1, y1)


class PdfService:
    """In-memory PDF document with undo-friendly page ops and rendering."""

    def __init__(self) -> None:
        self._doc: Optional[fitz.Document] = None
        self._path: Optional[Path] = None
        self._dirty: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._doc is not None and not self._doc.is_closed

    @property
    def path(self) -> Optional[Path]:
        return self._path

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def page_count(self) -> int:
        self._ensure_open()
        return self._doc.page_count  # type: ignore[union-attr]

    def mark_dirty(self, value: bool = True) -> None:
        self._dirty = value

    # ------------------------------------------------------------------
    # Open / close / save
    # ------------------------------------------------------------------

    def new_empty(self) -> None:
        self.close()
        self._doc = fitz.open()
        self._path = None
        self._dirty = True

    def open(self, path: Union[str, Path], password: str = "") -> None:
        path = Path(path)
        if not path.exists():
            raise PdfError(f"找不到檔案：{path}")
        try:
            doc = fitz.open(path)
        except Exception as exc:  # noqa: BLE001
            raise PdfError(
                f"無法開啟 PDF（可能已損毀或格式不支援）：{path.name}",
                cause=exc,
            ) from exc

        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                doc.close()
                raise PdfError("此 PDF 已加密，需要正確密碼才能開啟。")

        if doc.is_encrypted and doc.permissions == 0:
            # Still locked somehow
            doc.close()
            raise PdfError("此 PDF 已加密，無法讀取內容。")

        self.close()
        self._doc = doc
        self._path = path
        self._dirty = False

    def close(self) -> None:
        if self._doc is not None and not self._doc.is_closed:
            self._doc.close()
        self._doc = None
        self._path = None
        self._dirty = False

    def save(self, path: Optional[Union[str, Path]] = None) -> Path:
        self._ensure_open()
        target = Path(path) if path is not None else self._path
        if target is None:
            raise PdfError("尚未指定儲存路徑，請使用「另存新檔」。")

        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Saving over the currently open file requires incremental or temp dance.
        same_file = self._path is not None and target.resolve() == self._path.resolve()
        try:
            if same_file:
                # Write to temp then replace to avoid "cannot save to original"
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
            raise PdfError(f"儲存失敗：{exc}", cause=exc) from exc

        self._path = target
        self._dirty = False
        return target

    def save_as(self, path: Union[str, Path]) -> Path:
        return self.save(path)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render_page(
        self,
        index: int,
        *,
        zoom: float = 1.5,
        max_side: Optional[int] = None,
    ) -> bytes:
        """Render page to PNG bytes (RGBA)."""
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
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")

    def page_size(self, index: int) -> Tuple[float, float]:
        self._ensure_open()
        self._ensure_index(index)
        r = self._doc.load_page(index).rect  # type: ignore[union-attr]
        return float(r.width), float(r.height)

    def page_cropbox(self, index: int) -> CropBox:
        """Return the page's current crop as margin values (relative to media box)."""
        self._ensure_open()
        self._ensure_index(index)
        page = self._doc.load_page(index)  # type: ignore[union-attr]
        mb = page.mediabox
        cb = page.cropbox
        return CropBox(
            left=cb.x0 - mb.x0,
            top=mb.y1 - cb.y1,
            right=mb.x1 - cb.x1,
            bottom=cb.y0 - mb.y0,
        )

    # ------------------------------------------------------------------
    # Page operations
    # ------------------------------------------------------------------

    def delete_pages(self, indices: Sequence[int]) -> None:
        self._ensure_open()
        if not indices:
            return
        unique = sorted({int(i) for i in indices})
        for i in unique:
            self._ensure_index(i)
        if len(unique) >= self.page_count:
            raise PdfError("無法刪除所有頁面；請至少保留一頁。")
        # PyMuPDF delete_pages accepts a list (descending is safer for some versions)
        self._doc.delete_pages(unique)  # type: ignore[union-attr]
        self._dirty = True

    def rotate_pages(self, indices: Sequence[int], degrees: int) -> None:
        self._ensure_open()
        if degrees % 90 != 0:
            raise PdfError("旋轉角度必須是 90 的倍數。")
        for i in sorted({int(x) for x in indices}):
            self._ensure_index(i)
            page = self._doc.load_page(i)  # type: ignore[union-attr]
            page.set_rotation((page.rotation + degrees) % 360)
        self._dirty = True

    def crop_pages(self, indices: Sequence[int], crop: CropBox) -> None:
        self._ensure_open()
        for i in sorted({int(x) for x in indices}):
            self._ensure_index(i)
            page = self._doc.load_page(i)  # type: ignore[union-attr]
            rect = crop.as_rect(page)
            page.set_cropbox(rect)
        self._dirty = True

    def extract_pages(self, indices: Sequence[int], dest: Union[str, Path]) -> Path:
        self._ensure_open()
        if not indices:
            raise PdfError("請先選取要匯出的頁面。")
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
            raise PdfError(f"匯出失敗：{exc}", cause=exc) from exc
        return dest

    def reorder_pages(self, new_order: Sequence[int]) -> None:
        """Reorder pages. new_order is a permutation of 0..n-1."""
        self._ensure_open()
        n = self.page_count
        order = [int(i) for i in new_order]
        if len(order) != n or sorted(order) != list(range(n)):
            raise PdfError("頁面排序無效：必須是完整的頁面排列。")
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

    def move_page(self, from_index: int, to_index: int) -> None:
        """Move a single page from from_index to to_index (0-based)."""
        self._ensure_open()
        n = self.page_count
        self._ensure_index(from_index)
        if to_index < 0 or to_index >= n:
            raise PdfError("目標位置超出範圍。")
        if from_index == to_index:
            return
        order = list(range(n))
        item = order.pop(from_index)
        order.insert(to_index, item)
        self.reorder_pages(order)

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
            raise PdfError(f"找不到要合併的檔案：{other_path}")
        try:
            other = fitz.open(other_path)
        except Exception as exc:  # noqa: BLE001
            raise PdfError(
                f"無法開啟要合併的 PDF：{other_path.name}",
                cause=exc,
            ) from exc

        try:
            if other.needs_pass:
                if not password or not other.authenticate(password):
                    raise PdfError("要合併的 PDF 已加密，需要正確密碼。")
            if other.page_count == 0:
                raise PdfError("要合併的 PDF 沒有頁面。")

            if insert_at is None:
                self._doc.insert_pdf(other)  # type: ignore[union-attr]
            else:
                if insert_at < 0 or insert_at > self.page_count:
                    raise PdfError("插入位置超出範圍。")
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

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_open(self) -> None:
        if not self.is_open:
            raise PdfError("尚未開啟任何 PDF。")

    def _ensure_index(self, index: int) -> None:
        if index < 0 or index >= self.page_count:
            raise PdfError(f"頁碼超出範圍：{index + 1}（共 {self.page_count} 頁）")
