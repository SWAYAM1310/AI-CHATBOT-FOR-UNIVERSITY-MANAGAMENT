"""SQLAlchemy ORM models.

Schema is derived from data/synthetic/sample/*.csv headers (authoritative), with
the AI-layer tables taken from plan.md §2. Divergences from plan.md §2 are recorded
in SCHEMA_MAP.md. Every model module is imported here so Alembic autogenerate and
Base.metadata.create_all see the full set.
"""
from __future__ import annotations

from app.db.base import Base

from app.models.identity import (  # noqa: F401
    Admin,
    Department,
    Faculty,
    Student,
    User,
)
from app.models.academic import (  # noqa: F401
    Classroom,
    CourseOffering,
    Curriculum,
    Enrollment,
    Subject,
    TeachingAssignment,
    TimetableSlot,
)
from app.models.assessment import (  # noqa: F401
    Assessment,
    AttendanceRecord,
    AttendanceSession,
    ExamSchedule,
    Mark,
    ResultSemester,
    Submission,
)
from app.models.administration import (  # noqa: F401
    AcademicCalendarEvent,
    Announcement,
    DocumentRequest,
    Fee,
    LeaveRequest,
    Scholarship,
)
from app.models.ai import (  # noqa: F401
    AuditLog,
    Conversation,
    DocChunk,
    Document,
    Message,
)

__all__ = ["Base"]
