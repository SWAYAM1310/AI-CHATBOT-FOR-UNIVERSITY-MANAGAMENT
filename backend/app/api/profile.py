"""Profile: the caller's full record, safe edits, password change, photo.

Identity always comes from AuthContext, never from the request: there is no
user id in any write path. Official fields (roll number, department, CGPA, ...)
are read-only here; only the contact fields in EDITABLE can be changed, and
`ProfilePatch` forbids unknown keys so an attempt to send `cgpa` is a 422, not
a silent drop.

Photos are re-encoded with Pillow to a small WebP before they touch disk: that
strips EXIF (GPS!) and makes a non-image or polyglot upload fail loudly rather
than be stored as-is.
"""
from __future__ import annotations

import io
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.context import AuthContext, Role
from app.auth.deps import get_auth_context, get_db
from app.auth.security import hash_password, verify_password
from app.config import settings
from app.models import Admin, Department, Faculty, Student, User

router = APIRouter(prefix="/api/profile", tags=["profile"])

# the only fields a user may change about themselves, per role
EDITABLE: dict[Role, tuple[str, ...]] = {
    Role.STUDENT: ("phone", "personal_email", "address_city", "address_state"),
    Role.FACULTY: ("phone", "personal_email", "office_room"),
    Role.ADMIN: ("phone", "personal_email"),
}

MAX_PHOTO_BYTES = 2 * 1024 * 1024
MAX_PHOTO_PIXELS = 25_000_000  # a decompression-bomb guard: checked before the image is decoded
PHOTO_SIZE = 256
PHOTO_FORMATS = {"JPEG", "PNG", "WEBP"}
MIN_PASSWORD_CHARS = 8
MAX_PASSWORD_CHARS = 128

_PHONE = re.compile(r"^\+?[0-9][0-9 \-]{6,17}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str | None = Field(default=None, max_length=20)
    personal_email: str | None = Field(default=None, max_length=120)
    address_city: str | None = Field(default=None, max_length=80)
    address_state: str | None = Field(default=None, max_length=80)
    office_room: str | None = Field(default=None, max_length=40)


class PasswordIn(BaseModel):
    current: str
    new: str


# --- the caller's own row ---------------------------------------------------


def identity_row(db: Session, ctx: AuthContext) -> Student | Faculty | Admin:
    """The Student/Faculty/Admin row the token's role points at."""
    if ctx.role is Role.STUDENT:
        row = db.get(Student, ctx.student_id)
    elif ctx.role is Role.FACULTY:
        row = db.get(Faculty, ctx.faculty_id)
    else:
        row = db.get(Admin, ctx.admin_id)
    if row is None:  # a token for a row that no longer exists
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    return row


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _num(value: Any) -> float | None:
    return float(value) if value is not None else None


def _record(db: Session, ctx: AuthContext, row: Student | Faculty | Admin) -> dict[str, Any]:
    common = {
        "full_name": row.full_name,
        "university_email": row.university_email,
        "personal_email": row.personal_email,
        "gender": row.gender,
        "date_of_birth": _iso(row.date_of_birth),
        "phone": row.phone,
    }
    if ctx.role is Role.STUDENT:
        dept = db.get(Department, row.dept_id)
        hod = db.get(Faculty, dept.hod_faculty_id) if dept and dept.hod_faculty_id else None
        return {
            **common,
            "roll_no": row.roll_no,
            "department": dept.name if dept else row.dept_code,
            "dept_code": row.dept_code,
            "hod": hod.full_name if hod else None,
            "batch": row.batch,
            "semester": row.semester,
            "division": row.division,
            "lab_group": row.lab_group,
            "cgpa": _num(row.cgpa),
            "tenth_percentage": _num(row.tenth_percentage),
            "twelfth_percentage": _num(row.twelfth_percentage),
            "is_hosteller": row.is_hosteller,
            "address_city": row.address_city,
            "address_state": row.address_state,
            "guardian_name": row.guardian_name,
            "guardian_phone": row.guardian_phone,
            "admission_date": _iso(row.admission_date),
        }
    if ctx.role is Role.FACULTY:
        dept = db.get(Department, row.dept_id)
        return {
            **common,
            "employee_id": row.employee_id,
            "department": dept.name if dept else row.dept_code,
            "dept_code": row.dept_code,
            "designation": row.designation,
            "is_hod": bool(row.is_hod),
            "date_of_joining": _iso(row.date_of_joining),
            "qualification": row.qualification,
            "specialization": row.specialization,
            "office_room": row.office_room,
        }
    return {
        **common,
        "employee_id": row.employee_id,
        "designation": row.designation,
        "date_of_joining": _iso(row.date_of_joining),
    }


@router.get("")
def get_profile(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> dict[str, Any]:
    row = identity_row(db, ctx)
    user = db.get(User, ctx.user_id)
    return {
        "role": ctx.role.value,
        "editable": list(EDITABLE[ctx.role]),
        "has_photo": bool(user and user.photo_path),
        "profile": _record(db, ctx, row),
    }


@router.patch("")
def update_profile(
    body: ProfilePatch, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> dict[str, Any]:
    row = identity_row(db, ctx)
    allowed = set(EDITABLE[ctx.role])
    sent = body.model_fields_set
    if not sent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "nothing to update")
    if not sent <= allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"cannot edit: {', '.join(sorted(sent - allowed))}; editable: {', '.join(sorted(allowed))}",
        )
    for field in sorted(sent):
        value = (getattr(body, field) or "").strip() or None  # blank clears the field
        if value and field == "phone" and not _PHONE.match(value):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "phone must be digits, optionally with + - or spaces")
        if value and field == "personal_email" and not _EMAIL.match(value):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "personal_email is not a valid email address")
        setattr(row, field, value)
    db.commit()
    return {"profile": _record(db, ctx, row)}


