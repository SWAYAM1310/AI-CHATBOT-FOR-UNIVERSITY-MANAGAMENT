"""Subsystem 6 — Student life & administrative operations."""
from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)

from app.db.base import Base


class Fee(Base):
    __tablename__ = "fees"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    roll_no = Column(String, nullable=False)
    term = Column(String, nullable=False)
    amount_due = Column(Numeric(12, 2), nullable=True)
    amount_paid = Column(Numeric(12, 2), nullable=True)
    status = Column(String, nullable=False)  # paid | partial | unpaid | overdue
    due_date = Column(Date, nullable=True)
    paid_on = Column(Date, nullable=True)


class Scholarship(Base):
    __tablename__ = "scholarships"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    roll_no = Column(String, nullable=False)
    name = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=True)
    term = Column(String, nullable=True)
    status = Column(String, nullable=False)  # approved | pending | rejected | disbursed
    applied_on = Column(Date, nullable=True)
    decided_on = Column(Date, nullable=True)


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    roll_no = Column(String, nullable=False)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String, nullable=False)  # pending | approved | rejected
    applied_on = Column(Date, nullable=True)
    decided_by = Column(Integer, ForeignKey("faculty.id"), nullable=True)
    decided_on = Column(Date, nullable=True)


class DocumentRequest(Base):
    __tablename__ = "document_requests"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    roll_no = Column(String, nullable=False)
    doc_type = Column(String, nullable=False)
    purpose = Column(Text, nullable=True)
    status = Column(String, nullable=False)  # processing | ready | collected | rejected
    requested_on = Column(Date, nullable=True)
    ready_on = Column(Date, nullable=True)


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True)
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scope = Column(String, nullable=False)  # university | department | course
    scope_ref = Column(String, nullable=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    audience_roles = Column(String, nullable=True)  # CSV mirror: "student,faculty,admin"
    posted_at = Column(DateTime, nullable=True)


class AcademicCalendarEvent(Base):
    __tablename__ = "academic_calendar"

    id = Column(Integer, primary_key=True)
    event = Column(String, nullable=False)
    event_type = Column(String, nullable=False)  # term | exam | holiday | registration | ...
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    applies_to = Column(String, nullable=True)  # all | faculty | student
    term = Column(String, nullable=True)
    # populated by the Phase-3 RAG ingest; nullable FK resolved with use_alter
    source_chunk_id = Column(
        Integer,
        ForeignKey("doc_chunks.id", use_alter=True, name="fk_academic_calendar_source_chunk_id"),
        nullable=True,
    )
