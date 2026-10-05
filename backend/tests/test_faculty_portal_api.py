"""Phase 7b — the faculty portal API, the student dashboard, and the action-tool changes behind them.

Real DB, no LLM. Faculty 2 teaches 24CS201T (offering 3) and its Internal-2 (assessment 12,
max 20) has no marks yet; faculty 1 teaches offering 7. Everything a test writes is deleted
afterwards by the `undo` fixture.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.ai.tools.registry import REGISTRY
from app.ai.tools.schema import function_schema
from app.db.session import SessionLocal
from app.main import app
from app.models import AttendanceRecord, AttendanceSession, AuditLog, Mark, Student, User
from tests.conftest import make_ctx

client = TestClient(app)
DEV_PW = "uniassist"
DBMS_OFFERING = 3
DBMS = "24CS201T"
INTERNAL_2 = 12  # DBMS, max 20, nothing entered yet
OTHER_OFFERING = 7  # faculty 1's
OTHER_ASSESSMENT = 24  # faculty 1's
FACULTY = "faculty:2"
PAST_DAY = "2020-01-06"  # no seeded session falls here
CLEARED = (AttendanceRecord, AttendanceSession, Mark)


def _login(subject_ref: str) -> dict:
    with SessionLocal() as db:
        email = db.scalars(select(User.email).where(User.subject_ref == subject_ref)).one()
    r = client.post("/api/auth/login", json={"email": email, "password": DEV_PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def fac():
    return _login(FACULTY)


@pytest.fixture()
def undo():
    with SessionLocal() as s:
        high = {m: s.scalar(select(func.coalesce(func.max(m.id), 0))) for m in CLEARED}
    yield
    with SessionLocal() as s:
        for m in CLEARED:  # records before their sessions
            s.execute(delete(m).where(m.id > high[m]))
        s.commit()


def _roster(h) -> list[dict]:
    r = client.get(f"/api/faculty/offerings/{DBMS_OFFERING}/roster", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["students"]


def _student_headers(roll_no: str) -> dict:
    with SessionLocal() as db:
        sid = db.scalars(select(Student.id).where(Student.roll_no == roll_no)).one()
    return _login(f"student:{sid}")


def _dbms_row(dashboard: dict) -> dict:
    return next(c for c in dashboard["attendance"]["courses"] if c["course"] == DBMS)


# --- who may call ---------------------------------------------------------------------


def test_every_faculty_route_needs_a_faculty_token():
    student = _login("student:17")
    paths = [
        ("get", "/api/faculty/courses"),
        ("get", f"/api/faculty/offerings/{DBMS_OFFERING}/roster"),
        ("get", f"/api/faculty/offerings/{DBMS_OFFERING}/attendance"),
        ("get", f"/api/faculty/offerings/{DBMS_OFFERING}/assessments"),
        ("get", f"/api/faculty/assessments/{INTERNAL_2}/marks"),
        ("get", "/api/faculty/dashboard"),
    ]
    for verb, path in paths:
        assert getattr(client, verb)(path).status_code in (401, 403), path
        assert getattr(client, verb)(path, headers=student).status_code == 403, path
    assert client.get("/api/faculty/courses", headers=_login("admin:1")).status_code == 403


def test_a_student_dashboard_is_students_only(fac):
    assert client.get("/api/student/dashboard", headers=fac).status_code == 403
    assert client.get("/api/student/dashboard").status_code in (401, 403)


# --- courses and roster -----------------------------------------------------------------


def test_courses_lists_exactly_the_callers_sections_with_ids(fac):
    rows = client.get("/api/faculty/courses", headers=fac).json()
    assert {r["offering_id"] for r in rows} >= {DBMS_OFFERING}
    assert all(r["enrolled"] is not None for r in rows)
    with SessionLocal() as db:
        mine = REGISTRY.invoke("get_my_teaching_courses", make_ctx("faculty", 2), db)
    assert len(rows) == len(mine)  # the page and the assistant agree on what faculty 2 teaches


def test_roster_matches_the_assistants_roster_and_carries_attendance(fac):
    students = _roster(fac)
    with SessionLocal() as db:
        chat = REGISTRY.invoke("list_course_students", make_ctx("faculty", 2), db, {"course_code": DBMS})
    assert {s["roll_no"] for s in students} == {r["roll_no"] for r in chat}
    assert all({"attended", "total", "attendance_percent", "missing_submissions"} <= s.keys() for s in students)


def test_a_section_the_caller_does_not_teach_is_a_404_everywhere(fac, undo):
    for path in (
        f"/api/faculty/offerings/{OTHER_OFFERING}/roster",
        f"/api/faculty/offerings/{OTHER_OFFERING}/attendance",
        f"/api/faculty/offerings/{OTHER_OFFERING}/assessments",
        f"/api/faculty/assessments/{OTHER_ASSESSMENT}/marks",
        "/api/faculty/offerings/999999/roster",
    ):
        assert client.get(path, headers=fac).status_code == 404, path
    body = {"date": PAST_DAY, "absent_roll_nos": []}
    assert client.post(f"/api/faculty/offerings/{OTHER_OFFERING}/attendance", headers=fac, json=body).status_code == 404
    assert client.put(f"/api/faculty/offerings/{OTHER_OFFERING}/attendance", headers=fac, json=body).status_code == 404
    assert client.post(f"/api/faculty/assessments/{OTHER_ASSESSMENT}/marks", headers=fac, json={"marks": {"x": 1}}).status_code == 404
    with SessionLocal() as db:  # and nothing was written
        assert db.scalar(select(func.count(AttendanceSession.id)).where(AttendanceSession.session_date == date.fromisoformat(PAST_DAY))) == 0


# --- attendance -------------------------------------------------------------------------


def test_marking_attendance_reaches_the_students_dashboard_at_once(fac, undo):
    students = _roster(fac)
    victim = next(s for s in students if s["total"] > 0)["roll_no"]
    sh = _student_headers(victim)
    before = _dbms_row(client.get("/api/student/dashboard", headers=sh).json())

    r = client.post(
        f"/api/faculty/offerings/{DBMS_OFFERING}/attendance",
        headers=fac,
        json={"date": PAST_DAY, "slot_no": 1, "absent_roll_nos": [victim]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["absent"] == 1 and r.json()["present"] == len(students) - 1

    after = _dbms_row(client.get("/api/student/dashboard", headers=sh).json())
    assert after["total"] == before["total"] + 1
    assert after["attended"] == before["attended"]  # absent: the class counted, the attendance did not
    assert after["percent"] < before["percent"]

    day = client.get(f"/api/faculty/offerings/{DBMS_OFFERING}/attendance", headers=fac, params={"date": PAST_DAY}).json()
    assert [s["absent_roll_nos"] for s in day["sessions"]] == [[victim]]
    assert any(s["date"] == PAST_DAY for s in day["recent"]) or len(day["recent"]) == 10


def test_attendance_is_audited_as_a_confirmed_action(fac, undo):
    client.post(f"/api/faculty/offerings/{DBMS_OFFERING}/attendance", headers=fac, json={"date": PAST_DAY, "absent_roll_nos": []})
    with SessionLocal() as db:
        last = db.scalars(select(AuditLog).where(AuditLog.tool_name == "mark_attendance").order_by(AuditLog.id.desc())).first()
    assert last.decision == "confirmed" and last.role == "faculty"


def test_the_same_day_cannot_be_marked_twice_and_future_days_are_refused(fac, undo):
    body = {"date": PAST_DAY, "absent_roll_nos": []}
    assert client.post(f"/api/faculty/offerings/{DBMS_OFFERING}/attendance", headers=fac, json=body).status_code == 201
    dup = client.post(f"/api/faculty/offerings/{DBMS_OFFERING}/attendance", headers=fac, json=body)
    assert dup.status_code == 409 and "already recorded" in dup.json()["detail"]
    future = (date.today() + timedelta(days=1)).isoformat()
    assert client.post(f"/api/faculty/offerings/{DBMS_OFFERING}/attendance", headers=fac, json={"date": future}).status_code == 400


def test_unknown_roll_numbers_and_bad_input_are_refused(fac, undo):
    r = client.post(f"/api/faculty/offerings/{DBMS_OFFERING}/attendance", headers=fac, json={"date": PAST_DAY, "absent_roll_nos": ["25XXX999"]})
    assert r.status_code == 400 and "not enrolled" in r.json()["detail"]
    assert client.post(f"/api/faculty/offerings/{DBMS_OFFERING}/attendance", headers=fac, json={"date": "not-a-date"}).status_code == 422


def test_a_correction_rewrites_only_the_difference(fac, undo):
    a, b = (s["roll_no"] for s in _roster(fac)[:2])
    url = f"/api/faculty/offerings/{DBMS_OFFERING}/attendance"
    client.post(url, headers=fac, json={"date": PAST_DAY, "absent_roll_nos": [a]})

    fixed = client.put(url, headers=fac, json={"date": PAST_DAY, "absent_roll_nos": [b]})
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["changed"] == 2  # a: absent -> present, b: present -> absent
    day = client.get(url, headers=fac, params={"date": PAST_DAY}).json()
    assert day["sessions"][0]["absent_roll_nos"] == [b]

    again = client.put(url, headers=fac, json={"date": PAST_DAY, "absent_roll_nos": [b]})
    assert again.status_code == 409  # already matches: nothing to correct


def test_correcting_a_day_that_was_never_marked_is_a_400(fac, undo):
    r = client.put(f"/api/faculty/offerings/{DBMS_OFFERING}/attendance", headers=fac, json={"date": PAST_DAY, "absent_roll_nos": []})
    assert r.status_code == 400 and "mark it first" in r.json()["detail"]


def test_a_correction_keeps_late_and_excused_as_recorded(undo):
    ctx = make_ctx("faculty", 2)
    with SessionLocal() as db:
        args = {"course_code": DBMS, "date": PAST_DAY, "absent_roll_nos": [], "offering_id": DBMS_OFFERING}
        REGISTRY.invoke("mark_attendance", ctx, db, args, confirmed=True)
        db.commit()
        session = db.scalars(select(AttendanceSession).where(AttendanceSession.session_date == date.fromisoformat(PAST_DAY))).one()
        rec = db.scalars(select(AttendanceRecord).where(AttendanceRecord.session_id == session.id).limit(1)).one()
        rec.status = "late"
        db.commit()
        # "everyone is here" and a late student is not an absence: there is nothing to flip
        out = REGISTRY.invoke("correct_attendance", ctx, db, args, confirmed=True)
        assert "already matches" in out["error"]
        assert db.get(AttendanceRecord, rec.id).status == "late"


# --- marks ------------------------------------------------------------------------------


def test_marks_round_trip_with_an_absentee(fac, undo):
    a, b, c = (s["roll_no"] for s in _roster(fac)[:3])
    url = f"/api/faculty/assessments/{INTERNAL_2}/marks"
    r = client.post(url, headers=fac, json={"marks": {a: 17.5, b: 0}, "absent_roll_nos": [c]})
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == 3

    page = client.get(url, headers=fac).json()
    assert page["assessment"]["max_marks"] == 20.0
    by_roll = {s["roll_no"]: s for s in page["students"]}
    assert by_roll[a]["score"] == 17.5 and not by_roll[a]["is_absent"]
    assert by_roll[b]["score"] == 0.0
    assert by_roll[c]["score"] is None and by_roll[c]["is_absent"] is True

    # saving again updates in place, and a score entered for the absentee clears the flag
    r = client.post(url, headers=fac, json={"marks": {c: 12}})
    assert (r.json()["inserted"], r.json()["updated"]) == (0, 1)
    assert {s["roll_no"]: s for s in client.get(url, headers=fac).json()["students"]}[c]["is_absent"] is False

    listing = client.get(f"/api/faculty/offerings/{DBMS_OFFERING}/assessments", headers=fac).json()["assessments"]
    assert next(x for x in listing if x["assessment_id"] == INTERNAL_2)["graded"] == 3


def test_marks_are_validated(fac, undo):
    a, b = (s["roll_no"] for s in _roster(fac)[:2])
    url = f"/api/faculty/assessments/{INTERNAL_2}/marks"
    assert client.post(url, headers=fac, json={"marks": {a: 21}}).status_code == 400  # above the max of 20
    assert client.post(url, headers=fac, json={"marks": {a: -1}}).status_code == 400
    assert client.post(url, headers=fac, json={"marks": {"25XXX999": 5}}).status_code == 400
    assert client.post(url, headers=fac, json={"marks": {a: 5}, "absent_roll_nos": [a]}).status_code == 400
    assert client.post(url, headers=fac, json={}).status_code == 400  # nothing to save
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Mark.id)).where(Mark.assessment_id == INTERNAL_2)) == 0


# --- the action tools themselves -----------------------------------------------------------


def test_offering_id_is_hidden_from_the_models_schemas():
    for name in ("mark_attendance", "correct_attendance", "enter_marks"):
        props = function_schema(REGISTRY.get(name))["function"]["parameters"]["properties"]
        assert "offering_id" not in props and "course_code" in props, name
    assert "absent_roll_nos" in function_schema(REGISTRY.get("enter_marks"))["function"]["parameters"]["properties"]


def test_an_offering_id_cannot_reach_another_facultys_section(undo):
    other = make_ctx("faculty", 1)
    with SessionLocal() as db:
        out = REGISTRY.invoke("mark_attendance", other, db, {"course_code": DBMS, "date": PAST_DAY, "offering_id": DBMS_OFFERING}, confirmed=True)
    assert "do not teach" in out["error"]
    ctx = make_ctx("faculty", 2)
    with SessionLocal() as db:  # right course, someone else's section id
        out = REGISTRY.invoke("mark_attendance", ctx, db, {"course_code": DBMS, "date": PAST_DAY, "offering_id": OTHER_OFFERING}, confirmed=True)
    assert "do not teach" in out["error"]


def test_chat_previews_still_work_and_name_the_exact_section(undo):
    ctx = make_ctx("faculty", 2)
    with SessionLocal() as db:
        out = REGISTRY.invoke("correct_attendance", ctx, db, {"course_code": DBMS, "date": PAST_DAY})
    assert "mark it first" in out["error"]
    with SessionLocal() as db:
        prev = REGISTRY.invoke("mark_attendance", ctx, db, {"course_code": DBMS, "date": PAST_DAY, "absent_roll_nos": []})
    assert prev["needs_confirmation"] and prev["preview"]["offering_id"] == DBMS_OFFERING


# --- dashboards -----------------------------------------------------------------------------


def test_student_dashboard_has_every_section_and_the_attendance_arithmetic():
    d = client.get("/api/student/dashboard", headers=_login("student:17")).json()
    assert d["student"]["roll_no"] == "25BCP017" and d["attendance"]["threshold"] == 75
    assert {"attendance", "marks", "fees", "assignments", "exams", "today", "announcements"} <= d.keys()
    for c in d["attendance"]["courses"]:
        assert c["below_threshold"] == (c["total"] > 0 and c["attended"] / c["total"] < 0.75)
        if c["recover"]:  # attending that many classes in a row really does reach the floor
            assert (c["attended"] + c["recover"]) / (c["total"] + c["recover"]) >= 0.75
            assert (c["attended"] + c["recover"] - 1) / (c["total"] + c["recover"] - 1) < 0.75
        if c["can_skip"] is not None:
            assert c["attended"] / (c["total"] + c["can_skip"]) >= 0.75 > c["attended"] / (c["total"] + c["can_skip"] + 1)
    assert isinstance(d["fees"]["all_paid"], bool) and d["fees"]["outstanding"] >= 0


def test_student_dashboard_agrees_with_the_assistants_attendance():
    with SessionLocal() as db:
        chat = REGISTRY.invoke("get_my_attendance", make_ctx("student", 17), db)
    page = client.get("/api/student/dashboard", headers=_login("student:17")).json()["attendance"]["courses"]
    assert [(c["course"], c["percent"]) for c in page] == [(c["course"], c["percent"]) for c in chat]


def test_faculty_dashboard_shows_courses_todays_classes_and_hod_leave():
    d = client.get("/api/faculty/dashboard", headers=_login(FACULTY)).json()
    assert d["courses"] >= 1 and d["students"] >= 1 and isinstance(d["today"], list)
    assert d["pending_leave"]["count"] == 0  # faculty 2 is not an HOD
    assert {"count", "students"} <= d["at_risk"].keys()
    hod = client.get("/api/faculty/dashboard", headers=_login("faculty:4")).json()
    assert hod["faculty"]["is_hod"] is True and hod["pending_leave"]["count"] >= 1


# --- calendar -------------------------------------------------------------------------------


def _calendar(h, month: str, **params) -> dict:
    r = client.get("/api/faculty/calendar", headers=h, params={"month": month, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _day(cal: dict, iso: str) -> dict:
    return next(d for d in cal["days"] if d["date"] == iso)


def test_calendar_has_every_day_of_the_month_and_the_term_window(fac):
    cal = _calendar(fac, "2026-10")
    assert [d["date"] for d in cal["days"]] == [f"2026-10-{n:02d}" for n in range(1, 32)]
    assert cal["term"] == {"start": "2026-06-16", "end": "2026-11-06"}
    assert any(e["event_type"] == "holiday" for e in cal["events"])


def test_a_holiday_is_flagged_and_suspends_the_timetable(fac):
    cal = _calendar(fac, "2026-10")
    gandhi = _day(cal, "2026-10-02")
    assert [e["event_type"] for e in gandhi["events"]] == ["holiday"]
    assert all(c["status"] == "held" for c in gandhi["classes"])  # only a class someone actually marked
    assert any(d["classes"] for d in cal["days"])  # the timetable does run on ordinary days


def test_status_follows_the_attendance_actually_recorded(fac):
    cal = _calendar(fac, "2026-08")
    today = date.today().isoformat()
    statuses = set()
    for d in cal["days"]:
        for c in d["classes"]:
            statuses.add(c["status"])
            assert (c["status"] == "held") == bool(c["sessions"])
            assert c["status"] != "upcoming" or d["date"] > today
            assert {"course", "name", "division", "lab_group", "session_type"} <= c.keys()
    assert "held" in statuses


def test_marking_a_due_class_turns_it_held_on_the_calendar(fac, undo):
    cal = _calendar(fac, "2026-09", offering_id=DBMS_OFFERING)
    due = next(d for d in cal["days"] if any(c["status"] == "due" for c in d["classes"]))
    r = client.post(
        f"/api/faculty/offerings/{DBMS_OFFERING}/attendance", headers=fac, json={"date": due["date"], "absent_roll_nos": []}
    )
    assert r.status_code == 201, r.text
    [cls] = _day(_calendar(fac, "2026-09", offering_id=DBMS_OFFERING), due["date"])["classes"]
    assert cls["status"] == "held"
    assert cls["sessions"][0]["present"] == len(_roster(fac)) and cls["sessions"][0]["absent"] == 0


def test_calendar_filters_to_one_section_and_hides_foreign_ones(fac):
    cal = _calendar(fac, "2026-08", offering_id=DBMS_OFFERING)
    assert {c["offering_id"] for d in cal["days"] for c in d["classes"]} == {DBMS_OFFERING}
    assert client.get(
        "/api/faculty/calendar", headers=fac, params={"month": "2026-08", "offering_id": OTHER_OFFERING}
    ).status_code == 404


def test_calendar_rejects_a_bad_month_and_non_faculty(fac):
    for bad in ("2026-13", "2026-1", "october"):
        assert client.get("/api/faculty/calendar", headers=fac, params={"month": bad}).status_code == 422
    assert client.get("/api/faculty/calendar", headers=_login("student:17"), params={"month": "2026-10"}).status_code == 403
