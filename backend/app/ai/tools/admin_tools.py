"""Admin UNIVERSITY read tools (plan.md §6).

Admins see everything, so the risk here is not leakage but *shape*: every tool
returns aggregates or a bounded, filterable list, never a dump. `run_analytics`
is the open-ended one, and it stays safe by construction — `metric` and
`group_by` each select from a fixed map of SQL expressions, so the model can
combine them freely but cannot name a column, table or predicate of its own.
An unknown value comes back as an `error` row listing what is allowed, so
Call C can explain rather than the turn failing.
"""
from __future__ import annotations

from datetime import date as _date, time as _time
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.ai.tools.builtin import PRESENT
from app.ai.tools.registry import Scope, tool
from app.auth.context import AuthContext, Role
from app.models import (
    Assessment,
    AttendanceRecord,
    AttendanceSession,
    Classroom,
    CourseOffering,
    Department,
    Enrollment,
    Faculty,
    Fee,
    Mark,
    ResultSemester,
    Student,
    TimetableSlot,
)

ADMIN = {Role.ADMIN}
PASS_PERCENT = 40  # Part V §3.1: the minimum on any component and on the course total
LIST_CAP = 100  # list_students is a lookup aid, not an export
ATTENDANCE_FLOOR = 75.0


def _num(v: Any, digits: int = 1) -> float | None:
    return round(float(v), digits) if v is not None else None


# --- per-student subqueries reused by several tools -------------------------

def _attendance_by_student(term: str):
    total = func.count(AttendanceRecord.id).label("total")
    attended = func.count(AttendanceRecord.id).filter(AttendanceRecord.status.in_(PRESENT)).label("attended")
    return (
        select(AttendanceRecord.student_id, attended, total)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .join(CourseOffering, CourseOffering.id == AttendanceSession.offering_id)
        .where(CourseOffering.term == term)
        .group_by(AttendanceRecord.student_id)
        .subquery()
    )


def _marks_by_student(term: str):
    scored = Mark.score.isnot(None) & Mark.is_absent.is_(False)
    pct = func.sum(Mark.score).filter(scored) * 100.0 / func.nullif(func.sum(Assessment.max_marks).filter(scored), 0)
    return (
        select(Mark.student_id, pct.label("pct"))
        .join(Assessment, Assessment.id == Mark.assessment_id)
        .where(Assessment.term == term)
        .group_by(Mark.student_id)
        .subquery()
    )


def _student_filters(dept: str | None, semester: int | None) -> list[Any]:
    clauses: list[Any] = [Student.is_active.is_(True)]
    if dept:
        clauses.append(Student.dept_code == dept.upper())
    if semester is not None:
        clauses.append(Student.semester == semester)
    return clauses


# --- tools -------------------------------------------------------------------

@tool(
    name="get_enrollment_stats",
    description="Active student headcount and average CGPA by department and semester; optionally one department and/or semester.",
    allowed_roles=ADMIN,
    scope=Scope.UNIVERSITY,
)
def get_enrollment_stats(
    *, ctx: AuthContext, db: Session, dept: str | None = None, semester: int | None = None, **_: Any
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            Student.dept_code,
            Student.semester,
            func.count(Student.id).label("students"),
            func.avg(Student.cgpa).label("avg_cgpa"),
            func.count(Student.id).filter(Student.is_hosteller.is_(True)).label("hostellers"),
        )
        .where(*_student_filters(dept, semester))
        .group_by(Student.dept_code, Student.semester)
        .order_by(Student.dept_code, Student.semester)
    )
    return [
        {
            "dept": r.dept_code,
            "semester": r.semester,
            "students": r.students,
            "avg_cgpa": _num(r.avg_cgpa, 2),
            "hostellers": r.hostellers,
        }
        for r in rows
    ]


