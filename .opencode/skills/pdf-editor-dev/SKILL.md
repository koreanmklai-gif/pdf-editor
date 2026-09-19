---
name: PDF Editor Dev
description: Guide for working on the PDF editor — architecture, virtualenv usage, run/test workflow, and UI conventions.
---

# PDF Editor Development

Lightweight desktop PDF page editor: view, multi-select, delete, crop, rotate, extract, reorder, merge.
Built with **Python 3.11+**, **PySide6 (Qt6)**, and **PyMuPDF (fitz)**. All user-facing UI text is Traditional Chinese (港／台式用語).

## Environment

- Virtualenv: `.venv/` at the project root.
- Activate with `source .venv/bin/activate`, or run tools directly:
  - App: `.venv/bin/python -m app`
  - Headless test: `.venv/bin/python scripts/smoke_test.py`
- Pins live in `requirements.txt`; the exact frozen build lives in `requirements.lock.txt`.

## Project layout

```
app/
├── __main__.py           # python -m app entry point
├── main.py               # QApplication bootstrap
├── services/
│   ├── __init__.py       # re-exports PdfService, PdfError
│   └── pdf_service.py    # PdfService + PdfError + CropBox (no GUI)
└── ui/
    ├── main_window.py    # MainWindow: menus, toolbar, preview, action wiring
    ├── thumbnail_list.py # ThumbnailList: thumbnails + multi-select + drag-drop
    └── crop_dialog.py    # CropDialog: crop margin dialog
scripts/
└── smoke_test.py         # headless PdfService smoke test (no Qt display needed)
```

## Conventions

- Keep PDF logic in `app/services/pdf_service.py` and GUI code in `app/ui/`; UI modules must not use `fitz` directly.
- Raise user-facing failures as `PdfError` with a Traditional Chinese message.
- Type hints everywhere; start modules with `from __future__ import annotations`.
- `PdfService` renders pages to PNG bytes (`render_page`) and tracks a dirty flag; the GUI refreshes via `_refresh_ui`.
- After changing dependencies, refresh the lock: `.venv/bin/pip freeze > requirements.lock.txt`.

## Verify before finishing

1. Headless: `.venv/bin/python scripts/smoke_test.py` — must print `=== ALL SMOKE TESTS PASSED ===` and exit 0.
2. GUI (only when a display is available): `.venv/bin/python -m app` — window opens with no traceback.