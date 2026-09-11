"""Curriculum extracted relationally from the syllabus PDFs (plan.md §8 "curriculum").

Written by the curriculum extractor during ingest, alongside the chunks, so
"how many credits is DBMS?" and "what's in Unit 3?" are exact lookups rather
than retrieval. Every row points back at the chunk it came from, so an exact
answer can still cite the syllabus page.

`syllabus_courses.subject_code` is the link to the synthetic `subjects` table,
matched by normalised *name* at ingest: the PDFs' own codes differ from the
generated dataset's (and several are printed as placeholders).
"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY

from app.db.base import Base


class SyllabusCourse(Base):
    __tablename__ = "syllabus_courses"
    __table_args__ = (Index("ix_syllabus_courses_title_key", "title_key"),)

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    dept_code = Column(String, nullable=True)  # from the manifest entry
    code = Column(String, nullable=True, index=True)  # as printed; NULL for placeholders
    subject_code = Column(String, ForeignKey("subjects.subject_code"), nullable=True, index=True)
    title = Column(String, nullable=False)
    title_key = Column(String, nullable=False)  # normalised title used for name matching
    lecture_hours = Column(Integer, nullable=True)
    tutorial_hours = Column(Integer, nullable=True)
    practical_hours = Column(Integer, nullable=True)
    credits = Column(Numeric(3, 1), nullable=True)
    objectives = Column(ARRAY(String), nullable=True)
    page = Column(Integer, nullable=True)
    source_chunk_id = Column(Integer, ForeignKey("doc_chunks.id", ondelete="SET NULL"), nullable=True)


class SyllabusUnit(Base):
    __tablename__ = "syllabus_units"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("syllabus_courses.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    hours = Column(Integer, nullable=True)
    topics = Column(Text, nullable=True)
    page = Column(Integer, nullable=True)
    source_chunk_id = Column(Integer, ForeignKey("doc_chunks.id", ondelete="SET NULL"), nullable=True)


class CourseOutcome(Base):
    __tablename__ = "course_outcomes"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("syllabus_courses.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    source_chunk_id = Column(Integer, ForeignKey("doc_chunks.id", ondelete="SET NULL"), nullable=True)


class Textbook(Base):
    __tablename__ = "textbooks"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("syllabus_courses.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    citation = Column(Text, nullable=False)
    source_chunk_id = Column(Integer, ForeignKey("doc_chunks.id", ondelete="SET NULL"), nullable=True)
