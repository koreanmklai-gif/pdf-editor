# PDF Editor — Agent Instructions

Lightweight desktop PDF page editor (view, multi-select, delete, crop, rotate, extract, reorder, merge) built with Python 3.11+, PySide6, and PyMuPDF. All user-facing UI text is Traditional Chinese.

## Commands

- Setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Run app: `.venv/bin/python -m app` (needs a display)
- Headless test: `.venv/bin/python scripts/smoke_test.py`

## Architecture

- `app/ui/` — PySide6 widgets (MainWindow, ThumbnailList, CropDialog). No `fitz` imports here.
- `app/services/pdf_service.py` — `PdfService`, `PdfError`, `CropBox`. All PDF logic; no Qt imports; renders pages to PNG for the UI.
- `scripts/smoke_test.py` — headless sanity checks for `PdfService`; verify after any service change.

## Conventions

- Raise user-facing failures as `PdfError` with a Traditional Chinese message.
- User-facing strings are Traditional Chinese (港／台式用語).
- Type hints everywhere; start modules with `from __future__ import annotations`.
- Dependency pins in `requirements.txt`; exact build in `requirements.lock.txt`.

## Verification

Before finishing: `.venv/bin/python scripts/smoke_test.py` must pass, and the app should start without tracebacks when a display is available.