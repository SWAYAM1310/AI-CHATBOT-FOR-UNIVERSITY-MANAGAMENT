"""Phase 3 step 5b — relational curriculum extract, subject linking, the two curriculum tools.

Ingests the CP syllabus (no embedder, then the FakeEmbedder for the reuse test)
into a clean doc store; the session fixture in conftest restores the real
corpus afterwards.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.ai.orchestrator import _merge_passages, ToolRun, run_turn
from app.ai.providers import LLMResponse, ToolCall, Usage
from app.ai.rag import retriever as retriever_mod
from app.ai.rag.chunkers.curriculum import STRUCTURE_SECTION, _link_subject, parse_courses, title_key, CourseRecord
from app.ai.rag.embedder import FakeEmbedder
from app.ai.rag.ingest import ingest, ingest_one
from app.ai.rag.manifest import load_manifest
from app.ai.rag.parsers import Page, ParsedDocument
from app.ai.tools.registry import REGISTRY
from app.db.session import SessionLocal
from app.models import CourseOutcome, DocChunk, Document, SyllabusCourse, SyllabusUnit, Textbook
from tests.conftest import make_ctx
from tests.test_orchestrator import ScriptedProvider

CP = next(e for e in load_manifest() if e.dept_code == "CP" and e.doc_type == "curriculum")


@pytest.fixture(scope="module", autouse=True)
def _cp_ingested():
    with SessionLocal() as db:
        db.execute(text("UPDATE academic_calendar SET source_chunk_id = NULL"))
        db.execute(text("TRUNCATE doc_chunks, documents RESTART IDENTITY CASCADE"))
        db.commit()
    report = ingest([CP])
    assert not report.failed, report.failed
    retriever_mod._warned_no_embedder = True  # sparse-only here; keep the log quiet


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


def _doc(*pages: str) -> ParsedDocument:
    return ParsedDocument(path=Path("x.pdf"), pages=[Page(number=i, text=t.strip()) for i, t in enumerate(pages, 1)])


# --- title normalisation and subject linking -----------------------------------------

@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Mathematics – I", "Mathematics - 1"),
        ("Database Management Systems", "Database Management System"),
        ("Data Structures Lab", "Data Structures Laboratory"),
        ("Applied Physics (For CS, ICT, ECE, EE)", "Applied Physics"),
        ("Web & Mobile Development Essentials", "Web   Mobile Development Essentials"),
    ],
)
def test_title_key_folds_the_variants_the_two_sources_use(a, b):
    assert title_key(a) == title_key(b)


def test_link_prefers_name_then_department_then_a_plausible_printed_code(db):
    by_name = {"database management system": ["24CS201T", "24EC338T"], "digital logic and design": ["24CS201T"]}
    dbms = CourseRecord(code="24CS202T", title="Database Management Systems", page=1)
    assert _link_subject(db, dbms, by_name, dept_subjects={"24CS201T"}) == "24CS201T"  # the CP one
    assert _link_subject(db, dbms, by_name, dept_subjects={"24EC338T"}) == "24EC338T"  # the EC one
    assert _link_subject(db, dbms, by_name, dept_subjects=set()) == "24CS201T"  # first when neither

    # no name match: the printed code counts only if the dataset's course of that code has a similar name
    dld = CourseRecord(code="24CS202T", title="Digital Logic & Design Principles", page=1)  # dataset 24CS202T = Digital Logic and Design
    assert _link_subject(db, dld, {}, set()) == "24CS202T"
    stranger = CourseRecord(code="24CS202T", title="Underwater Basket Weaving", page=1)
    assert _link_subject(db, stranger, {}, set()) is None


# --- the extract --------------------------------------------------------------------------

def test_every_record_has_a_course_row_with_children_and_source_chunks(db):
    doc = db.scalars(select(Document).where(Document.source_path == CP.source_path)).one()
    courses = db.scalars(select(SyllabusCourse).where(SyllabusCourse.document_id == doc.id)).all()
    assert len(courses) == 88
    assert all(c.source_chunk_id and c.title_key and c.page for c in courses)
    assert all(db.get(DocChunk, c.source_chunk_id).section == " ".join(x for x in (c.code, c.title) if x) for c in courses)
    assert db.scalar(select(func.count(SyllabusUnit.id))) > 250
    assert db.scalar(select(func.count(CourseOutcome.id))) > 500
    assert db.scalar(select(func.count(Textbook.id))) > 300
    linked = sum(c.subject_code is not None for c in courses)
    assert linked >= 60  # by name; the dataset borrowed these course names


def test_dbms_links_to_the_datasets_cp_code_and_unit_rows_cite_their_chunks(db):
    c = db.scalars(select(SyllabusCourse).where(SyllabusCourse.code == "24CS202T")).one()
    assert (c.title, c.subject_code, float(c.credits)) == ("Database Management Systems", "24CS201T", 3.0)
    assert (c.lecture_hours, c.tutorial_hours, c.practical_hours) == (3, 0, 0)
    units = db.scalars(select(SyllabusUnit).where(SyllabusUnit.course_id == c.id).order_by(SyllabusUnit.number)).all()
    assert [u.number for u in units] == [1, 2, 3, 4]
    u3 = units[2]
    assert u3.title.lower().startswith("normalization") and "functional" in u3.topics.lower() and u3.page == 35
    chunk = db.get(DocChunk, u3.source_chunk_id)
    assert chunk.section.endswith(f"Unit 3: {u3.title}") and chunk.parent_chunk_id == c.source_chunk_id


def test_reingest_replaces_the_extract_without_duplicates(db):
    before = db.scalar(select(func.count(SyllabusCourse.id)))
    assert ingest_one(CP, db, force=True) == 556
    db.commit()
    assert db.scalar(select(func.count(SyllabusCourse.id))) == before


def test_forced_reingest_with_identical_text_reuses_stored_vectors(db):
    fake = FakeEmbedder()
    ingest_one(CP, db, force=True, embedder=fake)
    db.commit()
    first = fake.calls
    assert first > 50  # one late-chunked call per course
    ingest_one(CP, db, force=True, embedder=fake)
    db.commit()
    assert fake.calls == first  # nothing re-embedded
    assert db.scalar(select(func.count(DocChunk.id)).where(DocChunk.embedding.is_(None))) == 0
    ingest_one(CP, db, force=True)  # back to text-only for the remaining tests
    db.commit()


def test_structure_tables_between_records_are_not_part_of_the_course_above():
    text_ = """
