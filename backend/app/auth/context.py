"""AuthContext — the server-side identity + scoping derived from a verified JWT.

Nothing here is taken from request arguments. `subject_ref` ("student:17") comes
from the token; dept_id / is_hod are looked up fresh from the DB each request.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Admin, Faculty, Student, User


class Role(str, Enum):
    STUDENT = "student"
    FACULTY = "faculty"
    ADMIN = "admin"


@dataclass(frozen=True)
class AuthContext:
    user_id: int
    role: Role
    subject_ref: str
    term: str
    student_id: int | None = None
    faculty_id: int | None = None
    admin_id: int | None = None
    dept_id: int | None = None
    is_hod: bool = False

    @property
    def subject_id(self) -> int:
        """The row id in students/faculty/admins for this caller."""
        return self.student_id or self.faculty_id or self.admin_id  # type: ignore[return-value]


class AuthError(Exception):
    pass


def build_auth_context(payload: dict, db: Session) -> AuthContext:
    try:
        user_id = int(payload["sub"])
        subject_ref = payload["subject_ref"]
        role = Role(payload["role"])
    except (KeyError, ValueError) as exc:
        raise AuthError("malformed token") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthError("unknown or inactive user")

    kind, _, raw_id = subject_ref.partition(":")
    sid = int(raw_id) if raw_id.isdigit() else None
    if kind != role.value or sid is None:
        raise AuthError("token identity mismatch")

    ctx = dict(
        user_id=user_id,
        role=role,
        subject_ref=subject_ref,
        term=settings.current_term,
    )

    if role is Role.STUDENT:
        row = db.get(Student, sid)
        if row is None:
            raise AuthError("student not found")
        ctx.update(student_id=row.id, dept_id=row.dept_id)
    elif role is Role.FACULTY:
        row = db.get(Faculty, sid)
        if row is None:
            raise AuthError("faculty not found")
        ctx.update(faculty_id=row.id, dept_id=row.dept_id, is_hod=bool(row.is_hod))
    else:
        row = db.get(Admin, sid)
        if row is None:
            raise AuthError("admin not found")
        ctx.update(admin_id=row.id)

    return AuthContext(**ctx)
