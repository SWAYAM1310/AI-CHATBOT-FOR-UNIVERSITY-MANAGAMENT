"""Phase 3 step 3 — the clause-aware policy chunker.

Pure-function tests on hand-written page text, plus the real corpus: every
section / clause / sub-clause in the 7 PDFs must match the markdown sources,
and the 75% rule must come out as one chunk labelled §4.2 on page 2.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.ai.rag.chunkers import CHUNKERS
from app.ai.rag.chunkers.policy import TARGET_TOKENS, estimate_tokens, parse_outline, policy_chunks
from app.ai.rag.manifest import load_manifest
from app.ai.rag.parsers import Page, ParsedDocument, parse_pdf
from app.config import REPO_ROOT

POLICY_MD = REPO_ROOT / "docs" / "policies"
ATTENDANCE_PDF = POLICY_MD / "pdf" / "attendance_regulations.pdf"


def _doc(*pages: str) -> ParsedDocument:
    return ParsedDocument(path=Path("x.pdf"), pages=[Page(number=i, text=t.strip()) for i, t in enumerate(pages, 1)])


@pytest.fixture(scope="module")
def entry():
    return next(e for e in load_manifest() if e.path == ATTENDANCE_PDF)


def test_registered_for_policy_documents():
    assert CHUNKERS["policy"] is policy_chunks


# --- outline parsing --------------------------------------------------------------

def test_sections_clauses_and_subclauses_with_pages():
    doc = _doc(
        "Title line\nRef: X/2026\n1. Scope\n1.1 First clause\nwrapped line\n1.2 Second",
        "2. Rules\n2.1 Top\n2.1.1 Sub one\n2.1.2 Sub two\n2.2 Next top",
    )
    o = parse_outline(doc)
    assert o.preamble == [(1, "Title line"), (1, "Ref: X/2026")]
    assert [(s.number, s.title, s.page) for s in o.sections] == [(1, "Scope", 1), (2, "Rules", 2)]
    assert [(c.label, c.page, c.text) for c in o.sections[0].clauses] == [
        ("1.1", 1, "First clause wrapped line"),
        ("1.2", 1, "Second"),
    ]
    assert [c.label for c in o.sections[1].clauses] == ["2.1", "2.1.1", "2.1.2", "2.2"]


def test_out_of_sequence_numbers_are_continuation_text():
    doc = _doc(
        "1. Scope\n1.1 Rent is due within\n5 days, except as in clause\n3.6.\n"
        "1.2 The table:\n10\n5 %\n20\n1.5 not a clause (skips 1.3)\n2.1 not a clause (section 2 not open)\n1.3 Real third"
    )
    (s,) = parse_outline(doc).sections
    assert [c.label for c in s.clauses] == ["1.1", "1.2", "1.3"]
    assert s.clauses[0].text == "Rent is due within 5 days, except as in clause 3.6."
    assert "1.5 not a clause" in s.clauses[1].text and "2.1 not a clause" in s.clauses[1].text


def test_subclause_only_valid_under_the_current_top_clause():
    doc = _doc("1. S\n1.1 A\n1.1.1 A-one\n1.2 B\n1.1.2 stray (belongs to 1.1, but 1.2 is open)\n1.2.1 B-one")
    (s,) = parse_outline(doc).sections
    assert [c.label for c in s.clauses] == ["1.1", "1.1.1", "1.2", "1.2.1"]
    assert "stray" in s.clauses[2].text


def test_section_heading_must_be_the_next_number():
    doc = _doc("3. Not first\n1. Scope\n1.1 A\n5. Not second\n2. Rules\n2.1 B")
    o = parse_outline(doc)
    assert [s.title for s in o.sections] == ["Scope", "Rules"]
    assert o.preamble == [(1, "3. Not first")]
    assert "5. Not second" in o.sections[0].clauses[0].text


def test_text_between_heading_and_first_clause_is_kept():
    doc = _doc("1. Scope\nAn unnumbered lead-in.\n1.1 A")
    (s,) = parse_outline(doc).sections
    assert [(c.label, c.text) for c in s.clauses] == [("1.0", "An unnumbered lead-in."), ("1.1", "A")]


# --- chunk assembly ---------------------------------------------------------------

def test_one_chunk_per_top_clause_with_heading_and_subclauses(entry):
    doc = _doc("Title\n1. Scope\n1.1 A\n1.1.1 A-one\n1.1.2 A-two\n1.2 B")
    chunks = policy_chunks(doc, entry)
    assert [c.section for c in chunks] == ["Preamble", "§1.1 Scope", "§1.2 Scope"]
    assert chunks[1].content == "1. Scope\n1.1 A\n1.1.1 A-one\n1.1.2 A-two"
    assert chunks[2].content == "1. Scope\n1.2 B"
    assert [c.page for c in chunks] == [1, 1, 1]


def test_lead_in_chunk_is_labelled_by_section(entry):
    doc = _doc("1. Scope\nlead-in\n1.1 A")
    assert [c.section for c in policy_chunks(doc, entry)] == ["§1 Scope", "§1.1 Scope"]


def test_long_clauses_split_at_subclauses_then_sentences(entry):
    sub = "Sentence about something quite long enough to matter. " * 20  # ~250 tokens
    doc = _doc("1. S\n1.1 Head\n1.1.1 " + sub + "\n1.1.2 " + sub + "\n1.1.3 " + sub)
    chunks = policy_chunks(doc, entry)
    assert [c.section for c in chunks] == ["§1.1 S (1/3)", "§1.1 S (2/3)", "§1.1 S (3/3)"]
    assert all(estimate_tokens(c.content) <= TARGET_TOKENS + 10 for c in chunks)  # +heading line
    assert chunks[0].content.startswith("1. S\n1.1 Head\n1.1.1 ")

    one = "A sentence that keeps going and going for a while. " * 60  # ~750 tokens, no sub-clauses
    chunks = policy_chunks(_doc("1. S\n1.1 " + one), entry)
    assert len(chunks) == 2 and all(estimate_tokens(c.content) <= TARGET_TOKENS + 10 for c in chunks)
    assert chunks[1].content.split("\n", 1)[1].startswith("A sentence")  # split on a sentence boundary


def test_page_is_where_the_clause_starts(entry):
    doc = _doc("1. S\n1.1 starts on one\ncontinues on", "two\n1.2 starts on two")
    assert [(c.section, c.page) for c in policy_chunks(doc, entry)] == [("§1.1 S", 1), ("§1.2 S", 2)]
    assert policy_chunks(doc, entry)[0].content.endswith("starts on one continues on two")


def test_unnumbered_document_falls_back_to_pages(entry):
    chunks = policy_chunks(_doc("Just prose.", "More prose."), entry)
    assert [(c.page, c.section, c.content) for c in chunks] == [(1, None, "Just prose."), (2, None, "More prose.")]


# --- the real corpus ---------------------------------------------------------------

@pytest.mark.parametrize("entry_", [e for e in load_manifest() if e.doc_type == "policy"], ids=lambda e: e.path.stem)
def test_every_clause_in_the_pdf_matches_its_markdown_source(entry_):
    md = (POLICY_MD / f"{entry_.path.stem}.md").read_text(encoding="utf-8")
    outline = parse_outline(parse_pdf(entry_.path))
    assert [s.number for s in outline.sections] == [int(n) for n in re.findall(r"^## (\d+)\.", md, re.M)]
    got = [c.label for s in outline.sections for c in s.clauses]
    assert got == re.findall(r"^(\d+\.\d+(?:\.\d+)?) ", md, re.M)
    assert outline.preamble and outline.preamble[0][0] == 1


def test_the_75_percent_rule_is_one_chunk_at_4_2_on_page_2(entry):
    chunks = policy_chunks(parse_pdf(ATTENDANCE_PDF), entry)
    (hit,) = [c for c in chunks if "seventy-five" in c.content]
    assert hit.section == "§4.2 Minimum attendance for examination eligibility"
    assert hit.page == 2
    assert hit.content.startswith("4. Minimum attendance for examination eligibility\n4.2 A student must have")
    assert chunks[0].section == "Preamble" and "AR/IV/2026" in chunks[0].content
    assert all(estimate_tokens(c.content) <= TARGET_TOKENS for c in chunks)
    assert len(chunks) == 40
