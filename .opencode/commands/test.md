---
description: Run the headless PDF service smoke test
---

Run the headless `PdfService` smoke test: `.venv/bin/python scripts/smoke_test.py`.

It must print `=== ALL SMOKE TESTS PASSED ===` and exit with code 0. If any check fails, inspect `app/services/pdf_service.py` and the smoke test, fix the failure, and re-run until it passes.