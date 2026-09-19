---
description: Package the app into a single-file executable
---

Build the PDF editor into a single-file executable with PyInstaller:

1. Ensure the virtualenv and dev tools are ready:
   `.venv/bin/python -m pip install -r requirements-dev.txt`
2. Run the build script: `./build-exe.sh`
   (equivalent to `.venv/bin/pyinstaller pdf-editor.spec`)
3. Verify and report the output:
   - Binary: `dist/pdf-editor` (`ls -lh dist/pdf-editor`)
   - The executable must exist, be executable, and launch without tracebacks when a display is available.

Note: the first launch of a onefile binary is slower because it self-extracts to a temp directory; later launches are fast.