# --- password ---------------------------------------------------------------


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordIn, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> Response:
    user = db.get(User, ctx.user_id)
    if user is None or not verify_password(body.current, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "current password is incorrect")
    if not MIN_PASSWORD_CHARS <= len(body.new) <= MAX_PASSWORD_CHARS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"new password must be {MIN_PASSWORD_CHARS}-{MAX_PASSWORD_CHARS} characters",
        )
    if body.new == body.current:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "new password must differ from the current one")
    user.password_hash = hash_password(body.new)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- photo ------------------------------------------------------------------


def _avatar_dir():
    path = settings.media_dir / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _encode_photo(raw: bytes) -> bytes:
    """Square 256px WebP, no metadata; HTTP 400 for anything that is not a real image."""
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            if probe.format not in PHOTO_FORMATS:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "photo must be a JPEG, PNG or WebP image")
            if probe.width * probe.height > MAX_PHOTO_PIXELS:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "image dimensions are too large")
            img = ImageOps.exif_transpose(probe).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "file is not a valid image") from exc
    img = ImageOps.fit(img, (PHOTO_SIZE, PHOTO_SIZE))
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=85)  # a fresh image: nothing of the upload's metadata survives
    return out.getvalue()


@router.post("/photo", status_code=status.HTTP_204_NO_CONTENT)
async def upload_photo(
    file: UploadFile, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> Response:
    raw = await file.read(MAX_PHOTO_BYTES + 1)
    if len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "photo must be 2 MB or smaller")
    encoded = _encode_photo(raw)
    user = db.get(User, ctx.user_id)
    name = f"{ctx.user_id}.webp"  # the name is derived from the token, never from the upload
    (_avatar_dir() / name).write_bytes(encoded)
    user.photo_path = name
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/photo", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> Response:
    user = db.get(User, ctx.user_id)
    if user and user.photo_path:
        (_avatar_dir() / user.photo_path).unlink(missing_ok=True)
        user.photo_path = None
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/photo/{user_id}")
def get_photo(user_id: int, ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> FileResponse:
    """A photo is visible to its owner, to faculty (they see rosters) and to admins; not to other students."""
    if user_id != ctx.user_id and ctx.role is Role.STUDENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your photo")
    user = db.get(User, user_id)
    path = _avatar_dir() / user.photo_path if user and user.photo_path else None
    if path is None or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no photo")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=60"})
