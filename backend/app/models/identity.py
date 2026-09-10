"""Subsystem 1 — Identity, RBAC & core organization.

Columns mirror data/synthetic/sample/*.csv headers exactly (denormalised mirror
columns like dept_code are kept as-is; the CSV is authoritative). See SCHEMA_MAP.md.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # student | faculty | admin
    subject_ref = Column(String, nullable=False)  # e.g. "student:1", "faculty:5"
    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime, nullable=True)


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    code = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    building = Column(String, nullable=True)
    # circular with faculty.dept_id -> resolved with use_alter
    hod_faculty_id = Column(
        Integer,
        ForeignKey("faculty.id", use_alter=True, name="fk_departments_hod_faculty_id"),
        nullable=True,
    )


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    roll_no = Column(String, nullable=False, unique=True, index=True)
    full_name = Column(String, nullable=False)
    university_email = Column(String, nullable=False, index=True)
    personal_email = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    phone = Column(String, nullable=True)
    address_city = Column(String, nullable=True)
    address_state = Column(String, nullable=True)
    dept_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)
    dept_code = Column(String, nullable=False)
    batch = Column(Integer, nullable=False)
    semester = Column(Integer, nullable=False)
    division = Column(String, nullable=True)
    lab_group = Column(String, nullable=True)
    tenth_percentage = Column(Numeric(5, 2), nullable=True)
    twelfth_percentage = Column(Numeric(5, 2), nullable=True)
    cgpa = Column(Numeric(4, 2), nullable=True)
    is_hosteller = Column(Boolean, nullable=True)
    guardian_name = Column(String, nullable=True)
    guardian_phone = Column(String, nullable=True)
    admission_date = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class Faculty(Base):
    __tablename__ = "faculty"

    id = Column(Integer, primary_key=True)
    employee_id = Column(String, nullable=False, unique=True)
    full_name = Column(String, nullable=False)
    university_email = Column(String, nullable=False, index=True)
    personal_email = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    phone = Column(String, nullable=True)
    dept_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)
    dept_code = Column(String, nullable=False)
    designation = Column(String, nullable=True)
    is_hod = Column(Boolean, nullable=False, default=False)
    date_of_joining = Column(Date, nullable=True)
    qualification = Column(String, nullable=True)
    specialization = Column(String, nullable=True)
    office_room = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True)
    employee_id = Column(String, nullable=False, unique=True)
    full_name = Column(String, nullable=False)
    university_email = Column(String, nullable=False, index=True)
    personal_email = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    phone = Column(String, nullable=True)
    designation = Column(String, nullable=True)
    date_of_joining = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