@tool(
    name="get_department_overview",
    description="One row per department: name, HOD, active students, faculty, and course offerings this term.",
    allowed_roles=ADMIN,
    scope=Scope.UNIVERSITY,
)
def get_department_overview(*, ctx: AuthContext, db: Session, **_: Any) -> list[dict[str, Any]]:
    students = (
        select(func.count(Student.id))
        .where(Student.dept_id == Department.id, Student.is_active.is_(True))
        .scalar_subquery()
    )
    faculty = (
        select(func.count(Faculty.id))
        .where(Faculty.dept_id == Department.id, Faculty.is_active.is_(True))
        .scalar_subquery()
    )
    offerings = (
        select(func.count(CourseOffering.id))
        .where(CourseOffering.dept_id == Department.id, CourseOffering.term == ctx.term)
        .scalar_subquery()
    )
    hod = select(Faculty.full_name).where(Faculty.id == Department.hod_faculty_id).scalar_subquery()
    rows = db.execute(
        select(
            Department.code,
            Department.name,
            hod.label("hod"),
            students.label("students"),
            faculty.label("faculty"),
            offerings.label("offerings"),
        ).order_by(Department.code)
    )
    return [
        {
            "dept": r.code,
            "name": r.name,
            "hod": r.hod,
            "students": r.students,
            "faculty": r.faculty,
            "offerings_this_term": r.offerings,
        }
        for r in rows
    ]


@tool(
    name="get_course_performance",
    description="Per course this term: enrolled students, average attendance %, average marks % and failure rate % (students under the 40% pass mark on at least one graded component); filter by course code or department.",
    allowed_roles=ADMIN,
    scope=Scope.UNIVERSITY,
)
def get_course_performance(
    *, ctx: AuthContext, db: Session, course: str | None = None, dept: str | None = None, **_: Any
) -> list[dict[str, Any]]:
    scored = Mark.score.isnot(None) & Mark.is_absent.is_(False)
    attendance = (
        select(
            AttendanceSession.offering_id,
            (func.count(AttendanceRecord.id).filter(AttendanceRecord.status.in_(PRESENT)) * 100.0
             / func.nullif(func.count(AttendanceRecord.id), 0)).label("pct"),
        )
        .join(AttendanceRecord, AttendanceRecord.session_id == AttendanceSession.id)
        .group_by(AttendanceSession.offering_id)
        .subquery()
    )
    marks = (
        select(
            Assessment.offering_id,
            (func.sum(Mark.score).filter(scored) * 100.0
             / func.nullif(func.sum(Assessment.max_marks).filter(scored), 0)).label("pct"),
        )
        .join(Mark, Mark.assessment_id == Assessment.id)
        .group_by(Assessment.offering_id)
        .subquery()
    )
    enrolled = (
        select(func.count(Enrollment.id))
        .where(Enrollment.offering_id == CourseOffering.id, Enrollment.status == "enrolled")
        .scalar_subquery()
    )
    # Part V §3.1: 40% on EVERY component - a student is failing the course so far if any graded
    # component is under it (the course total alone hides a failed internal test)
    per_student = (
        select(
            Assessment.offering_id,
            Mark.student_id,
            func.min(Mark.score * 100.0 / func.nullif(Assessment.max_marks, 0)).filter(scored).label("pct"),
        )
        .join(Mark, Mark.assessment_id == Assessment.id)
        .group_by(Assessment.offering_id, Mark.student_id)
        .subquery()
    )
    failing = (
        select(
            per_student.c.offering_id,
            (func.count().filter(per_student.c.pct < PASS_PERCENT) * 100.0
             / func.nullif(func.count(per_student.c.pct), 0)).label("pct"),
        )
        .group_by(per_student.c.offering_id)
        .subquery()
    )
    q = (
        select(
            CourseOffering.subject_code,
            CourseOffering.subject_name,
            CourseOffering.dept_code,
            Faculty.full_name.label("faculty"),
            enrolled.label("enrolled"),
            attendance.c.pct.label("attendance"),
            marks.c.pct.label("marks"),
            failing.c.pct.label("failing"),
        )
        .join(Faculty, Faculty.id == CourseOffering.faculty_id)
        .outerjoin(attendance, attendance.c.offering_id == CourseOffering.id)
        .outerjoin(marks, marks.c.offering_id == CourseOffering.id)
        .outerjoin(failing, failing.c.offering_id == CourseOffering.id)
        .where(CourseOffering.term == ctx.term)
    )
    if course:
        q = q.where(CourseOffering.subject_code == course.upper())
    if dept:
        q = q.where(CourseOffering.dept_code == dept.upper())
    # worst first: a performance report is read for its problems, and compact() caps rows at 40
    q = q.order_by(failing.c.pct.desc().nulls_last(), marks.c.pct.asc().nulls_last(), CourseOffering.subject_code)
    return [
        {
            "course": r.subject_code,
            "name": r.subject_name,
            "dept": r.dept_code,
            "faculty": r.faculty,
            "enrolled": r.enrolled,
            "avg_attendance_percent": _num(r.attendance),
            "avg_marks_percent": _num(r.marks),
            "failure_rate_percent": _num(r.failing),
        }
        for r in db.execute(q)
    ]


