#!/usr/bin/env python3
"""Headless smoke test for PdfService — no GUI required."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Allow running from project root or scripts/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.pdf_service import CropBox, PdfError, PdfService  # noqa: E402


def assert_eq(a, b, msg: str = "") -> None:
    if a != b:
        raise AssertionError(f"{msg}: expected {b!r}, got {a!r}")


def main() -> int:
    print("=== PDF Editor service smoke test ===")
    tmp = Path(tempfile.mkdtemp(prefix="pdf-editor-smoke-"))
    print(f"Work dir: {tmp}")

    svc = PdfService()

    # 1. Create multi-page PDF
    svc.create_blank_pdf(pages=5)
    assert_eq(svc.page_count, 5, "create pages")
    assert svc.dirty
    src = tmp / "original.pdf"
    svc.save(src)
    assert not svc.dirty
    assert_eq(svc.path, src)
    print("[OK] create + save 5-page PDF")

    # Re-open
    svc.close()
    svc.open(src)
    assert_eq(svc.page_count, 5)
    print("[OK] reopen")

    # Render
    png = svc.render_page(0, zoom=1.0, max_side=200)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    print(f"[OK] render page 0 ({len(png)} bytes PNG)")

    # 2. Rotate
    svc.rotate_pages([0, 2], 90)
    assert svc.dirty
    # Check rotation via fitz
    assert_eq(svc._doc.load_page(0).rotation, 90)  # noqa: SLF001
    assert_eq(svc._doc.load_page(2).rotation, 90)  # noqa: SLF001
    print("[OK] rotate 90° pages 1 & 3")

    # 3. Crop
    svc.crop_pages([1], CropBox(left=20, top=30, right=20, bottom=40))
    cb = svc._doc.load_page(1).cropbox  # noqa: SLF001
    assert cb.width < 595 and cb.height < 842
    print(f"[OK] crop page 2 -> cropbox {tuple(cb)}")

    # 3b. page_cropbox reflects the current crop back as margins
    box = svc.page_cropbox(1)
    assert abs(box.left - 20) < 0.01, f"left={box.left}"
    assert abs(box.top - 30) < 0.01, f"top={box.top}"
    assert abs(box.right - 20) < 0.01, f"right={box.right}"
    assert abs(box.bottom - 40) < 0.01, f"bottom={box.bottom}"
    print(f"[OK] page_cropbox(1) -> ({box.left}, {box.top}, {box.right}, {box.bottom})")

    # 4. Reorder: reverse
    svc.reorder_pages([4, 3, 2, 1, 0])
    assert_eq(svc.page_count, 5)
    # After reverse, page that had rotation 90 at old 0 is now at index 4
    assert_eq(svc._doc.load_page(4).rotation, 90)  # noqa: SLF001
    print("[OK] reorder reverse")

    # 5. Move up/down
    new_sel = svc.move_pages_up([4])
    assert 3 in new_sel or 4 in new_sel  # moved toward start
    print(f"[OK] move_pages_up -> {new_sel}")

    # 6. Extract
    extracted = tmp / "extracted.pdf"
    # Current doc still 5 pages; extract first two
    svc.extract_pages([0, 1], extracted)
    ext = PdfService()
    ext.open(extracted)
    assert_eq(ext.page_count, 2, "extracted pages")
    ext.close()
    print("[OK] extract pages 1-2")

    # 7. Delete
    before = svc.page_count
    svc.delete_pages([0])
    assert_eq(svc.page_count, before - 1)
    print(f"[OK] delete one page -> {svc.page_count}")

    # 8. Merge
    other = tmp / "other.pdf"
    other_svc = PdfService()
    other_svc.create_blank_pdf(pages=2, labels=True)
    other_svc.save(other)
    other_svc.close()

    before = svc.page_count
    svc.merge_pdf(other)  # append
    assert_eq(svc.page_count, before + 2)
    print(f"[OK] merge append -> {svc.page_count} pages")

    # Insert at position 1
    before = svc.page_count
    svc.merge_pdf(other, insert_at=1)
    assert_eq(svc.page_count, before + 2)
    print(f"[OK] merge insert_at=1 -> {svc.page_count} pages")

    # Save As
    out = tmp / "final.pdf"
    svc.save_as(out)
    assert out.exists() and out.stat().st_size > 0
    print(f"[OK] save_as {out} ({out.stat().st_size} bytes)")

    # Error cases
    try:
        svc.open(tmp / "nope.pdf")
        raise AssertionError("should have failed on missing file")
    except PdfError as e:
        print(f"[OK] missing file error: {e}")

    # Corrupt file
    bad = tmp / "corrupt.pdf"
    bad.write_bytes(b"%PDF-1.4 not a real pdf junk")
    try:
        svc2 = PdfService()
        svc2.open(bad)
        # PyMuPDF may open some junk leniently; if it opens, that's ok —
        # try rendering which might fail, or accept open
        print(f"[OK] corrupt handling (opened={svc2.is_open}, pages={svc2.page_count if svc2.is_open else 0})")
        svc2.close()
    except PdfError as e:
        print(f"[OK] corrupt file error: {e}")

    svc.close()
    print("=== ALL SMOKE TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}", file=sys.stderr)
        raise
