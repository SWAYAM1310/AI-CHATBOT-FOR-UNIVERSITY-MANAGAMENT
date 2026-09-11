"""Phase 3 step 5a — the structure-first curriculum chunker and per-course late chunking.

Pure-function tests on hand-written record text in the position-sorted layout
the parser sees, plus one real syllabus (the CP PDF: the demo course lives
there) to pin segmentation against the source. The other five PDFs were
surveyed at build time; parsing 500 pages is for the CLI, not the suite.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.rag.chunkers import CHUNKERS
from app.ai.rag.chunkers.curriculum import curriculum_chunks, parse_courses
from app.ai.rag.embedder import FakeEmbedder
from app.ai.rag.ingest import ChunkDraft, _embed
from app.ai.rag.manifest import load_manifest
from app.ai.rag.parsers import Page, ParsedDocument, parse_pdf

CP_PDF = next(e for e in load_manifest() if e.dept_code == "CP" and e.doc_type == "curriculum")

RECORD = """
Pandit Deendayal Energy University School of Technology
24CS202T Database Management Systems
Teaching Scheme Examination Scheme
Theory Practical
L T P C Hrs./Week Total Marks
MS ES IA LW LE/Viva
3 0 0 3 3 25 50 25 -- -- 100
COURSE OBJECTIVES
 To learn fundamental concepts of Database management system
 To study various Database design models and normalization
concepts
UNIT I: INTRODUCTION AND DATABASE MODELS 10 Hrs.
File Structure: Concepts of fields, records and files.
UNIT II: SQL
10 Hrs.
Basics of SQL, DDL, DML, DCL.
UNIT III: NORMALIZATION
Functional dependency, 1NF to BCNF.
TOTAL HOURS: 30 Hrs.
COURSE OUTCOMES
On completion of the course, student will be able to:
CO1 : Understand the need of database management systems.
CO2
: Explain entity relationship and relational database models.
TEXT/REFERENCE BOOKS
1. A Silberschatz, H F Korth and S Sudarshan, Database System Concepts, McGraw Hill.
2. C. J. Date, An Introduction to Database Systems,
Pearson Education.
"""


def _doc(*pages: str) -> ParsedDocument:
    return ParsedDocument(path=Path("x.pdf"), pages=[Page(number=i, text=t.strip()) for i, t in enumerate(pages, 1)])


@pytest.fixture(scope="module")
def entry():
    return CP_PDF


def test_registered_for_curriculum_documents():
    assert CHUNKERS["curriculum"] is curriculum_chunks


# --- one record, every field ------------------------------------------------------

def test_a_record_parses_into_all_its_fields():
    _, (rec,) = parse_courses(_doc(RECORD))
    assert (rec.code, rec.title, rec.page) == ("24CS202T", "Database Management Systems", 1)
    assert (rec.lecture, rec.tutorial, rec.practical, rec.credits) == (3, 0, 0, 3.0)
    assert rec.objectives == [
        "To learn fundamental concepts of Database management system",
        "To study various Database design models and normalization concepts",  # wrap glued, bullet stripped
    ]
    assert [(u.number, u.title, u.hours) for u in rec.units] == [
        (1, "INTRODUCTION AND DATABASE MODELS", 10),  # hours on the heading line
        (2, "SQL", 10),  # hours on their own line
        (3, "NORMALIZATION", None),
    ]
    assert rec.units[2].body == "Functional dependency, 1NF to BCNF."
    assert rec.outcomes == [
        (1, "Understand the need of database management systems."),
        (2, "Explain entity relationship and relational database models."),  # label split over lines
    ]
    assert rec.books == [
        "A Silberschatz, H F Korth and S Sudarshan, Database System Concepts, McGraw Hill.",
        "C. J. Date, An Introduction to Database Systems, Pearson Education.",  # wrapped entry glued
    ]


def test_numbered_outcomes_without_co_labels_and_experiment_lists():
    text = """
