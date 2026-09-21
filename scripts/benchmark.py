#!/usr/bin/env python3
"""Benchmark PdfService + rendering on a large generated PDF.

Measures the per-page costs that drive the UI: PNG vs raw thumbnail
rendering, the Stage-1 lazy visible-window approach, preview rendering,
page ops, and (full-rewrite) save. Run from the project root:

    .venv/bin/python scripts/benchmark.py            # 1000 pages
    .venv/bin/python scripts/benchmark.py --pages 2000
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.pdf_service import PdfService  # noqa: E402


def _ms(t0: float, t1: float) -> float:
    return (t1 - t0) * 1000.0


def _fmt_mb(path: Path) -> str:
    return f"{path.stat().st_size / 1e6:.1f} MB"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark PdfService on a large PDF.")
    parser.add_argument("--pages", type=int, default=1000)
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="pdf-editor-bench-"))
    path = tmp / f"bench-{args.pages}.pdf"
    n = args.pages
    mid = n // 2

    print(f"=== Benchmark: {n}-page PDF ===")

    # 1. Create + first save (full rewrite)
    svc = PdfService()
    t0 = time.perf_counter()
    svc.create_blank_pdf(pages=n)
    print(f"\ncreate blank PDF:        {_ms(t0, time.perf_counter()):8.0f} ms")

    t0 = time.perf_counter()
    svc.save(path)
    print(f"save after create:       {_ms(t0, time.perf_counter()):8.0f} ms  ({_fmt_mb(path)})")
    svc.close()

    # 2. Open
    svc = PdfService()
    t0 = time.perf_counter()
    svc.open(path)
    print(f"open:                    {_ms(t0, time.perf_counter()):8.0f} ms")
    assert svc.page_count == n

    # 3. Thumbnail passes: the app's open path today renders ALL pages as PNG.
    t0 = time.perf_counter()
    for i in range(n):
        svc.render_page(i, zoom=0.35, max_side=160)
    total = _ms(t0, time.perf_counter())
    print(f"thumbs ALL  (PNG):       {total:8.0f} ms  ({total / n:.2f} ms/page)")

    t0 = time.perf_counter()
    for i in range(n):
        svc.render_page_raw(i, zoom=0.35, max_side=160)
    total = _ms(t0, time.perf_counter())
    print(f"thumbs ALL  (raw):       {total:8.0f} ms  ({total / n:.2f} ms/page)")

    t0 = time.perf_counter()
    for i in range(mid - 20, mid + 20):
        svc.render_page_raw(i, zoom=0.35, max_side=160)
    total = _ms(t0, time.perf_counter())
    print(f"thumbs lazy (~40, raw):  {total:8.0f} ms  (Stage-1 visible window)")

    # 4. Preview
    t0 = time.perf_counter()
    png = svc.render_page(mid, zoom=1.5)
    total = _ms(t0, time.perf_counter())
    print(f"preview (PNG):           {total:8.0f} ms  ({len(png) / 1024:.0f} KB)")

    t0 = time.perf_counter()
    raw = svc.render_page_raw(mid, zoom=1.5)
    total = _ms(t0, time.perf_counter())
    print(f"preview (raw):           {total:8.0f} ms  ({raw.width}x{raw.height})")

    # 5. Page op + in-place save. With Stage 4b, svc.save() on a file-backed
    # doc is an incremental append (fast); save_as() to a new path is a full
    # rewrite (garbage collection + deflate).
    t0 = time.perf_counter()
    svc.delete_pages([0])
    print(f"delete one page:         {_ms(t0, time.perf_counter()):8.0f} ms")

    t0 = time.perf_counter()
    svc.save()
    print(f"save in place (increm.): {_ms(t0, time.perf_counter()):8.0f} ms  ({_fmt_mb(svc.path)})")

    t0 = time.perf_counter()
    svc.delete_pages([0])
    svc.save_as(tmp / "rewrite.pdf")
    print(f"save_as (full rewrite):  {_ms(t0, time.perf_counter()):8.0f} ms")

    svc.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())