@tool(
    name="list_students",
    description="Look up active students by department, semester, division, CGPA range or hosteller status (at most 100 rows).",
    allowed_roles=ADMIN,
    scope=Scope.UNIVERSITY,
)
def list_students(
    *,
    ctx: AuthContext,
    db: Session,
    dept: str | None = None,
    semester: int | None = None,
    division: str | None = None,
    min_cgpa: float | None = None,
    max_cgpa: float | None = None,
    hosteller: bool | None = None,
    **_: Any,
) -> list[dict[str, Any]]:
    clauses = _student_filters(dept, semester)
    if division:
        clauses.append(Student.division == division)
    if min_cgpa is not None:
        clauses.append(Student.cgpa >= min_cgpa)
    if max_cgpa is not None:
        clauses.append(Student.cgpa <= max_cgpa)
    if hosteller is not None:
        clauses.append(Student.is_hosteller.is_(hosteller))
    rows = db.scalars(
        select(Student).where(*clauses).order_by(Student.dept_code, Student.roll_no).limit(LIST_CAP)
    )
    return [
        {
            "roll_no": s.roll_no,
            "full_name": s.full_name,
            "dept": s.dept_code,
            "semester": s.semester,
            "division": s.division,
            "cgpa": _num(s.cgpa, 2),
            "hosteller": s.is_hosteller,
        }
        for s in rows
    ]


@tool(
    name="get_university_attendance_report",
    description="Attendance this term by department and semester: students tracked, average %, and how many are under the threshold (default 75).",
    allowed_roles=ADMIN,
    scope=Scope.UNIVERSITY,
)
def get_university_attendance_report(
    *,
    ctx: AuthContext,
    db: Session,
    dept: str | None = None,
    semester: int | None = None,
    threshold: float = ATTENDANCE_FLOOR,
    **_: Any,
) -> list[dict[str, Any]]:
    att = _attendance_by_student(ctx.term)
    pct = att.c.attended * 100.0 / func.nullif(att.c.total, 0)
    rows = db.execute(
        select(
            Student.dept_code,
            Student.semester,
            func.count(Student.id).label("students"),
            func.avg(pct).label("average"),
            func.count(Student.id).filter(pct < threshold).label("below"),
        )
        .join(att, att.c.student_id == Student.id)
        .where(*_student_filters(dept, semester))
        .group_by(Student.dept_code, Student.semester)
        .order_by(Student.dept_code, Student.semester)
    )
    return [
        {
            "dept": r.dept_code,
            "semester": r.semester,
            "students": r.students,
            "average_percent": _num(r.average),
            "below_threshold": r.below,
            "threshold": threshold,
        }
        for r in rows
    ]


