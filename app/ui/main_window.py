"""Main application window — Traditional Chinese UI."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QKeySequence,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
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
from app.ui.thumbnail_list import ThumbnailList


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF 編輯器")
        self.resize(1100, 750)

        self.service = PdfService()
        self._preview_index: int = 0
        self._thumb_cache_zoom = 0.35
        self._preview_zoom = 1.5
        self._sidebar_last_w = 210

        self._build_ui()
        self._build_toolbar()
        self._build_menus()
        self._update_actions_enabled()
        self.statusBar().showMessage("請開啟 PDF 檔案")

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
        self.splitter.addWidget(self.thumbs)

        # Right: center preview
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label = QLabel("尚未開啟 PDF")
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
        tb = QToolBar("主工具列")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.act_open = QAction("開啟", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self._on_open)
        tb.addAction(self.act_open)

        self.act_save = QAction("儲存", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self._on_save)
        tb.addAction(self.act_save)

        self.act_save_as = QAction("另存新檔", self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_as.triggered.connect(self._on_save_as)
        tb.addAction(self.act_save_as)

        tb.addSeparator()

        self.act_delete = QAction("刪除頁面", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.triggered.connect(self._on_delete)
        tb.addAction(self.act_delete)

        self.act_crop = QAction("裁剪", self)
        self.act_crop.triggered.connect(self._on_crop)
        tb.addAction(self.act_crop)

        self.act_rot_cw = QAction("順時針 90°", self)
        self.act_rot_cw.triggered.connect(lambda: self._on_rotate(90))
        tb.addAction(self.act_rot_cw)

        self.act_rot_ccw = QAction("逆時針 90°", self)
        self.act_rot_ccw.triggered.connect(lambda: self._on_rotate(-90))
        tb.addAction(self.act_rot_ccw)

        self.act_rot_180 = QAction("旋轉 180°", self)
        self.act_rot_180.triggered.connect(lambda: self._on_rotate(180))
        tb.addAction(self.act_rot_180)

        tb.addSeparator()

        self.act_extract = QAction("匯出選取頁", self)
        self.act_extract.triggered.connect(self._on_extract)
        tb.addAction(self.act_extract)

        self.act_merge = QAction("合併 PDF", self)
        self.act_merge.triggered.connect(self._on_merge)
        tb.addAction(self.act_merge)

        tb.addSeparator()

        self.act_move_up = QAction("上移 ▲", self)
        self.act_move_up.setToolTip("將選取頁面上移")
        self.act_move_up.triggered.connect(self._on_move_up)
        tb.addAction(self.act_move_up)

        self.act_move_down = QAction("下移 ▼", self)
        self.act_move_down.setToolTip("將選取頁面下移")
        self.act_move_down.triggered.connect(self._on_move_down)
        tb.addAction(self.act_move_down)

        # Spacer: push zoom + sidebar controls to the right
        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        tb.addWidget(spacer)

        self.act_zoom_out = QAction("縮小", self)
        self.act_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self.act_zoom_out.triggered.connect(self._on_zoom_out)
        tb.addAction(self.act_zoom_out)

        self.act_zoom_in = QAction("縮大", self)
        self.act_zoom_in.setShortcut(QKeySequence("Ctrl++"))
        self.act_zoom_in.triggered.connect(self._on_zoom_in)
        tb.addAction(self.act_zoom_in)

        self.act_zoom_actual = QAction("100%", self)
        self.act_zoom_actual.setShortcut(QKeySequence("Ctrl+0"))
        self.act_zoom_actual.triggered.connect(self._on_zoom_actual)
        tb.addAction(self.act_zoom_actual)

        self.act_zoom_fit = QAction("適合視窗", self)
        self.act_zoom_fit.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.act_zoom_fit.triggered.connect(self._on_zoom_fit)
        tb.addAction(self.act_zoom_fit)

        tb.addSeparator()

        self.act_sidebar = QAction("縮圖側欄", self)
        self.act_sidebar.setCheckable(True)
        self.act_sidebar.setChecked(True)
        self.act_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        self.act_sidebar.triggered.connect(self._toggle_sidebar)
        tb.addAction(self.act_sidebar)

    def _build_menus(self) -> None:
        menu_file = self.menuBar().addMenu("檔案(&F)")
        menu_file.addAction(self.act_open)
        menu_file.addAction(self.act_save)
        menu_file.addAction(self.act_save_as)
        menu_file.addSeparator()
        act_quit = QAction("結束", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        menu_file.addAction(act_quit)

        menu_edit = self.menuBar().addMenu("編輯(&E)")
        menu_edit.addAction(self.act_delete)
        menu_edit.addAction(self.act_crop)
        menu_edit.addSeparator()
        menu_edit.addAction(self.act_rot_cw)
        menu_edit.addAction(self.act_rot_ccw)
        menu_edit.addAction(self.act_rot_180)
        menu_edit.addSeparator()
        menu_edit.addAction(self.act_extract)
        menu_edit.addAction(self.act_merge)
        menu_edit.addSeparator()
        menu_edit.addAction(self.act_move_up)
        menu_edit.addAction(self.act_move_down)

        menu_view = self.menuBar().addMenu("檢視(&V)")
        menu_view.addAction(self.act_zoom_in)
        menu_view.addAction(self.act_zoom_out)
        menu_view.addAction(self.act_zoom_actual)
        menu_view.addAction(self.act_zoom_fit)
        menu_view.addSeparator()
        menu_view.addAction(self.act_sidebar)

        menu_help = self.menuBar().addMenu("說明(&H)")
        act_about = QAction("關於", self)
        act_about.triggered.connect(self._on_about)
        menu_help.addAction(act_about)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _error(self, message: str, title: str = "錯誤") -> None:
        QMessageBox.critical(self, title, message)

    def _info(self, message: str, title: str = "提示") -> None:
        QMessageBox.information(self, title, message)

    def _confirm(self, message: str, title: str = "確認") -> bool:
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

    def _require_selection(self) -> Optional[List[int]]:
        sel = self._selected()
        if not sel:
            self._info("請先在縮圖列選取一或多個頁面。")
            return None
        return sel

    def _update_title(self) -> None:
        name = "未命名.pdf"
        if self.service.path:
            name = self.service.path.name
        dirty = " *" if self.service.dirty else ""
        self.setWindowTitle(f"PDF 編輯器 — {name}{dirty}")

    def _update_actions_enabled(self) -> None:
        opened = self.service.is_open
        sel = bool(self._selected()) if opened else False
        self.act_save.setEnabled(opened and self.service.dirty)
        self.act_save_as.setEnabled(opened)
        for a in (
            self.act_delete,
            self.act_crop,
            self.act_rot_cw,
            self.act_rot_ccw,
            self.act_rot_180,
            self.act_extract,
        ):
            a.setEnabled(opened and sel)
        self.act_merge.setEnabled(opened)
        self.act_move_up.setEnabled(opened and sel)
        self.act_move_down.setEnabled(opened and sel)

    def _refresh_ui(self, *, keep_selection: Optional[List[int]] = None) -> None:
        if not self.service.is_open:
            self.thumbs.clear_thumbnails()
            self.preview_label.setText("尚未開啟 PDF")
            self.preview_label.setPixmap(QPixmap())
            self._update_title()
            self._update_actions_enabled()
            return

        pixmaps: List[QPixmap] = []
        labels: List[str] = []
        for i in range(self.service.page_count):
            try:
                data = self.service.render_page(
                    i, zoom=self._thumb_cache_zoom, max_side=160
                )
                pix = QPixmap()
                pix.loadFromData(QByteArray(data), "PNG")
                pixmaps.append(pix)
            except Exception:  # noqa: BLE001
                pixmaps.append(QPixmap(100, 140))
            labels.append(str(i + 1))

        prev_sel = keep_selection if keep_selection is not None else self._selected()
        self.thumbs.set_thumbnails(pixmaps, labels)

        # Restore selection (clamp)
        n = self.service.page_count
        restored = [i for i in prev_sel if 0 <= i < n]
        if not restored and n > 0:
            restored = [min(self._preview_index, n - 1)]
        self.thumbs.set_selected_indices(restored)

        preview_idx = restored[0] if restored else 0
        self._show_preview(preview_idx)
        self._update_title()
        self._update_actions_enabled()
        self.statusBar().showMessage(
            f"共 {self.service.page_count} 頁"
            + ("（未儲存）" if self.service.dirty else "")
        )

    def _show_preview(self, index: int) -> None:
        if not self.service.is_open:
            return
        if index < 0 or index >= self.service.page_count:
            return
        self._preview_index = index
        try:
            data = self.service.render_page(
                index, zoom=self._preview_zoom, max_side=None
            )
            pix = QPixmap()
            pix.loadFromData(QByteArray(data), "PNG")
            self.preview_label.setPixmap(pix)
            self.preview_label.setText("")
            self.preview_label.adjustSize()
        except Exception as exc:  # noqa: BLE001
            self.preview_label.setText(f"預覽失敗：{exc}")

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

    def _toggle_sidebar(self, checked: bool) -> None:
        if checked:
            self.thumbs.setVisible(True)
            self.splitter.setSizes(
                [
                    self._sidebar_last_w,
                    max(200, self.splitter.width() - self._sidebar_last_w),
                ]
            )
        else:
            self._sidebar_last_w = self.thumbs.width()
            self.thumbs.setVisible(False)

    def _on_selection_changed(self, indices: List[int]) -> None:
        self._update_actions_enabled()
        if indices:
            self._show_preview(indices[0])
            self.statusBar().showMessage(
                f"已選取 {len(indices)} 頁："
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
            "開啟 PDF",
            "",
            "PDF 檔案 (*.pdf);;所有檔案 (*)",
        )
        if not path:
            return
        try:
            self.service.open(path)
        except PdfError as exc:
            # Try password
            if "加密" in str(exc):
                pwd, ok = QInputDialog.getText(
                    self, "密碼", "此 PDF 已加密，請輸入密碼：",
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
        self.statusBar().showMessage("已儲存")

    def _on_save_as(self) -> None:
        if not self.service.is_open:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "另存新檔",
            str(self.service.path or "未命名.pdf"),
            "PDF 檔案 (*.pdf)",
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
        self.statusBar().showMessage(f"已儲存至 {path}")

    def _maybe_save_before_close(self) -> bool:
        if not self.service.is_open or not self.service.dirty:
            return True
        r = QMessageBox.question(
            self,
            "未儲存的變更",
            "目前檔案有未儲存的變更，要先儲存嗎？",
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
    # Page ops
    # ------------------------------------------------------------------

    def _on_delete(self) -> None:
        sel = self._require_selection()
        if sel is None:
            return
        pages = ", ".join(str(i + 1) for i in sel)
        if not self._confirm(f"確定刪除以下頁面？\n第 {pages} 頁", "刪除頁面"):
            return
        try:
            self.service.delete_pages(sel)
        except PdfError as exc:
            self._error(str(exc))
            return
        keep = []
        n = self.service.page_count
        if n > 0:
            keep = [min(sel[0], n - 1)]
        self._refresh_ui(keep_selection=keep)

    def _on_crop(self) -> None:
        if not self.service.is_open:
            return
        sel = self._selected()
        idx = sel[0] if sel else 0
        if idx >= self.service.page_count:
            return
        w, h = self.service.page_size(idx)
        # Render the page so the dialog can draw the crop region on it.
        pix = QPixmap()
        try:
            data = self.service.render_page(idx, zoom=0.8, max_side=520)
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
        if dlg.exec() != CropDialog.DialogCode.Accepted:
            return
        indices = self._resolve_crop_scope(dlg.scope(), sel)
        if indices is None:
            return
        try:
            self.service.crop_pages(indices, dlg.crop_box())
        except PdfError as exc:
            self._error(str(exc))
            return
        self._refresh_ui(keep_selection=sel)

    def _resolve_crop_scope(
        self, scope: str, selection: List[int]
    ) -> Optional[List[int]]:
        n = self.service.page_count
        if scope == "all":
            return list(range(n))
        if scope == "odd":
            return list(range(0, n, 2))
        if scope == "even":
            return list(range(1, n, 2))
        if scope == "selected":
            if not selection:
                self._info("請先在縮圖列選取一或多個頁面。")
                return None
            return sorted(selection)
        return None

    def _on_rotate(self, degrees: int) -> None:
        sel = self._require_selection()
        if sel is None:
            return
        try:
            self.service.rotate_pages(sel, degrees)
        except PdfError as exc:
            self._error(str(exc))
            return
        self._refresh_ui(keep_selection=sel)

    def _on_extract(self) -> None:
        sel = self._require_selection()
        if sel is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "匯出選取頁面",
            "extracted.pdf",
            "PDF 檔案 (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self.service.extract_pages(sel, path)
        except PdfError as exc:
            self._error(str(exc))
            return
        self._info(f"已匯出 {len(sel)} 頁至：\n{path}")

    def _on_merge(self) -> None:
        if not self.service.is_open:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇要合併的 PDF",
            "",
            "PDF 檔案 (*.pdf)",
        )
        if not path:
            return
        # Ask insert position
        n = self.service.page_count
        items = ["附加到結尾"] + [f"插入到第 {i + 1} 頁之前" for i in range(n)]
        choice, ok = QInputDialog.getItem(
            self, "合併位置", "選擇插入位置：", items, 0, False
        )
        if not ok:
            return
        insert_at: Optional[int]
        if choice == "附加到結尾":
            insert_at = None
        else:
            insert_at = items.index(choice) - 1

        try:
            self.service.merge_pdf(path, insert_at=insert_at)
        except PdfError as e:
            if "加密" in str(e):
                pwd, ok2 = QInputDialog.getText(self, "密碼", "請輸入密碼：")
                if not ok2:
                    return
                try:
                    self.service.merge_pdf(path, insert_at=insert_at, password=pwd)
                except PdfError as e2:
                    self._error(str(e2))
                    return
            else:
                self._error(str(e))
                return
        self._refresh_ui()

    def _on_move_up(self) -> None:
        sel = self._require_selection()
        if sel is None:
            return
        try:
            new_sel = self.service.move_pages_up(sel)
        except PdfError as exc:
            self._error(str(exc))
            return
        self._refresh_ui(keep_selection=new_sel)

    def _on_move_down(self) -> None:
        sel = self._require_selection()
        if sel is None:
            return
        try:
            new_sel = self.service.move_pages_down(sel)
        except PdfError as exc:
            self._error(str(exc))
            return
        self._refresh_ui(keep_selection=new_sel)

    def _on_pages_reordered(self, new_order: List[int]) -> None:
        try:
            self.service.reorder_pages(new_order)
        except PdfError as exc:
            self._error(str(exc))
            self._refresh_ui()
            return
        # Selection follows moved pages: new positions of previously selected
        # After reorder, visual order already matches; keep current row selection
        self._update_title()
        self._update_actions_enabled()
        sel = self.thumbs.selected_indices()
        if sel:
            self._show_preview(sel[0])
        self.statusBar().showMessage("已重新排序頁面（未儲存）")

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "關於 PDF 編輯器",
            "PDF 編輯器 MVP\n"
            "以 PySide6 + PyMuPDF 打造的輕量頁面編輯工具。\n\n"
            "功能：檢視、多選、刪除、裁剪、旋轉、匯出、排序、合併。",
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._maybe_save_before_close():
            self.service.close()
            event.accept()
        else:
            event.ignore()
