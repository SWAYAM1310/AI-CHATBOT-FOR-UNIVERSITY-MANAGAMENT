"""Subsystem 2 & 3 — Academic catalog, infrastructure, course operations, timetable."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
)

from app.db.base import Base


class Subject(Base):
    __tablename__ = "subjects"

    subject_code = Column(String, primary_key=True)
    subject_name = Column(String, nullable=False)
    category = Column(String, nullable=True)  # BSC, ESC, PCC, PEC, OEC, HSC
    component = Column(String, nullable=True)  # Theory, Practical/Lab, Project
    lecture_hours = Column(Integer, nullable=True)
    tutorial_hours = Column(Integer, nullable=True)
    practical_hours = Column(Integer, nullable=True)
    credits = Column(Numeric(3, 1), nullable=True)


class Curriculum(Base):
    __tablename__ = "curriculum"

    id = Column(Integer, primary_key=True)
    dept_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    dept_code = Column(String, nullable=False)
    semester = Column(Integer, nullable=False)
    subject_code = Column(String, ForeignKey("subjects.subject_code"), nullable=False)
    subject_name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    is_elective = Column(Boolean, nullable=False, default=False)


class Classroom(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True)
    code = Column(String, nullable=False, unique=True)
    building = Column(String, nullable=True)
    capacity = Column(Integer, nullable=True)
    room_type = Column(String, nullable=True)
    dept_id = Column(Integer, ForeignKey("departments.id"), nullable=True)


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"

    id = Column(Integer, primary_key=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False, index=True)
    dept_code = Column(String, nullable=True)
    subject_code = Column(String, ForeignKey("subjects.subject_code"), nullable=False)
    subject_name = Column(String, nullable=True)
    batch = Column(Integer, nullable=True)
    semester = Column(Integer, nullable=True)
    session_type = Column(String, nullable=True)
    division = Column(String, nullable=True)
    lab_group = Column(String, nullable=True)


class CourseOffering(Base):
    __tablename__ = "course_offerings"

    id = Column(Integer, primary_key=True)
    subject_code = Column(String, ForeignKey("subjects.subject_code"), nullable=False, index=True)
    subject_name = Column(String, nullable=False)
    dept_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    dept_code = Column(String, nullable=False)
    term = Column(String, nullable=False, index=True)
    semester = Column(Integer, nullable=False)
    batch = Column(Integer, nullable=False)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False, index=True)
    session_type = Column(String, nullable=True)
    division = Column(String, nullable=True)
    lab_group = Column(String, nullable=True)
    capacity = Column(Integer, nullable=True)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        Index("ix_enrollments_offering_student", "offering_id", "student_id"),
    )

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    offering_id = Column(Integer, ForeignKey("course_offerings.id"), nullable=False)
    subject_code = Column(String, ForeignKey("subjects.subject_code"), nullable=False)
    term = Column(String, nullable=False)
    status = Column(String, nullable=False)  # enrolled | completed | dropped
    enrolled_on = Column(Date, nullable=True)


class TimetableSlot(Base):
    __tablename__ = "timetable_slots"

    id = Column(Integer, primary_key=True)
    offering_id = Column(Integer, ForeignKey("course_offerings.id"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Mon ... 5=Sat
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=True)
    session_type = Column(String, nullable=True)
