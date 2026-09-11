"""Render the synthetic corpus: docs/{policies,calendar,notices}/*.md -> <dir>/pdf/*.pdf.

The Markdown files are the source of truth for the synthetic policy, calendar
and notice documents; the PDFs exist so that Phase-3 ingest exercises the real
PDF parser path (page numbers in citations, table extraction) rather than a
Markdown shortcut.

    backend/.venv/Scripts/python.exe scripts/render_policies.py

Deterministic: the same Markdown always yields the same page breaks, so the
`page` in a citation is stable across re-renders.
"""
from __future__ import annotations

import sys
from pathlib import Path

import markdown
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "docs" / d for d in ("policies", "calendar", "notices")]

PAGE = pymupdf.paper_rect("a4")
MARGIN = 56  # 20 mm
CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.35; color: #111; }
h1 { font-size: 17pt; margin: 0 0 6pt 0; }
h2 { font-size: 12.5pt; margin: 14pt 0 4pt 0; }
p { margin: 0 0 6pt 0; }
table { border-collapse: collapse; margin: 4pt 0 8pt 0; width: 100%; }
th, td { border: 0.5pt solid #777; padding: 3pt 5pt; font-size: 9.5pt; vertical-align: top; }
th { background-color: #eee; }
"""


def render(md_path: Path, pdf_path: Path) -> int:
    html = markdown.markdown(md_path.read_text(encoding="utf-8"), extensions=["tables"])
    story = pymupdf.Story(html=html, user_css=CSS)
    writer = pymupdf.DocumentWriter(str(pdf_path))
    where = PAGE + (MARGIN, MARGIN, -MARGIN, -MARGIN)
    pages = 0
    more = True
    while more:
        device = writer.begin_page(PAGE)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
        pages += 1
    writer.close()
    return pages


def main() -> int:
    rendered = 0
    for src in SOURCES:
        out = src / "pdf"
        out.mkdir(parents=True, exist_ok=True)
        for md in sorted(src.glob("*.md")):
            pdf = out / (md.stem + ".pdf")
            pages = render(md, pdf)
            print(f"{md.name:38s} -> {pdf.relative_to(ROOT)}  ({pages} pages)")
            rendered += 1
    if not rendered:
        print(f"no markdown under {', '.join(str(s) for s in SOURCES)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
