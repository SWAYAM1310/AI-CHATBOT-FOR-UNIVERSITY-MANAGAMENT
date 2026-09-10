"""Phase 1a verification — the sample dataset loads faithfully and the planted
demo cases resolve. See plan.md §12 / the plan file's step 7.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.seed.load_csv import LOAD_ORDER
from tests.conftest import csv_row_count


@pytest.mark.parametrize("table", LOAD_ORDER)
def test_row_count_matches_csv(conn, table):
    db = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
    assert db == csv_row_count(table), f"{table}: db={db} csv={csv_row_count(table)}"


@pytest.mark.parametrize(
    ("child", "fk", "parent", "pk"),
    [
        ("enrollments", "offering_id", "course_offerings", "id"),
        ("attendance_records", "session_id", "attendance_sessions", "id"),
        ("marks", "assessment_id", "assessments", "id"),
        ("course_offerings", "faculty_id", "faculty", "id"),
        ("attendance_records", "student_id", "students", "id"),
        ("timetable_slots", "offering_id", "course_offerings", "id"),
    ],
)
def test_no_orphan_fks(conn, child, fk, parent, pk):
    orphans = conn.execute(
        text(
            f'SELECT count(*) FROM "{child}" c '
            f'LEFT JOIN "{parent}" p ON c.{fk} = p.{pk} '
            f"WHERE c.{fk} IS NOT NULL AND p.{pk} IS NULL"
        )
    ).scalar_one()
    assert orphans == 0


def test_identity_sequences_advanced(conn):
    # a fresh nextval must exceed the current MAX(id), i.e. loader bumped setval
    for table in ("students", "enrollments", "marks"):
        max_id = conn.execute(text(f'SELECT max(id) FROM "{table}"')).scalar_one()
        nxt = conn.execute(
            text(f"SELECT nextval(pg_get_serial_sequence('{table}', 'id'))")
        ).scalar_one()
        assert nxt > max_id


def test_department_hods_patched(conn):
    unpatched = conn.execute(
        text("SELECT count(*) FROM departments WHERE hod_faculty_id IS NULL")
    ).scalar_one()
    assert unpatched == 0


# --- planted demo edge cases (data/synthetic/sample/README.md) ---


def test_planted_attendance_68pct(conn):
    row = conn.execute(
        text(
            """
            SELECT
              count(*) FILTER (WHERE ar.status IN ('present', 'excused_leave'))::float
              / count(*) * 100 AS pct,
              count(*) AS total
            FROM students s
            JOIN attendance_records ar ON ar.student_id = s.id
            JOIN attendance_sessions ses ON ses.id = ar.session_id
            JOIN course_offerings co ON co.id = ses.offering_id
            WHERE s.roll_no = '25BCP017' AND co.subject_code = '24CS201T'
            """
        )
    ).one()
    assert row.total > 0
    assert 60 <= row.pct <= 75, f"expected ~68%, got {row.pct:.1f}%"


def test_planted_fail_rate_24cs202t(conn):
    row = conn.execute(
        text(
            """
            SELECT
              count(*) FILTER (WHERE m.score < 0.4 * a.max_marks)::float
              / count(*) * 100 AS fail_pct,
              count(*) AS graded
            FROM assessments a
            JOIN course_offerings co ON co.id = a.offering_id
            JOIN marks m ON m.assessment_id = a.id
            WHERE co.subject_code = '24CS202T'
              AND a.type ILIKE '%internal%1%'
              AND m.score IS NOT NULL
            """
        )
    ).one()
    assert row.graded > 0
    assert 20 <= row.fail_pct <= 50, f"expected ~35%, got {row.fail_pct:.1f}%"


def test_planted_unpaid_fee_and_pending_scholarship(conn):
    fee = conn.execute(
        text(
            "SELECT count(*) FROM fees f JOIN students s ON s.id = f.student_id "
            "WHERE s.roll_no = '25BCP012' AND f.status IN ('unpaid', 'overdue')"
        )
    ).scalar_one()
    sch = conn.execute(
        text(
            "SELECT count(*) FROM scholarships sc JOIN students s ON s.id = sc.student_id "
            "WHERE s.roll_no = '25BCP012' AND sc.status = 'pending'"
        )
    ).scalar_one()
    assert fee > 0 and sch > 0


def test_planted_pending_leaves(conn):
    n = conn.execute(
        text(
            "SELECT count(DISTINCT s.roll_no) FROM leave_requests lr "
            "JOIN students s ON s.id = lr.student_id "
            "WHERE lr.status = 'pending' AND s.roll_no IN ('25BCP003', '25BCP021', '25BIT004')"
        )
    ).scalar_one()
    assert n == 3