@tool(
    name="get_faculty_workload",
    description="Teaching load per faculty member this term: offerings, weekly contact hours and students taught; optionally one department.",
    allowed_roles=ADMIN,
    scope=Scope.UNIVERSITY,
)
def get_faculty_workload(
    *, ctx: AuthContext, db: Session, dept: str | None = None, **_: Any
) -> list[dict[str, Any]]:
    hours = (
        select(
            CourseOffering.faculty_id,
            func.sum(
                func.extract("epoch", TimetableSlot.end_time) - func.extract("epoch", TimetableSlot.start_time)
            ).label("seconds"),
        )
        .join(TimetableSlot, TimetableSlot.offering_id == CourseOffering.id)
        .where(CourseOffering.term == ctx.term)
        .group_by(CourseOffering.faculty_id)
        .subquery()
    )
    students = (
        select(CourseOffering.faculty_id, func.count(func.distinct(Enrollment.student_id)).label("n"))
        .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
        .where(CourseOffering.term == ctx.term, Enrollment.status == "enrolled")
        .group_by(CourseOffering.faculty_id)
        .subquery()
    )
    offerings = (
        select(func.count(CourseOffering.id))
        .where(CourseOffering.faculty_id == Faculty.id, CourseOffering.term == ctx.term)
        .scalar_subquery()
    )
    q = (
        select(
            Faculty.employee_id,
            Faculty.full_name,
            Faculty.dept_code,
            Faculty.designation,
            offerings.label("offerings"),
            hours.c.seconds,
            students.c.n.label("students"),
        )
        .outerjoin(hours, hours.c.faculty_id == Faculty.id)
        .outerjoin(students, students.c.faculty_id == Faculty.id)
        .where(Faculty.is_active.is_(True))
    )
    if dept:
        q = q.where(Faculty.dept_code == dept.upper())
    q = q.order_by(Faculty.dept_code, Faculty.full_name)
    return [
        {
            "employee_id": r.employee_id,
            "full_name": r.full_name,
            "dept": r.dept_code,
            "designation": r.designation,
            "offerings": r.offerings,
            "weekly_hours": _num(float(r.seconds or 0) / 3600.0),
            "students": r.students or 0,
        }
        for r in db.execute(q)
    ]


@tool(
    name="find_available_classrooms",
    description="Classrooms free on a given date (YYYY-MM-DD) between start_time and end_time (HH:MM), per the weekly timetable; optionally one room type (Lecture Hall, Laboratory, Seminar Hall, Examination Hall).",
    allowed_roles=ADMIN,
    scope=Scope.UNIVERSITY,
)
def find_available_classrooms(
    *,
    ctx: AuthContext,
    db: Session,
    date: str,
    start_time: str,
    end_time: str,
    room_type: str | None = None,
    **_: Any,
) -> list[dict[str, Any]] | dict[str, Any]:
    try:
        day = _date.fromisoformat(date).weekday()
        start, end = _time.fromisoformat(start_time), _time.fromisoformat(end_time)
    except ValueError:
        return {"error": "date must be YYYY-MM-DD and times HH:MM"}
    if end <= start:
        return {"error": "end_time must be after start_time"}
    if day > 5:
        return []  # no timetable on Sundays — nothing is booked, but nothing runs either

    busy = (
        select(TimetableSlot.classroom_id)
        .join(CourseOffering, CourseOffering.id == TimetableSlot.offering_id)
        .where(
            CourseOffering.term == ctx.term,
            TimetableSlot.day_of_week == day,
            TimetableSlot.start_time < end,
            TimetableSlot.end_time > start,  # overlap
            TimetableSlot.classroom_id.isnot(None),
        )
    )
    q = select(Classroom).where(Classroom.id.not_in(busy))
    if room_type:
        q = q.where(Classroom.room_type.ilike(room_type))
    q = q.order_by(Classroom.building, Classroom.code)
    return [
        {"room": c.code, "building": c.building, "type": c.room_type, "capacity": c.capacity}
        for c in db.scalars(q)
    ]


@tool(
    name="get_fee_collection_summary",
    description="Fee collection by department for a term (default: current): billed, collected, outstanding and counts by status; optionally one department.",
    allowed_roles=ADMIN,
    scope=Scope.UNIVERSITY,
)
def get_fee_collection_summary(
    *, ctx: AuthContext, db: Session, dept: str | None = None, term: str | None = None, **_: Any
) -> list[dict[str, Any]]:
    q = (
        select(
            Student.dept_code,
            func.count(Fee.id).label("bills"),
            func.sum(Fee.amount_due).label("due"),
            func.sum(Fee.amount_paid).label("paid"),
            func.count(Fee.id).filter(Fee.status == "paid").label("n_paid"),
            func.count(Fee.id).filter(Fee.status == "partial").label("n_partial"),
            func.count(Fee.id).filter(Fee.status == "unpaid").label("n_unpaid"),
            func.count(Fee.id).filter(Fee.status == "overdue").label("n_overdue"),
        )
        .join(Student, Student.id == Fee.student_id)
        .where(Fee.term == (term or ctx.term))
        .group_by(Student.dept_code)
        .order_by(Student.dept_code)
    )
    if dept:
        q = q.where(Student.dept_code == dept.upper())
    return [
        {
            "dept": r.dept_code,
            "term": term or ctx.term,
            "bills": r.bills,
            "billed": _num(r.due, 2),
            "collected": _num(r.paid, 2),
            "outstanding": _num((r.due or 0) - (r.paid or 0), 2),
            "collection_rate_percent": _num(float(r.paid or 0) * 100 / float(r.due)) if r.due else None,
            "paid": r.n_paid,
            "partial": r.n_partial,
            "unpaid": r.n_unpaid,
            "overdue": r.n_overdue,
        }
        for r in db.execute(q)
    ]


