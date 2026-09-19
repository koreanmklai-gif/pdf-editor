# PDF 編輯器（MVP）

輕量桌面 PDF 頁面編輯工具，類似精簡版 Adobe Acrobat：預覽、多選、刪除、裁剪、旋轉、匯出、排序、合併。

技術：**Python 3.11+** · **PySide6** · **PyMuPDF (fitz)**

---

## 安裝與執行

```bash
cd <本專案資料夾>   # 例如 /media/mathslai/DATADISK/3-myprog/mkopencode/pdf-editor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app
```

無顯示環境時，可先跑服務層煙霧測試：

```bash
source .venv/bin/activate
python scripts/smoke_test.py
```

使用 OpenCode 開發時，可直接用專案斜線指令：

| 指令 | 作用 |
|------|------|
| `/setup` | 建立 `.venv` 並安裝相依套件 |
| `/run` | 啟動圖形介面（需要顯示環境） |
| `/test` | 執行無頭煙霧測試 |
| `/build` | 以 PyInstaller 打包為單一執行檔 |

---

## 打包為單一執行檔

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt   # 加入 PyInstaller
./build-exe.sh                        # 產出 dist/pdf-editor（單一檔案）
./dist/pdf-editor                     # 直接執行
```

- `run.py` 是 PyInstaller 的進入點；一般開發仍用 `python -m app`。
- `pdf-editor.spec` 已納入版本控制，可用 `.venv/bin/pyinstaller pdf-editor.spec` 重現相同建置。
- 產物在 `dist/`（已被 `.gitignore` 排除），暫存檔與中間檔在 `build/`。

---

## 功能一覽

| # | 功能 | 說明 |
|---|------|------|
| 1 | 檢視／預覽 | 開啟 PDF、底部縮圖列 + 中央頁面預覽 |
| 2 | 多選頁面 | 滑鼠點選、Shift 範圍、Ctrl/Cmd 切換 |
| 3 | 刪除頁面 | 刪除選取頁（確認對話框） |
| 4 | 裁剪 | 對話框輸入四邊邊界（pt），以 PyMuPDF 套用 cropbox |
| 5 | 旋轉 | 順時針 90°、逆時針 90°、180° |
| 6 | 匯出 | 將選取頁另存為新 PDF |
| 7 | 排序 | 拖放縮圖，或「上移／下移」按鈕 |
| 8 | 合併 | 開啟另一 PDF，附加到結尾或插入指定位置 |
| — | 檔案 | 開啟、儲存、另存新檔；髒旗標（未儲存標記 `*`） |
| — | 錯誤處理 | 找不到檔案、損毀、加密 PDF 有明確提示 |

介面標籤為繁體中文（港／台式用語）。

---

## 專案結構

```
pdf-editor/
├── .opencode/
│   ├── commands/             # /setup、/run、/test、/build 斜線指令
│   └── skills/
│       └── pdf-editor-dev/   # 專案開發技能（SKILL.md）
├── app/
│   ├── __main__.py           # python -m app
│   ├── main.py               # QApplication 啟動
│   ├── services/
│   │   └── pdf_service.py    # PDF 操作（與 GUI 分離）
│   └── ui/
│       ├── main_window.py
│       ├── thumbnail_list.py
│       └── crop_dialog.py
├── scripts/
│   └── smoke_test.py
├── .gitignore
├── .gitattributes
├── AGENTS.md                  # OpenCode 專案指引
├── build-exe.sh               # PyInstaller 打包腳本
├── pdf-editor.spec            # PyInstaller spec（可重現建置）
├── requirements.txt
├── requirements-dev.txt       # 開發相依（含 PyInstaller）
├── requirements.lock.txt      # 精確鎖定相依版本
├── run.py                     # PyInstaller 進入點
└── README.md
```

---

## English (short)

**Install & run**

```bash
cd <this-project-dir> && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && python -m app
```

**Features:** view + thumbnails, multi-select, delete, crop, rotate (90/180), extract pages, reorder (drag or buttons), merge (append/insert), Open/Save/Save As, dirty flag, errors for missing/corrupt/encrypted PDFs.

**Headless check:** `python scripts/smoke_test.py` exercises the same `PdfService` layer.
