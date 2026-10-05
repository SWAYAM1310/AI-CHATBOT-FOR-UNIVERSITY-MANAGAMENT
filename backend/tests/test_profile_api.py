"""Phase 7a — profile view/edit, password change, photo upload.

Real DB, no LLM. Every test that writes restores the rows it touched: the suite
reloads the seed once per session, not per test.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models import Faculty, Student, User

client = TestClient(app)
DEV_PW = "uniassist"
STUDENT = "student:17"
OTHER_STUDENT = "student:18"
FACULTY = "faculty:2"


def _login(subject_ref: str | None = None, role: str | None = None, password: str = DEV_PW) -> dict:
    with SessionLocal() as db:
        q = select(User.email)
        q = q.where(User.subject_ref == subject_ref) if subject_ref else q.where(User.role == role)
        email = db.scalars(q.limit(1)).one()
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _user_id(subject_ref: str) -> int:
    with SessionLocal() as db:
        return db.scalars(select(User.id).where(User.subject_ref == subject_ref)).one()


@pytest.fixture()
def restore():
    """Snapshot the users/students/faculty rows these tests edit and put them back."""
    cols = {
        User: ("password_hash", "photo_path"),
        Student: ("phone", "personal_email", "address_city", "address_state"),
        Faculty: ("phone", "personal_email", "office_room"),
    }
    with SessionLocal() as db:
        snap = [(row, {c: getattr(row, c) for c in names}) for model, names in cols.items()
                for row in db.scalars(select(model).where(_pick(model)))]
        saved = [(type(r), r.id, vals) for r, vals in snap]
    yield
    with SessionLocal() as db:
        for model, pk, vals in saved:
            row = db.get(model, pk)
            for c, v in vals.items():
                setattr(row, c, v)
        db.commit()


def _pick(model):
    ids = {User: [_user_id(STUDENT), _user_id(OTHER_STUDENT), _user_id(FACULTY)], Student: [17, 18], Faculty: [2]}
    return model.id.in_(ids[model])


@pytest.fixture()
def media(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_dir", tmp_path)
    return tmp_path


def _image(fmt: str = "PNG", size=(400, 300), exif: bool = False) -> bytes:
    img = Image.new("RGB", size, (200, 30, 30))
    out = io.BytesIO()
    kwargs = {}
    if exif:
        e = Image.Exif()
        e[0x010F] = "SecretCameraMaker"  # Make
        kwargs["exif"] = e.tobytes()
    img.save(out, format=fmt, **kwargs)
    return out.getvalue()


# --- view ---------------------------------------------------------------------


def test_profile_view_has_the_full_record_per_role():
    s = client.get("/api/profile", headers=_login(STUDENT)).json()
    assert s["role"] == "student" and s["profile"]["roll_no"] == "25BCP017"
    assert {"department", "hod", "semester", "cgpa", "guardian_name"} <= s["profile"].keys()
    assert s["editable"] == ["phone", "personal_email", "address_city", "address_state"]

    f = client.get("/api/profile", headers=_login(FACULTY)).json()
    assert f["role"] == "faculty" and f["profile"]["employee_id"] and "designation" in f["profile"]
    assert "cgpa" not in f["profile"]

    a = client.get("/api/profile", headers=_login(role="admin")).json()
    assert a["role"] == "admin" and a["editable"] == ["phone", "personal_email"]


def test_profile_requires_a_token():
    assert client.get("/api/profile").status_code in (401, 403)


def test_me_carries_the_name_and_photo_flag():
    me = client.get("/api/me", headers=_login(STUDENT)).json()
    assert me["full_name"] and me["has_photo"] is False


# --- edit ---------------------------------------------------------------------


def test_contact_fields_can_be_edited(restore):
    h = _login(STUDENT)
    r = client.patch("/api/profile", headers=h, json={"phone": "+91 98765 43210", "address_city": "Pune"})
    assert r.status_code == 200
    assert r.json()["profile"]["phone"] == "+91 98765 43210"
    assert client.get("/api/profile", headers=h).json()["profile"]["address_city"] == "Pune"


def test_blank_clears_a_field(restore):
    h = _login(STUDENT)
    r = client.patch("/api/profile", headers=h, json={"address_state": "  "})
    assert r.json()["profile"]["address_state"] is None


@pytest.mark.parametrize("field", ["cgpa", "roll_no", "dept_code", "semester", "full_name", "university_email", "is_hod"])
def test_official_fields_are_rejected(field, restore):
    r = client.patch("/api/profile", headers=_login(STUDENT), json={field: "9.9"})
    assert r.status_code == 422  # extra keys are forbidden outright, not silently dropped


def test_a_field_the_role_does_not_have_is_refused(restore):
    # office_room is a real column - but a student's profile has no such field
    r = client.patch("/api/profile", headers=_login(STUDENT), json={"office_room": "B-12"})
    assert r.status_code == 400 and "cannot edit" in r.json()["detail"]
    ok = client.patch("/api/profile", headers=_login(FACULTY), json={"office_room": "B-12"})
    assert ok.status_code == 200 and ok.json()["profile"]["office_room"] == "B-12"


def test_bad_values_are_refused(restore):
    h = _login(STUDENT)
    assert client.patch("/api/profile", headers=h, json={"phone": "call me"}).status_code == 422
    assert client.patch("/api/profile", headers=h, json={"personal_email": "not-an-email"}).status_code == 422
    assert client.patch("/api/profile", headers=h, json={}).status_code == 400


def test_an_edit_only_touches_the_callers_own_row(restore):
    client.patch("/api/profile", headers=_login(STUDENT), json={"phone": "+91 11111 11111"})
    other = client.get("/api/profile", headers=_login(OTHER_STUDENT)).json()
    assert other["profile"]["phone"] != "+91 11111 11111"


# --- password -----------------------------------------------------------------


def test_password_change_round_trip(restore):
    h = _login(STUDENT)
    r = client.post("/api/profile/password", headers=h, json={"current": DEV_PW, "new": "a-brand-new-pass"})
    assert r.status_code == 204
    with SessionLocal() as db:
        email = db.scalars(select(User.email).where(User.subject_ref == STUDENT)).one()
    assert client.post("/api/auth/login", json={"email": email, "password": DEV_PW}).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "a-brand-new-pass"}).status_code == 200


def test_wrong_current_password_is_a_400(restore):
    r = client.post("/api/profile/password", headers=_login(STUDENT), json={"current": "nope", "new": "a-brand-new-pass"})
    assert r.status_code == 400 and "incorrect" in r.json()["detail"]


@pytest.mark.parametrize("new", ["short", "x" * 129, DEV_PW])
def test_weak_or_unchanged_new_password_is_a_400(new, restore):
    r = client.post("/api/profile/password", headers=_login(STUDENT), json={"current": DEV_PW, "new": new})
    assert r.status_code == 400


# --- photo --------------------------------------------------------------------


def test_photo_upload_is_re_encoded_to_a_small_webp_without_metadata(media, restore):
    h = _login(STUDENT)
    assert client.post("/api/profile/photo", headers=h, files={"file": ("me.jpg", _image("JPEG", exif=True), "image/jpeg")}).status_code == 204
    me = client.get("/api/me", headers=h).json()
    assert me["has_photo"] is True

    served = client.get(f"/api/profile/photo/{me['user_id']}", headers=h)
    assert served.status_code == 200 and served.headers["content-type"] == "image/webp"
    img = Image.open(io.BytesIO(served.content))
    assert img.format == "WEBP" and img.size == (256, 256)
    assert not img.getexif() and b"SecretCameraMaker" not in served.content


def test_photo_can_be_removed(media, restore):
    h = _login(STUDENT)
    client.post("/api/profile/photo", headers=h, files={"file": ("me.png", _image(), "image/png")})
    uid = client.get("/api/me", headers=h).json()["user_id"]
    assert client.delete("/api/profile/photo", headers=h).status_code == 204
    assert client.get(f"/api/profile/photo/{uid}", headers=h).status_code == 404
    assert client.get("/api/me", headers=h).json()["has_photo"] is False
    assert not list((media / "avatars").glob("*"))


def test_non_images_are_rejected(media, restore):
    h = _login(STUDENT)
    for name, data in [("a.png", b"this is not an image"), ("a.gif", _image("GIF")), ("a.txt", b"<script>alert(1)</script>")]:
        r = client.post("/api/profile/photo", headers=h, files={"file": (name, data, "image/png")})
        assert r.status_code == 400, name
    assert client.get("/api/me", headers=h).json()["has_photo"] is False


def test_oversize_upload_is_rejected(media, restore):
    r = client.post(
        "/api/profile/photo",
        headers=_login(STUDENT),
        files={"file": ("big.png", b"\x89PNG" + b"0" * (2 * 1024 * 1024 + 10), "image/png")},
    )
    assert r.status_code == 413


def test_uploaded_filename_never_picks_where_the_file_lands(media, restore):
    h = _login(STUDENT)
    client.post("/api/profile/photo", headers=h, files={"file": ("../../evil.png", _image(), "image/png")})
    stored = [p.name for p in (media / "avatars").iterdir()]
    assert stored == [f"{_user_id(STUDENT)}.webp"]
    assert not any(p.name == "evil.png" for p in media.rglob("*"))


def test_a_student_cannot_view_another_users_photo_or_overwrite_it(media, restore):
    other_h, mine = _login(OTHER_STUDENT), _login(STUDENT)
    client.post("/api/profile/photo", headers=other_h, files={"file": ("o.png", _image(size=(50, 50)), "image/png")})
    other_id = _user_id(OTHER_STUDENT)
    assert client.get(f"/api/profile/photo/{other_id}", headers=mine).status_code == 403

    before = (media / "avatars" / f"{other_id}.webp").read_bytes()
    client.post("/api/profile/photo", headers=mine, files={"file": ("m.png", _image(size=(90, 90)), "image/png")})
    assert (media / "avatars" / f"{other_id}.webp").read_bytes() == before  # the upload only ever wrote the caller's own


def test_faculty_and_admin_can_view_a_students_photo(media, restore):
    client.post("/api/profile/photo", headers=_login(STUDENT), files={"file": ("m.png", _image(), "image/png")})
    uid = _user_id(STUDENT)
    for h in (_login(FACULTY), _login(role="admin")):
        assert client.get(f"/api/profile/photo/{uid}", headers=h).status_code == 200