24CS202T Database Management Systems
Teaching Scheme Examination Scheme
3 0 0 3 3 25 50 25 -- -- 100
COURSE OBJECTIVES
To learn.
TEXT/REFERENCE BOOKS
1. Silberschatz, Database System Concepts.
Category Course
Semester Course Name Theory Tutorial Practical Hrs Credits
PC Data Structures 3 0 0 3 3
24CS203T Data Structures
Teaching Scheme Examination Scheme
3 0 0 3 3 25 50 25 -- -- 100
COURSE OBJECTIVES
To learn more.
"""
    structure, records = parse_courses(_doc(text_))
    assert [r.code for r in records] == ["24CS202T", "24CS203T"]
    assert records[0].books == ["Silberschatz, Database System Concepts."]
    assert [t for _, t in structure] == ["Category Course", "Semester Course Name Theory Tutorial Practical Hrs Credits", "PC Data Structures 3 0 0 3 3"]


# --- the tools ---------------------------------------------------------------------------

def test_get_course_syllabus_by_name_code_and_unit(db):
    ctx = make_ctx("student", 17)
    full = REGISTRY.invoke("get_course_syllabus", ctx, db, {"course": "Database Management Systems"})
    assert full["course"] == "24CS202T Database Management Systems" and full["credits"] == 3.0
    assert full["scheme"] == "L-T-P 3-0-0" and full["source"].endswith(", p.35") and full["chunk_id"]
    assert full["units"].startswith("Unit 1: Introduction And Database Models (10 hrs): ")
    assert "CO1:" in full["outcomes"] and full["textbooks"].startswith("1. A Silberschatz")

    by_dataset_code = REGISTRY.invoke("get_course_syllabus", ctx, db, {"course": "24cs201t", "unit": 3})
    assert by_dataset_code["course"] == full["course"]
    assert by_dataset_code["unit"].startswith("Unit 3: Normalization And File Organization (10 hrs): Importance")
    assert "units" not in by_dataset_code  # one unit asked for, one unit returned

    missing_unit = REGISTRY.invoke("get_course_syllabus", ctx, db, {"course": "24CS202T", "unit": 9})
    assert missing_unit["error"].startswith("no unit 9")


def test_get_course_syllabus_disambiguates_and_reports_unknowns(db):
    ctx = make_ctx("admin")
    r = REGISTRY.invoke("get_course_syllabus", ctx, db, {"course": "mathematics"})
    assert "matches" in r and len(r["matches"]) >= 2 and all("Mathematics" in m for m in r["matches"])
    r = REGISTRY.invoke("get_course_syllabus", ctx, db, {"course": "quantum basket weaving"})
    assert r["error"].startswith("no course matching")


def test_search_curriculum_returns_passages_with_the_course_record_and_no_structure_pages(db):
    hits = REGISTRY.invoke("search_curriculum", make_ctx("student", 17), db, {"query": "normalization functional dependencies BCNF"})
    assert hits and {"chunk_id", "document", "section", "page", "excerpt"} <= set(hits[0])
    assert all(h["section"] != STRUCTURE_SECTION for h in hits)
    top = hits[0]
    assert "Unit 3" in top["section"] and top["parent"].startswith("24CS202T Database Management Systems")


# --- retrieval-tool hits become citable passages in a turn -------------------------------------

def test_merge_passages_dedupes_by_chunk_id_and_keeps_order():
    runs = [
        ToolRun("get_my_courses", {}, "| a |"),
        ToolRun("search_curriculum", {"query": "x"}, "| t |", passages=[{"chunk_id": 2, "excerpt": "b"}, {"chunk_id": 3, "excerpt": "c"}]),
    ]
    merged = _merge_passages([{"chunk_id": 1, "excerpt": "a"}, {"chunk_id": 2, "excerpt": "dup"}], runs)
    assert [p["chunk_id"] for p in merged] == [1, 2, 3] and merged[1]["excerpt"] == "dup"


def test_a_planned_search_curriculum_call_feeds_passages_not_a_table(db):
    route = LLMResponse(
        text=json.dumps({"intent": "syllabus", "candidate_tools": ["search_curriculum", "get_my_courses"], "needs_rag": False}),
        usage=Usage(100, 20),
    )
    plan = LLMResponse(
        text="",
        tool_calls=[
            ToolCall(id="1", name="search_curriculum", arguments={"query": "normalization functional dependencies"}),
            ToolCall(id="2", name="get_my_courses", arguments={}),
        ],
        usage=Usage(200, 30),
    )
    provider = ScriptedProvider(route, plan, LLMResponse(text="Unit 3 covers normalisation [[cite:{cid}]]."))
    out = run_turn(question="which unit covers normalisation?", ctx=make_ctx("student", 17), db=db, provider=provider)
    prompt = provider.calls[-1]["messages"][-1]["content"]
    assert "### get_my_courses" in prompt and "### search_curriculum" not in prompt
    assert "(course record: 24CS202T Database Management Systems | L-T-P 3-0-0, 3 credits)" in prompt
    assert prompt.count("[[cite:") >= 1
    assert [r.name for r in out.tool_runs] == ["search_curriculum", "get_my_courses"]


def test_get_course_syllabus_resolves_the_abbreviations_students_use(db):
    """Live finding: 'what's in Unit 3 of DBMS?' -> 'no course matching DBMS'."""
    ctx = make_ctx("student", 17)  # CP
    for abbr, title in [("DBMS", "Database Management Systems"), ("dld", "Digital Logic and Design"),
                        ("OS", "Operating System"), ("TOC", "Theory of Computation"),
                        ("COA", "Computer Organization and Architecture")]:
        r = REGISTRY.invoke("get_course_syllabus", ctx, db, {"course": abbr, "unit": 3})
        assert r.get("course", "").endswith(title) and r["department"] == "CP", (abbr, r)
        assert r["unit"].startswith("Unit 3:")
        assert r["passages"] and r["passages"][0]["chunk_id"] and "Unit 3" in r["passages"][0]["excerpt"]
    assert REGISTRY.invoke("get_course_syllabus", ctx, db, {"course": "XQZV"})["error"].startswith("no course")
