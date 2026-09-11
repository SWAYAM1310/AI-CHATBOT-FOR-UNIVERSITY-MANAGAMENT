"""Phase 3 step 6 — tabular (calendar) extraction and single-chunk notices.

Ingests the synthetic calendar and the four notices (small, no embedder) into
a clean doc store; the session fixture in conftest restores the real corpus
afterwards.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.ai.orchestrator import run_turn
from app.ai.providers import LLMResponse, ToolCall, Usage
from app.ai.rag import retriever as retriever_mod
from app.ai.rag.chunkers import CHUNKERS, EXTRACTORS
from app.ai.rag.chunkers.notice import notice_chunks
from app.ai.rag.chunkers.tabular import build, extract_calendar, parse_date, tabular_chunks
from app.ai.rag.ingest import ingest, ingest_one
from app.ai.rag.manifest import load_manifest
from app.ai.rag.parsers import Page, ParsedDocument, Table, clean_tables, extract_tables
from app.ai.tools.registry import REGISTRY
from app.db.session import SessionLocal
from app.models import AcademicCalendarEvent, DocChunk, Document
from tests.conftest import make_ctx
from tests.test_orchestrator import ScriptedProvider

ENTRIES = [e for e in load_manifest() if e.doc_type in ("tabular", "notice")]
CALENDAR = next(e for e in ENTRIES if e.doc_type == "tabular")
FACULTY_CIRCULAR = next(e for e in ENTRIES if "faculty" in e.path.name)


@pytest.fixture(scope="module", autouse=True)
def _ingested():
    with SessionLocal() as db:
        db.execute(text("UPDATE academic_calendar SET source_chunk_id = NULL"))
        db.execute(text("TRUNCATE doc_chunks, documents RESTART IDENTITY CASCADE"))
        db.commit()
    report = ingest(ENTRIES)
    assert not report.failed, report.failed
    retriever_mod._warned_no_embedder = True


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


def _doc(*pages: str) -> ParsedDocument:
    return ParsedDocument(path=Path("x.pdf"), pages=[Page(number=i, text=t.strip()) for i, t in enumerate(pages, 1)])


def test_registered_for_their_doc_types():
    assert CHUNKERS["tabular"] is tabular_chunks and EXTRACTORS["tabular"] is extract_calendar
    assert CHUNKERS["notice"] is notice_chunks


# --- table cleaning -------------------------------------------------------------------

def test_clean_tables_drops_phantom_columns_and_merges_split_rows():
    raw = Table(
        page=2,
        rows=[
            ["Dussehra holiday", "holiday", "", "20 October", "", "", "all", "", "2026-27-"],
            ["", "", "", "2026", "", "", "", "", "ODD"],
            ["Diwali vacation", "break", "", "7 November 2026", "", "15 November 2026", "all", "", "2026-27- ODD"],
        ],
    )
    (t,) = clean_tables([raw])
    assert t.rows == [
        ["Dussehra holiday", "holiday", "20 October 2026", "", "all", "2026-27- ODD"],
        ["Diwali vacation", "break", "7 November 2026", "15 November 2026", "all", "2026-27- ODD"],
    ]


@pytest.mark.parametrize(
    ("text_", "expected"),
    [("26 August 2026", date(2026, 8, 26)), ("5 Sep 2026", date(2026, 9, 5)), ("2026-08-26", date(2026, 8, 26)),
     ("26/08/2026", date(2026, 8, 26)), ("26 August\n2026", date(2026, 8, 26)), ("", None), ("tba", None)],
)
def test_parse_date_formats(text_, expected):
    assert parse_date(text_) == expected


def test_calendar_pdf_tables_keep_every_row_including_the_one_at_the_page_break():
    tables = extract_tables(CALENDAR.path)
    data = [r for t in tables for r in t.rows if r[0] != "Event" and len(r) == 6]
    assert len(data) == 25
    assert any(r[0] == "Raksha Bandhan holiday" and r[2] == "26 August 2026" for r in data)
    assert any(r[0] == "Dussehra holiday" and r[2] == "20 October 2026" for r in data)  # was a split row
    assert all(len(r) == 6 for t in tables for r in t.rows if r[0] != "Applies")


# --- chunkers ---------------------------------------------------------------------------

def test_tabular_chunks_are_page_prose_plus_one_chunk_per_table_with_row_sentences():
    parsed = ParsedDocument(path=CALENDAR.path)
    from app.ai.rag.parsers import parse_pdf
    parsed = parse_pdf(CALENDAR.path)
    drafts, blocks = build(parsed, CALENDAR)
    assert [d.page for d in drafts[:2]] == [1, 2] and all(d.section is None for d in drafts[:2])
    tables = [d for d in drafts if d.section and d.section.startswith("Table")]
    assert len(tables) == len(blocks) >= 3
    continued = next(d for d in tables if "Raksha Bandhan" in d.content)
    assert continued.section.startswith("Table 4 (Event, Type, From") and continued.page == 2  # header inherited
    assert "Event: Raksha Bandhan holiday; Type: holiday; From: 26 August 2026; Applies to: all; Term: 2026-27- ODD" in continued.content
    assert all(blocks[i].draft == drafts.index(t) for i, t in enumerate(tables))


def test_notice_is_one_chunk_headed_by_its_title():
    chunks = notice_chunks(_doc("Notice: Fees due\nOffice of X\nPay by Friday.", "Continued text."), CALENDAR)
    assert len(chunks) == 1
    assert chunks[0].section == "Notice: Fees due" and chunks[0].page == 1
    assert chunks[0].content == "Notice: Fees due\nOffice of X\nPay by Friday.\n\nContinued text."
    assert notice_chunks(_doc("", ""), CALENDAR) == []


# --- the calendar extract ------------------------------------------------------------------

def test_calendar_rows_are_upserted_with_their_source_chunk(db):
    rows = db.scalars(select(AcademicCalendarEvent).order_by(AcademicCalendarEvent.start_date)).all()
    assert len(rows) == 25 and all(r.source_chunk_id for r in rows)
    raksha = next(r for r in rows if r.event == "Raksha Bandhan holiday")
    assert (raksha.start_date, raksha.end_date, raksha.event_type, raksha.term) == (date(2026, 8, 26), None, "holiday", "2026-27-ODD")
    exams = next(r for r in rows if r.event == "Odd Semester end-term examinations")
    assert (exams.start_date, exams.end_date) == (date(2026, 11, 17), date(2026, 11, 28))
    chunk = db.get(DocChunk, exams.source_chunk_id)
    assert chunk.section.startswith("Table") and "Odd Semester end-term examinations" in chunk.content
    assert db.scalar(select(Document.doc_type).where(Document.id == chunk.document_id)) == "tabular"


def test_reingest_corrects_a_changed_row_and_reinserts_a_deleted_one(db):
    exams = db.scalars(select(AcademicCalendarEvent).where(AcademicCalendarEvent.event == "Odd Semester end-term examinations")).one()
    exams.end_date = date(2026, 12, 1)
    diwali = db.scalars(select(AcademicCalendarEvent).where(AcademicCalendarEvent.event == "Diwali vacation")).one()
    db.delete(diwali)
    db.commit()
    assert ingest_one(CALENDAR, db, force=True) == 6  # 2 page chunks + 4 tables
    db.commit()
    db.expire_all()
    assert exams.end_date == date(2026, 11, 28)
    diwali = db.scalars(select(AcademicCalendarEvent).where(AcademicCalendarEvent.event == "Diwali vacation")).one()
    assert (diwali.start_date, diwali.end_date, diwali.source_chunk_id is not None) == (date(2026, 11, 7), date(2026, 11, 15), True)
    assert db.scalar(select(func.count(AcademicCalendarEvent.id))) == 25


def test_non_calendar_tabular_documents_extract_nothing(db):
    from dataclasses import replace
    other = replace(CALENDAR, category="timetable")
    doc = db.scalars(select(Document).where(Document.source_path == CALENDAR.source_path)).one()
    assert extract_calendar(db, doc, _doc("x"), other, []) == 0


# --- tools and the turn -------------------------------------------------------------------

def test_policy_search_covers_notices_and_the_calendar_and_respects_audience(db):
    student = REGISTRY.invoke("search_university_policies", make_ctx("student", 17), db, {"query": "internal test 1 marks entry deadline"})
    faculty = REGISTRY.invoke("search_university_policies", make_ctx("faculty", 4), db, {"query": "internal test 1 marks entry deadline"})
    assert not any(FACULTY_CIRCULAR.title.split(":")[0] in h["document"] for h in student)
    assert any(FACULTY_CIRCULAR.title.split(":")[0] in h["document"] for h in faculty)
    fees = REGISTRY.invoke("search_university_policies", make_ctx("student", 17), db, {"query": "fee payment last date"})
    assert any(h["document"].startswith("Notice FO/N/2026/07") for h in fees)
    exams = REGISTRY.invoke("search_university_policies", make_ctx("student", 17), db, {"query": "end-term examinations November"})
    assert any(h["document"].startswith("Academic Calendar") for h in exams)


def test_get_academic_calendar_returns_rows_and_citable_source_passages(db):
    result = REGISTRY.invoke("get_academic_calendar", make_ctx("student", 17), db, {"event_type": "exam"})
    assert [r["event"] for r in result["rows"]] == ["Internal Test 1", "Internal Test 2", "Odd Semester end-term examinations"]
    assert result["passages"] and all({"chunk_id", "document", "section", "page", "excerpt"} <= set(p) for p in result["passages"])
    assert all(p["document"].startswith("Academic Calendar") for p in result["passages"])


def test_a_calendar_answer_can_cite_the_calendar_pdf(db):
    route = LLMResponse(text=json.dumps({"intent": "dates", "candidate_tools": ["get_academic_calendar"], "needs_rag": False}), usage=Usage(90, 20))
    plan = LLMResponse(text="", tool_calls=[ToolCall(id="1", name="get_academic_calendar", arguments={"event_type": "exam"})], usage=Usage(150, 30))
    provider = ScriptedProvider(route, plan, LLMResponse(text="Exams run 17–28 November [[cite:{cid}]]."))
    out = run_turn(question="when are the end-sem exams?", ctx=make_ctx("student", 17), db=db, provider=provider)
    prompt = provider.calls[-1]["messages"][-1]["content"]
    assert "### get_academic_calendar" in prompt and "| Internal Test 2 |" in prompt  # the rows stay in the tool results
    assert "[[cite:" in prompt and "Academic Calendar 2026-27" in prompt  # and the calendar PDF is offered to cite
    assert out.tool_runs[0].passages
