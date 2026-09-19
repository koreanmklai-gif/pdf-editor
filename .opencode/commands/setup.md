---
description: Create the .venv and install dependencies for the PDF editor
---

Set up the Python virtual environment and install dependencies for the PDF editor:

1. Create the venv: `python3 -m venv .venv`
2. Install pinned deps: `.venv/bin/pip install -r requirements.txt`
3. Refresh the frozen lock: `.venv/bin/pip freeze > requirements.lock.txt`
4. Verify headlessly: `.venv/bin/python scripts/smoke_test.py` must pass.