24CS302P Computer Networks Laboratory
Teaching Scheme Examination Scheme
0 0 2 1 2 - - - 25 25 50
COURSE OBJECTIVES
1. To design LAN topologies
SR. LIST OF EXPERIMENTS
1. Study of network devices.
2. Configure a switch.
COURSE OUTCOMES
On completion of the course, students will be able to:
1. Understand networking devices.
2. Configure switches and routers.
"""
    _, (rec,) = parse_courses(_doc(text))
    assert (rec.credits, rec.practical) == (1.0, 2)
    assert [(u.number, u.title) for u in rec.units] == [(1, "List of experiments")]
    assert rec.units[0].body == "1. Study of network devices. 2. Configure a switch."
    assert rec.outcomes == [(1, "Understand networking devices."), (2, "Configure switches and routers.")]


# --- headers: codes, placeholders, wrapped titles ---------------------------------

@pytest.mark.parametrize(
    ("head", "code", "title"),
    [
        ("24MA101T Mathematics – I", "24MA101T", "Mathematics – I"),
        ("Applied Physics (For CS, ICT, ECE,\n24PH101T EE)", "24PH101T", "Applied Physics (For CS, ICT, ECE, EE)"),
        ("Data Warehousing and Data Mining\n24CS331T", "24CS331T", "Data Warehousing and Data Mining"),
        ("<Course Code> Electronic Devices and Circuits", None, "Electronic Devices and Circuits"),
        ("24ICxxxT Digital Circuits", None, "Digital Circuits"),
        ("24ECE***T Digital Signal Processing", None, "Digital Signal Processing"),
        ("< Database Management Systems >", None, "Database Management Systems"),
        ("Intro to Programming Laboratory (For ME, CL, CH,\n<Course Code>\nBT)", None,
         "Intro to Programming Laboratory (For ME, CL, CH, BT)"),
        ("5. Some book, Some publisher.\nEnvironmental Science", None, "Environmental Science"),  # no code at all
    ],
)
def test_header_variants(head, code, title):
    text = f"{head}\nTeaching Scheme Examination Scheme\n2 0 0 2 2 25 50 25 -- -- 100\nCOURSE OBJECTIVES\nTo learn."
    _, (rec,) = parse_courses(_doc(text))
    assert (rec.code, rec.title) == (code, title)


def test_structure_table_headers_are_not_records_and_stay_in_the_preface():
    text = "COURSE STRUCTURE SEM I\nCourse Name\nTeaching Scheme Examination Scheme\n24MA101T Mathematics 3 1 0 4\n" + RECORD.strip()
    preface, records = parse_courses(_doc(text))
    assert [r.code for r in records] == ["24CS202T"]
    assert [t for _, t in preface][:3] == ["COURSE STRUCTURE SEM I", "Course Name", "Teaching Scheme Examination Scheme"]


def test_records_are_split_at_the_next_header_and_keep_their_pages():
    second = "24CS203T Data Structures\nTeaching Scheme Examination Scheme\n3 0 0 3 3 25 50 25 -- -- 100\nCOURSE OBJECTIVES\nTo learn.\nUNIT I: ARRAYS 8 Hrs.\nArrays and lists."
    _, records = parse_courses(_doc(RECORD, second))
    assert [(r.code, r.page) for r in records] == [("24CS202T", 1), ("24CS203T", 2)]
    assert records[0].books[-1].endswith("Pearson Education.")  # the first record did not swallow the second
    assert records[1].units[0].page == 2


def test_page_furniture_is_dropped():
    text = "Academic year: 2024-2025\nB. Tech. Mechanical Engineering\nSemester – VI\n" + RECORD.strip()
    preface, records = parse_courses(_doc(text))
    assert preface == [] and records[0].code == "24CS202T"


# --- chunk assembly ----------------------------------------------------------------

def test_parent_and_children_with_labels_pages_and_parent_links(entry):
    chunks = curriculum_chunks(_doc(RECORD), entry)
    assert [c.section for c in chunks] == [
        "24CS202T Database Management Systems",
        "24CS202T Database Management Systems / Unit 1: INTRODUCTION AND DATABASE MODELS",
        "24CS202T Database Management Systems / Unit 2: SQL",
        "24CS202T Database Management Systems / Unit 3: NORMALIZATION",
        "24CS202T Database Management Systems / Course outcomes",
        "24CS202T Database Management Systems / Books",
    ]
    parent, *children = chunks
    assert parent.parent is None and all(c.parent == 0 for c in children)
    assert parent.content.startswith("24CS202T Database Management Systems\nL-T-P 3-0-0, 3 credits\nCourse objectives:\n- To learn")
    assert "Units: 1. INTRODUCTION AND DATABASE MODELS; 2. SQL; 3. NORMALIZATION" in parent.content
    assert children[0].content == (
        "24CS202T Database Management Systems / Unit 1: INTRODUCTION AND DATABASE MODELS (10 hrs)\n"
        "File Structure: Concepts of fields, records and files."
    )
    assert children[3].content.startswith("24CS202T Database Management Systems / Course outcomes\nCO1: Understand")
    assert children[4].content.endswith("2. C. J. Date, An Introduction to Database Systems, Pearson Education.")
    assert all(c.page == 1 for c in chunks)


def test_preface_pages_become_programme_structure_chunks(entry):
    text = "COURSE STRUCTURE SEM I\n24MA101T Mathematics 3 1 0 4"
    chunks = curriculum_chunks(_doc(text, RECORD), entry)
    assert (chunks[0].section, chunks[0].page, chunks[0].parent) == ("Programme structure", 1, None)
    assert chunks[1].section == "24CS202T Database Management Systems" and chunks[1].page == 2


# --- ingest: late chunking per course ------------------------------------------------

def test_embedding_is_one_late_chunked_call_per_course_plus_a_batch_for_singles():
    fake = FakeEmbedder()
    drafts = [
        ChunkDraft("structure p1"), ChunkDraft("structure p2"),
        ChunkDraft("A"), ChunkDraft("A/u1", parent=2), ChunkDraft("A/u2", parent=2),
        ChunkDraft("B"), ChunkDraft("B/u1", parent=5),
    ]
    vectors = _embed(fake, "curriculum", drafts)
    assert len(vectors) == 7 and all(v is not None for v in vectors)
    assert fake.calls == 3  # A-family, B-family, one plain batch for the two structure pages
    assert vectors[3] == fake.embed_documents(["A/u1"])[0]  # vectors land in draft order


# --- the real CP syllabus --------------------------------------------------------------

@pytest.fixture(scope="module")
def cp_records():
    return parse_courses(parse_pdf(CP_PDF.path))


def test_cp_syllabus_segments_into_courses_with_full_records(cp_records):
    preface, records = cp_records
    assert len(records) == 88
    assert sum(r.code is not None for r in records) >= 86
    assert all(r.credits is not None and r.objectives and r.outcomes for r in records)
    assert sum(bool(r.units) for r in records) >= 84  # NSS/NCC/Yoga-style courses have no units
    assert all(r.books for r in records)
    assert all(r.title != "(untitled course)" and "<" not in r.title for r in records)
    assert {p for p, _ in preface} <= set(range(1, 10))  # structure tables come first


def test_the_demo_course_unit_3_is_a_child_of_dbms(cp_records):
    _, records = cp_records
    dbms = next(r for r in records if r.code == "24CS202T")
    assert dbms.title == "Database Management Systems" and dbms.scheme == "L-T-P 3-0-0, 3 credits"
    assert [u.number for u in dbms.units] == [1, 2, 3, 4]
    assert dbms.units[2].title.lower().startswith("normalization") and "functional" in dbms.units[2].body.lower()
    assert dbms.units[2].page == 35
    chunks = curriculum_chunks(parse_pdf(CP_PDF.path), CP_PDF)
    unit3 = next(c for c in chunks if c.section == f"{dbms.label} / Unit 3: {dbms.units[2].title}")
    assert chunks[unit3.parent].section == dbms.label
