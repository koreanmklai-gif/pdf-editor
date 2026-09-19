#!/usr/bin/env python3
"""PyInstaller entry point: builds a single-file executable (`pdf-editor`).

Run `python -m app` for normal development; this file exists so PyInstaller
can analyze the `app` package from the project root.
"""

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())