"""Subsystem 4 & 5 — Attendance tracking; assessments, marks, submissions, exams."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
)

from app.db.base import Base


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id = Column(Integer, primary_key=True)
    offering_id = Column(Integer, ForeignKey("course_offerings.id"), nullable=False, index=True)
    subject_code = Column(String, nullable=True)
    session_date = Column(Date, nullable=False)
    slot_no = Column(Integer, nullable=True)
    marked_by = Column(Integer, ForeignKey("faculty.id"), nullable=True)
    marked_at = Column(DateTime, nullable=True)
    topic_no = Column(Integer, nullable=True)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        Index("ix_attendance_records_student_session", "student_id", "session_id"),
    )

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    status = Column(String, nullable=False)  # present | absent | late | excused_leave


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True)
    offering_id = Column(Integer, ForeignKey("course_offerings.id"), nullable=False, index=True)
    subject_code = Column(String, nullable=True)
    term = Column(String, nullable=True)
    type = Column(String, nullable=False)  # Quiz-1, Assignment, Mid-Sem, Internal Test, ...
    title = Column(String, nullable=True)
    max_marks = Column(Numeric(6, 2), nullable=True)
    weightage_pct = Column(Numeric(5, 2), nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(String, nullable=True)  # scheduled | completed | graded


class Mark(Base):
    __tablename__ = "marks"

    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    score = Column(Numeric(6, 2), nullable=True)
    is_absent = Column(Boolean, nullable=False, default=False)
    graded_on = Column(Date, nullable=True)


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    status = Column(String, nullable=False)  # submitted | missing | late
    submitted_at = Column(DateTime, nullable=True)


class ResultSemester(Base):
    __tablename__ = "results_semester"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    roll_no = Column(String, nullable=False)
    term = Column(String, nullable=False)
    semester = Column(Integer, nullable=False)
    credits_registered = Column(Integer, nullable=True)
    credits_earned = Column(Integer, nullable=True)
    sgpa = Column(Numeric(4, 2), nullable=True)
    cgpa = Column(Numeric(4, 2), nullable=True)
    result_status = Column(String, nullable=True)  # Pass | Fail
    backlogs = Column(Integer, nullable=True)
    declared_on = Column(Date, nullable=True)


class ExamSchedule(Base):
    __tablename__ = "exam_schedule"

    id = Column(Integer, primary_key=True)
    term = Column(String, nullable=False)
    exam_type = Column(String, nullable=False)  # Mid-Sem | End-Sem
    subject_code = Column(String, nullable=False)
    subject_name = Column(String, nullable=True)
    dept_code = Column(String, nullable=True)
    semester = Column(Integer, nullable=True)
    exam_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True)
    status = Column(String, nullable=True)
