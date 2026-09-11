"""Student SELF-scope read tools (plan.md §6).

All identity comes from AuthContext (ctx.student_id), never from args — Layer 3
of the registry strips any identity args a client tries to pass anyway.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.auth.context import AuthContext, Role
from app.ai.tools.registry import Scope, tool
from app.models import (
    Assessment,
    Classroom,
    CourseOffering,
    Enrollment,
    ExamSchedule,
    Fee,
    Faculty,
    LeaveRequest,
    Mark,
    ResultSemester,
    Scholarship,
    Student,
    Subject,
    Submission,
    TimetableSlot,
)


@tool(
    name="get_my_courses",
    description="Courses the calling student is enrolled in this term, with faculty and credits.",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
)
def get_my_courses(*, ctx: AuthContext, db: Session, **_: Any) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            CourseOffering.subject_code,
            CourseOffering.subject_name,
            CourseOffering.session_type,
            CourseOffering.division,
            Faculty.full_name.label("faculty_name"),
            Subject.credits,
        )
        .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
        .join(Faculty, Faculty.id == CourseOffering.faculty_id)
        .join(Subject, Subject.subject_code == CourseOffering.subject_code)
        .where(
            Enrollment.student_id == ctx.student_id,
            Enrollment.term == ctx.term,
            Enrollment.status == "enrolled",
        )
        .order_by(CourseOffering.subject_code)
    )
    return [
        {
            "course": r.subject_code,
            "name": r.subject_name,
            "faculty": r.faculty_name,
            "session_type": r.session_type,
            "division": r.division,
            "credits": float(r.credits) if r.credits is not None else None,
        }
        for r in rows
    ]


@tool(
    name="get_my_timetable",
    description="The calling student's weekly class timetable, optionally filtered to one day (0=Mon..5=Sat).",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
)
def get_my_timetable(*, ctx: AuthContext, db: Session, day: int | None = None, **_: Any) -> list[dict[str, Any]]:
    q = (
        select(
            TimetableSlot.day_of_week,
            TimetableSlot.start_time,
            TimetableSlot.end_time,
            TimetableSlot.session_type,
            CourseOffering.subject_code,
            CourseOffering.subject_name,
            Classroom.code.label("room"),
        )
        .join(CourseOffering, CourseOffering.id == TimetableSlot.offering_id)
        .join(Enrollment, Enrollment.offering_id == CourseOffering.id)
        .outerjoin(Classroom, Classroom.id == TimetableSlot.classroom_id)
        .where(
            Enrollment.student_id == ctx.student_id,
            Enrollment.term == ctx.term,
            Enrollment.status == "enrolled",
        )
    )
    if day is not None:
        q = q.where(TimetableSlot.day_of_week == day)
    q = q.order_by(TimetableSlot.day_of_week, TimetableSlot.start_time)
    return [
        {
            "day_of_week": r.day_of_week,
            "start_time": r.start_time.strftime("%H:%M"),
            "end_time": r.end_time.strftime("%H:%M"),
            "course": r.subject_code,
            "name": r.subject_name,
            "session_type": r.session_type,
            "room": r.room,
        }
        for r in db.execute(q)
    ]


@tool(
    name="get_my_marks",
    description="The calling student's marks for graded assessments this term, optionally filtered by assessment type.",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
)
def get_my_marks(
    *, ctx: AuthContext, db: Session, assessment_type: str | None = None, **_: Any
) -> list[dict[str, Any]]:
    q = (
        select(
            CourseOffering.subject_code,
            Assessment.type,
            Assessment.title,
            Mark.score,
            Assessment.max_marks,
            Mark.is_absent,
        )
        .join(Assessment, Assessment.id == Mark.assessment_id)
        .join(CourseOffering, CourseOffering.id == Assessment.offering_id)
        .where(Mark.student_id == ctx.student_id, Assessment.term == ctx.term)
    )
    if assessment_type:
        q = q.where(Assessment.type == assessment_type)
    q = q.order_by(CourseOffering.subject_code, Assessment.type)
    return [
        {
            "course": r.subject_code,
            "assessment_type": r.type,
            "title": r.title,
            "score": float(r.score) if r.score is not None else None,
            "max_marks": float(r.max_marks) if r.max_marks is not None else None,
            "is_absent": bool(r.is_absent),
        }
        for r in db.execute(q)
    ]


@tool(
    name="get_my_results",
    description="The calling student's declared semester results (SGPA/CGPA, credits, pass/fail), optionally filtered to one semester.",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
)
def get_my_results(*, ctx: AuthContext, db: Session, semester: int | None = None, **_: Any) -> list[dict[str, Any]]:
    q = select(ResultSemester).where(ResultSemester.student_id == ctx.student_id)
    if semester is not None:
        q = q.where(ResultSemester.semester == semester)
    q = q.order_by(ResultSemester.semester)
    return [
        {
            "term": r.term,
            "semester": r.semester,
            "credits_registered": r.credits_registered,
            "credits_earned": r.credits_earned,
            "sgpa": float(r.sgpa) if r.sgpa is not None else None,
            "cgpa": float(r.cgpa) if r.cgpa is not None else None,
            "result_status": r.result_status,
            "backlogs": r.backlogs,
        }
        for r in db.scalars(q)
    ]


@tool(
    name="get_my_exam_schedule",
    description="The calling student's exam schedule this term (subject, date, time, room).",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
)
def get_my_exam_schedule(*, ctx: AuthContext, db: Session, **_: Any) -> list[dict[str, Any]]:
    student = db.get(Student, ctx.student_id)
    q = (
        select(
            ExamSchedule.exam_type,
            ExamSchedule.subject_code,
            ExamSchedule.subject_name,
            ExamSchedule.exam_date,
            ExamSchedule.start_time,
            ExamSchedule.end_time,
            Classroom.code.label("room"),
        )
        .outerjoin(Classroom, Classroom.id == ExamSchedule.classroom_id)
        .where(
            ExamSchedule.term == ctx.term,
            ExamSchedule.dept_code == student.dept_code,
            ExamSchedule.semester == student.semester,
        )
        .order_by(ExamSchedule.exam_date)
    )
    return [
        {
            "exam_type": r.exam_type,
            "course": r.subject_code,
            "name": r.subject_name,
            "date": r.exam_date.isoformat(),
            "start_time": r.start_time.strftime("%H:%M") if r.start_time else None,
            "end_time": r.end_time.strftime("%H:%M") if r.end_time else None,
            "room": r.room,
        }
        for r in db.execute(q)
    ]


@tool(
    name="get_my_assignments",
    description="The calling student's assignments this term with submission status, optionally filtered by status (submitted/missing/late).",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
)
def get_my_assignments(*, ctx: AuthContext, db: Session, status: str | None = None, **_: Any) -> list[dict[str, Any]]:
    q = (
        select(
            CourseOffering.subject_code,
            Assessment.title,
            Assessment.due_date,
            Submission.status,
            Submission.submitted_at,
        )
        .join(CourseOffering, CourseOffering.id == Assessment.offering_id)
        .join(Submission, Submission.assessment_id == Assessment.id)
        .where(
            Submission.student_id == ctx.student_id,
            Assessment.type == "Assignment",
            Assessment.term == ctx.term,
        )
    )
    if status:
        q = q.where(Submission.status == status)
    q = q.order_by(Assessment.due_date)
    return [
        {
            "course": r.subject_code,
            "title": r.title,
            "due_date": r.due_date.isoformat() if r.due_date else None,
            "status": r.status,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        }
        for r in db.execute(q)
    ]


@tool(
    name="get_my_fees",
    description="The calling student's fee dues and payment status across terms.",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
)
def get_my_fees(*, ctx: AuthContext, db: Session, **_: Any) -> list[dict[str, Any]]:
    rows = db.scalars(select(Fee).where(Fee.student_id == ctx.student_id).order_by(desc(Fee.term)))
    return [
        {
            "term": r.term,
            "amount_due": float(r.amount_due) if r.amount_due is not None else None,
            "amount_paid": float(r.amount_paid) if r.amount_paid is not None else None,
            "status": r.status,
            "due_date": r.due_date.isoformat() if r.due_date else None,
            "paid_on": r.paid_on.isoformat() if r.paid_on else None,
        }
        for r in rows
    ]


@tool(
    name="get_my_scholarships",
    description="The calling student's scholarship applications and their status.",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
)
def get_my_scholarships(*, ctx: AuthContext, db: Session, **_: Any) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Scholarship).where(Scholarship.student_id == ctx.student_id).order_by(desc(Scholarship.applied_on))
    )
    return [
        {
            "name": r.name,
            "amount": float(r.amount) if r.amount is not None else None,
            "term": r.term,
            "status": r.status,
            "applied_on": r.applied_on.isoformat() if r.applied_on else None,
            "decided_on": r.decided_on.isoformat() if r.decided_on else None,
        }
        for r in rows
    ]


@tool(
    name="get_my_leave_requests",
    description="The calling student's leave requests and their approval status.",
    allowed_roles={Role.STUDENT},
    scope=Scope.SELF,
)
def get_my_leave_requests(*, ctx: AuthContext, db: Session, **_: Any) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(LeaveRequest).where(LeaveRequest.student_id == ctx.student_id).order_by(desc(LeaveRequest.applied_on))
    )
    return [
        {
            "from_date": r.from_date.isoformat(),
            "to_date": r.to_date.isoformat(),
            "reason": r.reason,
            "status": r.status,
            "applied_on": r.applied_on.isoformat() if r.applied_on else None,
            "decided_on": r.decided_on.isoformat() if r.decided_on else None,
        }
        for r in rows
    ]