# --- run_analytics: bounded aggregation ------------------------------------

GROUP_BY = {
    "department": Student.dept_code,
    "semester": Student.semester,
    "batch": Student.batch,
    "division": Student.division,
}

METRICS = (
    "student_count",
    "average_cgpa",
    "average_attendance",
    "average_marks_percent",
    "fee_collection_rate",
    "backlog_count",
    "failure_rate",  # % of declared semester results not passed (Fail / ATKT) — the plan.md §11 Phase-4 demo
)


@tool(
    name="run_analytics",
    description=(
        "Aggregate one metric (student_count, average_cgpa, average_attendance, average_marks_percent, "
        "fee_collection_rate, backlog_count, failure_rate) grouped by department, semester, batch or division; "
        "optionally filtered to one department and/or semester."
    ),
    allowed_roles=ADMIN,
    scope=Scope.UNIVERSITY,
)
def run_analytics(
    *,
    ctx: AuthContext,
    db: Session,
    metric: str,
    group_by: str,
    dept: str | None = None,
    semester: int | None = None,
    **_: Any,
) -> list[dict[str, Any]] | dict[str, Any]:
    metric, group_by = metric.strip().lower(), group_by.strip().lower()
    if metric not in METRICS:
        return {"error": f"unknown metric {metric!r}; allowed: {', '.join(METRICS)}"}
    if group_by not in GROUP_BY:
        return {"error": f"unknown group_by {group_by!r}; allowed: {', '.join(GROUP_BY)}"}

    key = GROUP_BY[group_by]
    q = select(key.label("group")).where(*_student_filters(dept, semester))

    if metric == "student_count":
        q = q.add_columns(func.count(Student.id).label("value"))
    elif metric == "average_cgpa":
        q = q.add_columns(func.avg(Student.cgpa).label("value"))
    elif metric == "average_attendance":
        att = _attendance_by_student(ctx.term)
        pct = att.c.attended * 100.0 / func.nullif(att.c.total, 0)
        q = q.join(att, att.c.student_id == Student.id).add_columns(func.avg(pct).label("value"))
    elif metric == "average_marks_percent":
        marks = _marks_by_student(ctx.term)
        q = q.join(marks, marks.c.student_id == Student.id).add_columns(func.avg(marks.c.pct).label("value"))
    elif metric == "fee_collection_rate":
        q = q.join(Fee, and_(Fee.student_id == Student.id, Fee.term == ctx.term)).add_columns(
            (func.sum(Fee.amount_paid) * 100.0 / func.nullif(func.sum(Fee.amount_due), 0)).label("value")
        )
    elif metric == "backlog_count":
        q = q.join(ResultSemester, ResultSemester.student_id == Student.id).add_columns(
            func.coalesce(func.sum(ResultSemester.backlogs), 0).label("value")
        )
    else:  # failure_rate: results not passed (Fail, ATKT) as a percentage of all declared results in the group
        failed = func.count(ResultSemester.id).filter(func.lower(ResultSemester.result_status) != "pass")
        q = q.join(ResultSemester, ResultSemester.student_id == Student.id).add_columns(
            (failed * 100.0 / func.nullif(func.count(ResultSemester.id), 0)).label("value")
        )

    rows = db.execute(q.group_by(key).order_by(key))
    digits = 0 if metric in ("student_count", "backlog_count") else 2
    return [
        {
            "metric": metric,
            group_by: r.group,
            "value": int(r.value) if digits == 0 and r.value is not None else _num(r.value, digits),
        }
        for r in rows
    ]
