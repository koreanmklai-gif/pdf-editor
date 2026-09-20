"""Main application window."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QByteArray, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QImage,
    QKeySequence,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.services.pdf_service import CropBox, PdfError, PdfService
from app.ui.crop_dialog import CropDialog
from app.ui.delete_dialog import DeleteDialog
from app.ui.extract_dialog import ExtractDialog
from app.ui.merge_dialog import MergeDialog
from app.ui.preview_label import PreviewLabel
from app.ui.reorder_dialog import ReorderDialog
from app.ui.rotate_dialog import RotateDialog
from app.ui.scope_selector import resolve_scope
from app.ui.thumbnail_list import ThumbnailList


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Editor")
        self.resize(1100, 750)
        self.setMinimumSize(1100, 750)

        self.service = PdfService()
        self._preview_index: int = 0
        self._thumb_cache_zoom = 0.35
        self._preview_zoom = 1.5
        self._sidebar_last_w = 210
        self._crop_overlay: Optional[Tuple[float, float, float, float]] = None
        self._crop_dialog: Optional[CropDialog] = None

        # LRU caches: thumbnails by (page_index, zoom), previews by the same.
        # Thumbnails are rendered lazily for the visible window only; previews
        # avoid re-rendering when we jump between a few pages.
        self._thumb_cache: OrderedDict[Tuple[int, float], QPixmap] = OrderedDict()
        self._thumb_cache_max = 300
        self._preview_cache: OrderedDict[Tuple[int, float], QPixmap] = OrderedDict()
        self._preview_cache_max = 3

        # Debounced thumbnail fill: multiple scroll events collapse into one pass.
        self._fill_timer = QTimer(self)
        self._fill_timer.setSingleShot(True)
        self._fill_timer.setInterval(50)
        self._fill_timer.timeout.connect(self._fill_visible_thumbnails)

        self._build_ui()
        self._build_toolbar()
        self._build_menus()
        self._update_actions_enabled()
        self.statusBar().showMessage("Please open a PDF file")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # Left: thumbnail sidebar (vertical)
        self.thumbs = ThumbnailList()
        self.thumbs.selection_changed_custom.connect(self._on_selection_changed)
        self.thumbs.pages_reordered.connect(self._on_pages_reordered)
        self.thumbs.page_activated.connect(self._show_preview)
        self.thumbs.visible_range_changed.connect(self._schedule_fill)
        self.splitter.addWidget(self.thumbs)

        # Right: center preview
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(False)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.viewport().setStyleSheet(
            "background: #3a3a3a; border: none;"
        )
        self.preview_label = PreviewLabel("No PDF opened")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400, 500)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_label.setStyleSheet(
            "QLabel { background: #3a3a3a; color: #ddd; border: 1px solid #555; }"
        )
        self.preview_scroll.setWidget(self.preview_label)
        self.splitter.addWidget(self.preview_scroll)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([self._sidebar_last_w, 800])
        root.addWidget(self.splitter)

        self.setStatusBar(QStatusBar())

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        tb.setFloatable(False)
        self.addToolBar(tb)

        # ---- Left set: page tools ----
        self.act_open = QAction("Open", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self._on_open)
        tb.addAction(self.act_open)

        self.act_save = QAction("Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self._on_save)
        tb.addAction(self.act_save)

        self.act_save_as = QAction("Save As", self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_as.triggered.connect(self._on_save_as)

        tb.addSeparator()

        self.act_delete = QAction("Delete", self)
        self.act_delete.triggered.connect(self._on_delete)
        tb.addAction(self.act_delete)

        self.act_crop = QAction("Crop", self)
        self.act_crop.triggered.connect(self._on_crop)
        tb.addAction(self.act_crop)

        self.act_rotate = QAction("Rotate", self)
        self.act_rotate.triggered.connect(self._on_rotate)
        tb.addAction(self.act_rotate)

        self.act_extract = QAction("Extract", self)
        self.act_extract.triggered.connect(self._on_extract)
        tb.addAction(self.act_extract)

        self.act_merge = QAction("Merge", self)
        self.act_merge.triggered.connect(self._on_merge)
        tb.addAction(self.act_merge)

        self.act_reorder = QAction("Reorder", self)
        self.act_reorder.triggered.connect(self._on_reorder)
        tb.addAction(self.act_reorder)

        # Spacer: push the zoom + sidebar controls to the right
        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        tb.addWidget(spacer)

        # ---- Right set: zoom + sidebar ----
        self.act_zoom_in = QAction("Zoom In", self)
        self.act_zoom_in.setShortcut(QKeySequence("Ctrl++"))
        self.act_zoom_in.triggered.connect(self._on_zoom_in)
        tb.addAction(self.act_zoom_in)

        self.act_zoom_out = QAction("Zoom Out", self)
        self.act_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self.act_zoom_out.triggered.connect(self._on_zoom_out)
        tb.addAction(self.act_zoom_out)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItem("100%")
        self.zoom_combo.addItem("Fit page")
        self.zoom_combo.addItem("Fit width")
        self.zoom_combo.setToolTip("Zoom preset")
        self.zoom_combo.currentIndexChanged.connect(self._on_zoom_combo_changed)
        tb.addWidget(self.zoom_combo)

        # Zoom presets used by the View menu and shortcuts (not on the toolbar)
        self.act_zoom_actual = QAction("100%", self)
        self.act_zoom_actual.setShortcut(QKeySequence("Ctrl+0"))
        self.act_zoom_actual.triggered.connect(self._on_zoom_actual)

        self.act_zoom_fit = QAction("Fit Page", self)
        self.act_zoom_fit.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.act_zoom_fit.triggered.connect(self._on_zoom_fit)

        self.act_zoom_fit_width = QAction("Fit Width", self)
        self.act_zoom_fit_width.setShortcut(QKeySequence("Ctrl+Shift+W"))
        self.act_zoom_fit_width.triggered.connect(self._on_zoom_fit_width)

        tb.addSeparator()

        self.act_sidebar = QAction("Thumbnail Sidebar", self)
        self.act_sidebar.setCheckable(True)
        self.act_sidebar.setChecked(True)
        self.act_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        self.act_sidebar.triggered.connect(self._toggle_sidebar)
        tb.addAction(self.act_sidebar)

    def _build_menus(self) -> None:
        menu_file = self.menuBar().addMenu("&File")
        menu_file.addAction(self.act_open)
        menu_file.addAction(self.act_save)
        menu_file.addAction(self.act_save_as)
        menu_file.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        menu_file.addAction(act_quit)

        menu_edit = self.menuBar().addMenu("&Edit")
        menu_edit.addAction(self.act_delete)
        menu_edit.addAction(self.act_crop)
        menu_edit.addSeparator()
        menu_edit.addAction(self.act_rotate)
        menu_edit.addSeparator()
        menu_edit.addAction(self.act_extract)
        menu_edit.addAction(self.act_merge)
        menu_edit.addSeparator()
        menu_edit.addAction(self.act_reorder)

        menu_view = self.menuBar().addMenu("&View")
        menu_view.addAction(self.act_zoom_in)
        menu_view.addAction(self.act_zoom_out)
        menu_view.addAction(self.act_zoom_actual)
        menu_view.addAction(self.act_zoom_fit)
        menu_view.addAction(self.act_zoom_fit_width)
        menu_view.addSeparator()
        menu_view.addAction(self.act_sidebar)

        menu_help = self.menuBar().addMenu("&Help")
        act_about = QAction("About", self)
        act_about.triggered.connect(self._on_about)
        menu_help.addAction(act_about)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _error(self, message: str, title: str = "Error") -> None:
        QMessageBox.critical(self, title, message)

    def _info(self, message: str, title: str = "Info") -> None:
        QMessageBox.information(self, title, message)

    def _confirm(self, message: str, title: str = "Confirm") -> bool:
        r = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return r == QMessageBox.StandardButton.Yes

    def _selected(self) -> List[int]:
        return self.thumbs.selected_indices()

    def _update_title(self) -> None:
        name = "Untitled.pdf"
        if self.service.path:
            name = self.service.path.name
        dirty = " *" if self.service.dirty else ""
        self.setWindowTitle(f"PDF Editor — {name}{dirty}")

    def _update_actions_enabled(self) -> None:
        opened = self.service.is_open
        self.act_save.setEnabled(opened and self.service.dirty)
        self.act_save_as.setEnabled(opened)
        for a in (
            self.act_delete,
            self.act_crop,
            self.act_rotate,
            self.act_extract,
            self.act_merge,
            self.act_reorder,
        ):
            a.setEnabled(opened)
        self.act_zoom_in.setEnabled(opened)
        self.act_zoom_out.setEnabled(opened)
        self.zoom_combo.setEnabled(opened)
        for a in (
            self.act_zoom_actual,
            self.act_zoom_fit,
            self.act_zoom_fit_width,
        ):
            a.setEnabled(opened)

    def _refresh_ui(self, *, keep_selection: Optional[List[int]] = None) -> None:
        if not self.service.is_open:
            if self._crop_dialog is not None:
                self._crop_dialog.close()
            self._crop_dialog = None
            self._crop_overlay = None
            self._thumb_cache.clear()
            self._preview_cache.clear()
            self.thumbs.clear_thumbnails()
            self.preview_label.setText("No PDF opened")
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.clear_crop_overlay()
            self.preview_label.adjustSize()
            self._update_title()
            self._update_actions_enabled()
            return

        # Page indices/content may have shifted: drop cached renderings.
        self._thumb_cache.clear()
        self._preview_cache.clear()

        prev_sel = keep_selection if keep_selection is not None else self._selected()
        n = self.service.page_count
        self.thumbs.set_placeholder_pages(n)

        # Restore selection (clamp)
        restored = [i for i in prev_sel if 0 <= i < n]
        if not restored and n > 0:
            restored = [min(self._preview_index, n - 1)]
        self.thumbs.set_selected_indices(restored)

        preview_idx = restored[0] if restored else 0
        self._show_preview(preview_idx)
        self._schedule_fill()
        self._update_title()
        self._update_actions_enabled()
        self.statusBar().showMessage(
            f"Total: {self.service.page_count} pages"
            + (" (unsaved)" if self.service.dirty else "")
        )

    # ------------------------------------------------------------------
    # Lazy thumbnail pipeline
    # ------------------------------------------------------------------

    def _schedule_fill(self) -> None:
        """Debounce fill requests so scroll bursts collapse into one pass."""
        if self.service.is_open:
            self._fill_timer.start()

    def _fill_visible_thumbnails(self) -> None:
        if not self.service.is_open:
            return
        first, last = self.thumbs.visible_range()
        if last < first:
            return
        lookahead = 25
        lo = max(0, first - lookahead)
        hi = min(self.service.page_count - 1, last + lookahead)
        for i in range(lo, hi + 1):
            self._load_thumbnail(i)

    def _load_thumbnail(self, index: int) -> None:
        key = (index, self._thumb_cache_zoom)
        cached = self._thumb_cache.get(key)
        if cached is not None:
            self.thumbs.set_thumbnail(index, cached)
            return
        try:
            page = self.service.render_page_raw(
                index, zoom=self._thumb_cache_zoom, max_side=160
            )
        except Exception:  # noqa: BLE001
            return  # keep the placeholder in place
        img = QImage(
            page.samples, page.width, page.height, page.stride,
            QImage.Format.Format_RGB888,
        )
        pix = QPixmap.fromImage(img)
        self._thumb_cache[key] = pix
        self._thumb_cache.move_to_end(key)
        while len(self._thumb_cache) > self._thumb_cache_max:
            self._thumb_cache.popitem(last=False)
        self.thumbs.set_thumbnail(index, pix)

    def _show_preview(self, index: int) -> None:
        if not self.service.is_open:
            return
        if index < 0 or index >= self.service.page_count:
            return
        self._preview_index = index
        key = (index, self._preview_zoom)
        cached = self._preview_cache.get(key)
        if cached is not None:
            self._preview_cache.move_to_end(key)
            pix = cached
        else:
            try:
                page = self.service.render_page_raw(
                    index, zoom=self._preview_zoom, max_side=None
                )
                img = QImage(
                    page.samples, page.width, page.height, page.stride,
                    QImage.Format.Format_RGB888,
                )
                pix = QPixmap.fromImage(img)
            except Exception as exc:  # noqa: BLE001
                self.preview_label.setText(f"Preview failed: {exc}")
                return
            self._preview_cache[key] = pix
            self._preview_cache.move_to_end(key)
            while len(self._preview_cache) > self._preview_cache_max:
                self._preview_cache.popitem(last=False)
        self.preview_label.setPixmap(pix)
        self.preview_label.setText("")
        self.preview_label.adjustSize()
        # Re-apply an active crop overlay so it follows page/zoom changes.
        if self._crop_overlay is not None and self.service.is_open:
            try:
                pw, ph = self.service.page_size(index)
            except PdfError:
                return
            self.preview_label.set_crop_overlay(self._crop_overlay, pw, ph)

    # ------------------------------------------------------------------
    # Zoom + sidebar
    # ------------------------------------------------------------------

    ZOOM_STEP = 1.25
    ZOOM_MIN = 0.1
    ZOOM_MAX = 8.0

    def _on_zoom_in(self) -> None:
        if not self.service.is_open:
            return
        self._preview_zoom = min(
            self.ZOOM_MAX, self._preview_zoom * self.ZOOM_STEP
        )
        self._show_preview(self._preview_index)

    def _on_zoom_out(self) -> None:
        if not self.service.is_open:
            return
        self._preview_zoom = max(
            self.ZOOM_MIN, self._preview_zoom / self.ZOOM_STEP
        )
        self._show_preview(self._preview_index)

    def _on_zoom_actual(self) -> None:
        if not self.service.is_open:
            return
        self._preview_zoom = 1.0
        self._show_preview(self._preview_index)

    def _on_zoom_fit(self) -> None:
        if not self.service.is_open:
            return
        idx = self._preview_index
        w_pt, h_pt = self.service.page_size(idx)
        vw = self.preview_scroll.viewport().width()
        vh = self.preview_scroll.viewport().height()
        if w_pt <= 0 or h_pt <= 0 or vw <= 0 or vh <= 0:
            return
        margin = 24
        self._preview_zoom = max(
            self.ZOOM_MIN,
            min((vw - margin) / w_pt, (vh - margin) / h_pt),
        )
        self._show_preview(idx)

    def _on_zoom_fit_width(self) -> None:
        if not self.service.is_open:
            return
        idx = self._preview_index
        w_pt, _h_pt = self.service.page_size(idx)
        vw = self.preview_scroll.viewport().width()
        if w_pt <= 0 or vw <= 0:
            return
        margin = 24
        self._preview_zoom = max(
            self.ZOOM_MIN,
            min(self.ZOOM_MAX, (vw - margin) / w_pt),
        )
        self._show_preview(idx)

    def _on_zoom_combo_changed(self, index: int) -> None:
        if index == 1:
            self._on_zoom_fit()
        elif index == 2:
            self._on_zoom_fit_width()
        else:
            self._on_zoom_actual()

    def _toggle_sidebar(self, checked: bool) -> None:
        if checked:
            self.thumbs.setVisible(True)
            self.splitter.setSizes(
                [
                    self._sidebar_last_w,
                    max(200, self.splitter.width() - self._sidebar_last_w),
                ]
            )
            self._schedule_fill()
        else:
            self._sidebar_last_w = self.thumbs.width()
            self.thumbs.setVisible(False)

    def _on_selection_changed(self, indices: List[int]) -> None:
        self._update_actions_enabled()
        if indices:
            self._show_preview(indices[0])
            self.statusBar().showMessage(
                f"Selected {len(indices)} pages: "
                + ", ".join(str(i + 1) for i in indices)
            )

    # ------------------------------------------------------------------
    # File actions
    # ------------------------------------------------------------------

    def _on_open(self) -> None:
        if not self._maybe_save_before_close():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PDF",
            "",
            "PDF Files (*.pdf);;All Files (*)",
        )
        if not path:
            return
        try:
            self.service.open(path)
        except PdfError as exc:
            # Try password
            if "encrypted" in str(exc):
                pwd, ok = QInputDialog.getText(
                    self, "Password", "This PDF is encrypted. Enter the password:",
                )
                if not ok:
                    return
                try:
                    self.service.open(path, password=pwd)
                except PdfError as exc2:
                    self._error(str(exc2))
                    return
            else:
                self._error(str(exc))
                return
        self._preview_index = 0
        self._refresh_ui(keep_selection=[0])

    def _on_save(self) -> None:
        if not self.service.is_open:
            return
        if self.service.path is None:
            self._on_save_as()
            return
        try:
            self.service.save()
        except PdfError as exc:
            self._error(str(exc))
            return
        self._update_title()
        self._update_actions_enabled()
        self.statusBar().showMessage("Saved")

    def _on_save_as(self) -> None:
        if not self.service.is_open:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As",
            str(self.service.path or "Untitled.pdf"),
            "PDF Files (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self.service.save_as(path)
        except PdfError as exc:
            self._error(str(exc))
            return
        self._update_title()
        self._update_actions_enabled()
        self.statusBar().showMessage(f"Saved to {path}")

    def _maybe_save_before_close(self) -> bool:
        if not self.service.is_open or not self.service.dirty:
            return True
        r = QMessageBox.question(
            self,
            "Unsaved Changes",
            "The current file has unsaved changes. Save them first?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if r == QMessageBox.StandardButton.Cancel:
            return False
        if r == QMessageBox.StandardButton.Save:
            self._on_save()
            return not self.service.dirty
        return True

    # ------------------------------------------------------------------
    # Page ops (each tool opens an options dialog)
    # ------------------------------------------------------------------

    def _on_delete(self) -> None:
        if not self.service.is_open:
            return
        sel = self._selected()
        dlg = DeleteDialog(
            self, page_count=self.service.page_count, selection=sel
        )
        if dlg.exec() != DeleteDialog.DialogCode.Accepted:
            return
        try:
            self.service.delete_pages(dlg.target_pages())
        except PdfError as exc:
            self._error(str(exc))
            return
        keep: List[int] = []
        n = self.service.page_count
        if n > 0:
            keep = [min(sel[0], n - 1)] if sel else []
        self._refresh_ui(keep_selection=keep)

    def _on_crop(self) -> None:
        if not self.service.is_open:
            return
        if self._crop_dialog is not None:
            # A crop dialog is already open: focus it instead of opening another.
            self._crop_dialog.raise_()
            self._crop_dialog.activateWindow()
            return
        n = self.service.page_count
        sel = self._selected()
        idx = sel[0] if sel else 0
        if idx >= n:
            return
        w, h = self.service.page_media_size(idx)
        # Render the full page (media box, unrotated) so the dialog's overlay
        # maps to the same coordinate space crop_pages() applies margins in.
        pix = QPixmap()
        try:
            data = self.service.render_page_media_box(idx, zoom=0.8, max_side=520)
            pix.loadFromData(QByteArray(data), "PNG")
        except Exception:  # noqa: BLE001
            pix = QPixmap()
        try:
            box = self.service.page_cropbox(idx)
        except Exception:  # noqa: BLE001
            box = None
        dlg = CropDialog(
            self,
            page_width=w,
            page_height=h,
            page_pixmap=pix,
            selection_count=len(sel),
            initial_box=box,
        )
        # Seed the preview overlay with the current margins (a zero box shows
        # the full page rectangle).
        if box is not None:
            margins: Tuple[float, float, float, float] = (
                box.left,
                box.top,
                box.right,
                box.bottom,
            )
        else:
            margins = (0.0, 0.0, 0.0, 0.0)
        self._set_preview_crop_overlay(margins, idx)

        dlg.margins_changed.connect(self._on_crop_margins_changed)
        dlg.accepted.connect(lambda: self._apply_crop(dlg, sel, n))
        dlg.finished.connect(self._on_crop_finished)
        self._crop_dialog = dlg
        dlg.show()  # modeless: the main window stays interactive

    def _on_crop_margins_changed(
        self, left: float, top: float, right: float, bottom: float
    ) -> None:
        self._set_preview_crop_overlay((left, top, right, bottom), self._preview_index)

    def _set_preview_crop_overlay(
        self, margins: Tuple[float, float, float, float], index: int
    ) -> None:
        self._crop_overlay = (
            float(margins[0]),
            float(margins[1]),
            float(margins[2]),
            float(margins[3]),
        )
        if not self.service.is_open:
            return
        try:
            pw, ph = self.service.page_size(index)
        except PdfError:
            return
        self.preview_label.set_crop_overlay(self._crop_overlay, pw, ph)

    def _apply_crop(
        self, dlg: CropDialog, sel: List[int], page_count: int
    ) -> None:
        indices = resolve_scope(dlg.scope(), page_count, sel)
        if not indices:
            self._info(
                "Please select one or more pages in the thumbnail sidebar first."
            )
            return
        try:
            self.service.crop_pages(indices, dlg.crop_box())
        except PdfError as exc:
            self._error(str(exc))
            return
        self._refresh_ui(keep_selection=sel)

    def _on_crop_finished(self, *_args: object) -> None:
        self._crop_dialog = None
        self._crop_overlay = None
        self.preview_label.clear_crop_overlay()

    def _on_rotate(self) -> None:
        if not self.service.is_open:
            return
        dlg = RotateDialog(
            self, page_count=self.service.page_count, selection=self._selected()
        )
        if dlg.exec() != RotateDialog.DialogCode.Accepted:
            return
        try:
            self.service.rotate_pages(dlg.target_pages(), dlg.angle())
        except PdfError as exc:
            self._error(str(exc))
            return
        self._refresh_ui(keep_selection=self._selected())

    def _on_extract(self) -> None:
        if not self.service.is_open:
            return
        dlg = ExtractDialog(
            self, page_count=self.service.page_count, selection=self._selected()
        )
        if dlg.exec() != ExtractDialog.DialogCode.Accepted:
            return
        pages = dlg.target_pages()
        if not pages:
            self._info("No pages selected to extract.")
            return
        dest = dlg.destination()
        try:
            self.service.extract_pages(pages, dest)
        except PdfError as exc:
            self._error(str(exc))
            return
        self._info(f"Exported {len(pages)} pages to:\n{dest}")

    def _on_merge(self) -> None:
        if not self.service.is_open:
            return
        dlg = MergeDialog(self, page_count=self.service.page_count)
        if dlg.exec() != MergeDialog.DialogCode.Accepted:
            return
        src = dlg.source_path()
        if not src:
            self._error("Choose a PDF file to merge.")
            return
        insert_at = dlg.insert_at()
        try:
            self.service.merge_pdf(src, insert_at=insert_at)
        except PdfError as exc:
            if "encrypted" in str(exc):
                pwd, ok = QInputDialog.getText(
                    self, "Password", "Enter password:"
                )
                if not ok:
                    return
                try:
                    self.service.merge_pdf(
                        src, insert_at=insert_at, password=pwd
                    )
                except PdfError as exc2:
                    self._error(str(exc2))
                    return
            else:
                self._error(str(exc))
                return
        self._refresh_ui()

    def _on_reorder(self) -> None:
        if not self.service.is_open:
            return
        dlg = ReorderDialog(self, page_count=self.service.page_count)
        if dlg.exec() != ReorderDialog.DialogCode.Accepted:
            return
        try:
            self.service.reorder_pages(dlg.new_order())
        except PdfError as exc:
            self._error(str(exc))
            return
        self._refresh_ui()
        self.statusBar().showMessage("Pages reordered (unsaved)")

    def _on_pages_reordered(self, new_order: List[int]) -> None:
        try:
            self.service.reorder_pages(new_order)
        except PdfError as exc:
            self._error(str(exc))
            self._refresh_ui()
            return
        # The visual order already matches the document, but page content per
        # index has changed (pages moved): drop cached renderings and refill.
        self._thumb_cache.clear()
        self._preview_cache.clear()
        self._update_title()
        self._update_actions_enabled()
        sel = self.thumbs.selected_indices()
        if sel:
            self._show_preview(sel[0])
        self._schedule_fill()
        self.statusBar().showMessage("Pages reordered (unsaved)")

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About PDF Editor",
            "PDF Editor MVP\n"
            "A lightweight page editing tool built with PySide6 + PyMuPDF.\n\n"
            "Features: view, multi-select, delete, crop, rotate, extract, reorder, merge.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._maybe_save_before_close():
            self.service.close()
            event.accept()
        else:
            event.ignore()