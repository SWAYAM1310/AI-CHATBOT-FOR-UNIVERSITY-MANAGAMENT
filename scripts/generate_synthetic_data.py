"""
Full synthetic dataset generator for UniAssist (School of Technology, PDEU).

Produces a deterministic (fixed-seed) relational dataset covering the whole
plan.md data model except the AI layer (conversations / messages / documents /
doc_chunks / audit_log — those are populated at runtime and by RAG ingest) and
the curriculum-detail tables (syllabus_units / course_outcomes / textbooks /
course_prerequisites — those are filled by the Phase-3 PDF extractor).

Two academic terms are modelled:
    2026-27-ODD   in progress, "as of" 2026-08-27  (sems 1/3/5/7)
    2025-26-EVEN  completed, with results          (sems 2/4/6)

Deliberately planted demo edge cases (see academic_data.DEMO):
    - a CP sem-3 student at ~68% attendance in DBMS
    - Digital Logic & Design with a ~35% fail rate on Internal Test 1
    - a cohort with missing Assignment 2 submissions in DBMS
    - a student with unpaid fees and a pending scholarship
    - several pending leave requests for the decide_leave_request demo

Requirements:
    pip install pandas

Usage:
    python scripts/generate_synthetic_data.py --sample   # tiny sample  -> data/synthetic/sample/
    python scripts/generate_synthetic_data.py            # full dataset -> data/synthetic/
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import math
import random
from pathlib import Path

import pandas as pd

import academic_data as AD
from curriculum_data import CURRICULUM, OWNED_AREAS, SUBJECTS, component, subject_area
from gujarati_names import (
    guardian_first_name,
    home_town,
    staff_name,
    student_name,
)

SEED = 42
DOMAIN = "sot.pdpu.ac.in"
DIVISION_SIZE = 60

# ---------------------------------------------------------------------------
# Departments.  SH ("Basic Sciences & Humanities") has no students of its own;
# it staffs the shared first-year service courses (Maths, Physics, Humanities,
# basic Electrical, open electives, MOOCs).
# ---------------------------------------------------------------------------
DEPARTMENTS = [
    {"code": "CP", "name": "Computer Science", "letter": "G", "students_per_batch": 350, "building": "A Block"},
    {"code": "IT", "name": "Information & Communication Technology", "letter": "H", "students_per_batch": 200, "building": "B Block"},
    {"code": "EC", "name": "Electronics & Communication", "letter": "F", "students_per_batch": 150, "building": "C Block"},
    {"code": "ME", "name": "Mechanical", "letter": "A", "students_per_batch": 150, "building": "D Block"},
    {"code": "CE", "name": "Civil", "letter": "B", "students_per_batch": 150, "building": "E Block"},
    {"code": "CH", "name": "Chemical", "letter": "C", "students_per_batch": 150, "building": "F Block"},
    {"code": "SH", "name": "Basic Sciences & Humanities", "letter": "S", "students_per_batch": 0, "building": "Central Block"},
]
STUDENT_DEPARTMENTS = [d for d in DEPARTMENTS if d["code"] != "SH"]

FULL_BATCHES = [2023, 2024, 2025, 2026]
SAMPLE_BATCHES = [2025, 2026]
# CP is 22 (not a rounder 16) so the planted-demo rolls 25BCP017 (the ~68%
# attendance signature demo) and 25BCP021 (a decide_leave_request target) exist
# in the sample. 24BCP009 is a 2024-batch roll and stays sample-absent by design.
SAMPLE_STUDENT_COUNTS = {"CP": 22, "IT": 10, "EC": 6, "ME": 6, "CE": 6, "CH": 6}

FACULTY_TOTAL_FULL = 118          # includes SH
FACULTY_PER_DEPT_SAMPLE = 4

ADMIN_DESIGNATIONS = [
    "Registrar", "Dean - School of Technology", "Academic Coordinator",
    "Examination Controller", "IT Systems Administrator",
    "Training & Placement Officer", "Accounts Officer",
]

SPECIALIZATIONS_BY_DEPT = {
    "CP": ["Artificial Intelligence & Machine Learning", "Data Science & Big Data", "Computer Networks & Security",
           "Software Engineering", "Database Systems", "Theoretical Computer Science", "Cloud Computing",
           "Human-Computer Interaction"],
    "IT": ["Web & Mobile Technologies", "Information Security", "Cloud Computing", "Data Analytics",
           "Networking & Distributed Systems", "Database Systems", "Internet of Things"],
    "EC": ["VLSI Design", "Embedded Systems", "Wireless Communication", "Signal Processing", "Microelectronics",
           "Communication Systems", "Control Systems"],
    "ME": ["Thermal Engineering", "Design Engineering", "Manufacturing & Production", "Robotics & Automation",
           "Fluid Mechanics", "Automobile Engineering", "CAD/CAM"],
    "CE": ["Structural Engineering", "Geotechnical Engineering", "Transportation Engineering",
           "Environmental Engineering", "Water Resources Engineering", "Construction Management"],
    "CH": ["Process Engineering", "Reaction Engineering", "Petrochemical Engineering",
           "Environmental & Green Chemistry", "Polymer Engineering", "Process Control"],
    "SH": ["Applied Mathematics", "Applied Physics", "Engineering Chemistry", "English & Communication",
           "Economics & Management", "Environmental Science", "Electrical Engineering Fundamentals"],
}

# subject-area -> department that staffs it
AREA_OWNER: dict[str, str] = {}
for _dept, _areas in OWNED_AREAS.items():
    for _a in _areas:
        AREA_OWNER[_a] = _dept
for _a in ("MA", "PH", "BT", "HS", "EE", "YOG", "NSS", "NCC", "OE", "INT"):
    AREA_OWNER.setdefault(_a, "SH")

# ---------------------------------------------------------------------------
# Shared dev credentials — every user logs in with the same password.
# ---------------------------------------------------------------------------
DEV_PASSWORD = "uniassist"
_PW_SALT = b"uniassist-dev-static-salt"
_PW_DK = hashlib.pbkdf2_hmac("sha256", DEV_PASSWORD.encode(), _PW_SALT, 100_000)
PASSWORD_HASH = f"pbkdf2_sha256$100000${_PW_SALT.hex()}${_PW_DK.hex()}"


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def rand_date(rng: random.Random, start: dt.date, end: dt.date) -> dt.date:
    return start + dt.timedelta(days=rng.randint(0, (end - start).days))


def phone(rng: random.Random) -> str:
    return f"+91{rng.randint(6, 9)}{rng.randint(10**8, 10**9 - 1)}"


def slug(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def n_divisions(cohort: int) -> int:
    return max(1, math.ceil(cohort / DIVISION_SIZE))


def cohort_size(dept_code: str, sample: bool) -> int:
    if sample:
        return SAMPLE_STUDENT_COUNTS[dept_code]
    return next(d["students_per_batch"] for d in STUDENT_DEPARTMENTS if d["code"] == dept_code)


def division_of(seq: int) -> int:
    return (seq - 1) // DIVISION_SIZE + 1


def lab_group_of(seq: int, cohort: int, letter: str) -> str:
    div = division_of(seq)
    div_start = (div - 1) * DIVISION_SIZE
    div_size = min(DIVISION_SIZE, cohort - div_start)
    pos = (seq - 1) - div_start
    grp = 2 * div - 1 if pos < math.ceil(div_size / 2) else 2 * div
    return f"{letter}{grp}"


def uni_email(first: str, last: str, used: set) -> str:
    base = f"{slug(first)}.{slug(last)}"
    cand, n = f"{base}@{DOMAIN}", 2
    while cand in used:
        cand = f"{base}{n}@{DOMAIN}"
        n += 1
    used.add(cand)
    return cand


def personal_email(rng: random.Random, first: str, last: str, used: set) -> str:
    dom = rng.choice(["gmail.com", "gmail.com", "outlook.com", "yahoo.com"])
    base = f"{slug(first)}.{slug(last)}"
    cand = f"{base}{rng.randint(1, 999)}@{dom}"
    while cand in used:
        cand = f"{base}{rng.randint(1, 99999)}@{dom}"
    used.add(cand)
    return cand


# ---------------------------------------------------------------------------
# reference tables
# ---------------------------------------------------------------------------
def gen_departments():
    rows = []
    for i, d in enumerate(DEPARTMENTS, start=1):
        rows.append({"id": i, "code": d["code"], "name": d["name"],
                     "building": d["building"], "hod_faculty_id": None})
    return pd.DataFrame(rows)


def gen_subjects():
    rows = []
    for code, (name, category, lec, tut, prac, credits) in sorted(SUBJECTS.items()):
        rows.append({
            "subject_code": code, "subject_name": name, "category": category,
            "component": component(code), "lecture_hours": lec, "tutorial_hours": tut,
            "practical_hours": prac, "credits": credits,
        })
    return pd.DataFrame(rows)


def gen_curriculum(dept_id_by_code):
    rows, cid = [], 1
    for d in STUDENT_DEPARTMENTS:
        for semester in sorted(CURRICULUM[d["code"]]):
            for code in CURRICULUM[d["code"]][semester]:
                name, category, *_ = SUBJECTS[code]
                rows.append({
                    "id": cid, "dept_id": dept_id_by_code[d["code"]], "dept_code": d["code"],
                    "semester": semester, "subject_code": code, "subject_name": name,
                    "category": category, "is_elective": category in ("PE", "OE"),
                })
                cid += 1
    return pd.DataFrame(rows)


def gen_classrooms(dept_id_by_code):
    rows, cid = [], 1
    for d in DEPARTMENTS:
        if d["code"] == "SH":
            continue
        n_lec, n_lab = AD.CLASSROOM_PLAN[d["code"]]
        for k in range(1, n_lec + 1):
            floor = (k - 1) // 4 + 1
            rows.append({"id": cid, "code": f"{d['code']}-{floor}{k:02d}",
                         "building": d["building"], "capacity": AD.LECTURE_CAPACITY,
                         "room_type": "Lecture Hall", "dept_id": dept_id_by_code[d["code"]]})
            cid += 1
        for k in range(1, n_lab + 1):
            rows.append({"id": cid, "code": f"{d['code']}-L{k:02d}",
                         "building": d["building"], "capacity": AD.LAB_CAPACITY,
                         "room_type": "Laboratory", "dept_id": dept_id_by_code[d["code"]]})
            cid += 1
    # central seminar + exam halls
    for k in range(1, 4):
        rows.append({"id": cid, "code": f"SEM-{k:02d}", "building": "Central Block",
                     "capacity": AD.SEMINAR_CAPACITY, "room_type": "Seminar Hall",
                     "dept_id": dept_id_by_code["SH"]})
        cid += 1
    for k in range(1, 5):
        rows.append({"id": cid, "code": f"EXAM-H{k}", "building": "Central Block",
                     "capacity": AD.EXAM_HALL_CAPACITY, "room_type": "Examination Hall",
                     "dept_id": dept_id_by_code["SH"]})
        cid += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# people
# ---------------------------------------------------------------------------
def gen_faculty(rng: random.Random, sample: bool, dept_id_by_code):
    if sample:
        counts = {d["code"]: FACULTY_PER_DEPT_SAMPLE for d in DEPARTMENTS}
    else:
        weights = {d["code"]: max(2, d["students_per_batch"]) for d in DEPARTMENTS}
        weights["SH"] = 320  # SH carries a heavy service-teaching load
        total = sum(weights.values())
        counts, assigned = {}, 0
        for d in DEPARTMENTS[:-1]:
            c = max(3, round(FACULTY_TOTAL_FULL * weights[d["code"]] / total))
            counts[d["code"]] = c
            assigned += c
        counts[DEPARTMENTS[-1]["code"]] = max(6, FACULTY_TOTAL_FULL - assigned)

    rows, uni_used, pers_used = [], set(), set()
    fid = 1
    hod_by_dept = {}
    for d in DEPARTMENTS:
        n = counts[d["code"]]
        n_prof = max(1, round(n * 0.15))
        n_assoc = round(n * 0.32)
        desigs = (["Professor"] * n_prof + ["Associate Professor"] * n_assoc +
                  ["Assistant Professor"] * (n - n_prof - n_assoc))
        rng.shuffle(desigs)
        hod_idx = desigs.index("Professor") if "Professor" in desigs else 0
        for i in range(n):
            gender = rng.choice(["Male", "Male", "Female"])
            first, last = staff_name(rng, gender)
            full = f"Dr. {first} {last}"
            ue = uni_email(first, last, uni_used)
            rows.append({
                "id": fid, "employee_id": f"SOT-FAC-{fid:04d}", "full_name": full,
                "university_email": ue, "personal_email": personal_email(rng, first, last, pers_used),
                "gender": gender, "date_of_birth": rand_date(rng, dt.date(1963, 1, 1), dt.date(1996, 12, 31)).isoformat(),
                "phone": phone(rng), "dept_id": dept_id_by_code[d["code"]], "dept_code": d["code"],
                "designation": desigs[i], "is_hod": i == hod_idx,
                "date_of_joining": rand_date(rng, dt.date(2001, 6, 1), dt.date(2025, 7, 31)).isoformat(),
                "qualification": rng.choice(["PhD", "PhD", "PhD", "M.Tech", "M.E.", "PhD (Pursuing)"]),
                "specialization": rng.choice(SPECIALIZATIONS_BY_DEPT[d["code"]]),
                "office_room": f"{d['code'] if d['code'] != 'SH' else 'SH'}-{rng.randint(101, 340)}",
                "is_active": True,
            })
            if i == hod_idx:
                hod_by_dept[dept_id_by_code[d["code"]]] = fid
            fid += 1
    return pd.DataFrame(rows), hod_by_dept


def gen_admins(rng: random.Random):
    rows, uni_used, pers_used = [], set(), set()
    for i, desig in enumerate(ADMIN_DESIGNATIONS, start=1):
        gender = rng.choice(["Male", "Female"])
        first, last = staff_name(rng, gender)
        rows.append({
            "id": i, "employee_id": f"SOT-ADM-{i:03d}", "full_name": f"{first} {last}",
            "university_email": uni_email(first, last, uni_used),
            "personal_email": personal_email(rng, first, last, pers_used),
            "gender": gender,
            "date_of_birth": rand_date(rng, dt.date(1968, 1, 1), dt.date(1995, 12, 31)).isoformat(),
            "phone": phone(rng), "designation": desig,
            "date_of_joining": rand_date(rng, dt.date(2005, 1, 1), dt.date(2025, 7, 1)).isoformat(),
            "is_active": True,
        })
    return pd.DataFrame(rows)


def gen_students(rng: random.Random, sample: bool, dept_id_by_code):
    """Returns a list of mutable dicts (cgpa filled in later from past results)."""
    students, pers_used = [], set()
    sid = 1
    batches = SAMPLE_BATCHES if sample else FULL_BATCHES
    for batch in batches:
        yy = batch % 100
        for d in STUDENT_DEPARTMENTS:
            cohort = cohort_size(d["code"], sample)
            for seq in range(1, cohort + 1):
                gender = rng.choice(["Male", "Male", "Female"])
                first, last = student_name(rng, gender)
                roll = f"{yy:02d}B{d['code']}{seq:03d}"
                city, state = home_town(rng)
                twelfth = round(clamp(rng.gauss(84, 7), 58, 99), 2)
                tenth = round(clamp(rng.gauss(85, 7), 58, 99), 2)
                if batch == 2026:
                    adm = rand_date(rng, dt.date(2026, 6, 2), dt.date(2026, 6, 13))
                else:
                    adm = rand_date(rng, dt.date(batch, 6, 20), dt.date(batch, 8, 10))
                students.append({
                    "id": sid, "roll_no": roll, "full_name": f"{first} {last}",
                    "university_email": f"{roll.lower()}@{DOMAIN}",
                    "personal_email": personal_email(rng, first, last, pers_used),
                    "gender": gender,
                    "date_of_birth": rand_date(rng, dt.date(2026 - batch + 17, 1, 1),
                                               dt.date(2026 - batch + 19, 12, 31)).isoformat(),
                    "phone": phone(rng), "address_city": city, "address_state": state,
                    "dept_id": dept_id_by_code[d["code"]], "dept_code": d["code"],
                    "batch": batch, "semester": AD.CURRENT_SEM_BY_BATCH[batch],
                    "division": division_of(seq),
                    "lab_group": lab_group_of(seq, cohort, d["letter"]),
                    "tenth_percentage": tenth, "twelfth_percentage": twelfth,
                    "cgpa": None,
                    "is_hosteller": rng.random() < 0.45,
                    "guardian_name": f"{guardian_first_name(rng)} {last}",
                    "guardian_phone": phone(rng),
                    "admission_date": adm.isoformat(), "is_active": True,
                    "_seq": seq, "_ability": clamp(rng.gauss(0.42 + twelfth / 100 * 0.42, 0.11), 0.34, 0.98),
                })
                sid += 1
    return students


def gen_users(students, faculty_df, admins_df):
    rows, uid = [], 1
    for s in students:
        rows.append({"id": uid, "email": s["university_email"], "password_hash": PASSWORD_HASH,
                     "role": "student", "subject_ref": f"student:{s['id']}", "is_active": True,
                     "last_login_at": None})
        s["_user_id"] = uid
        uid += 1
    fac_user = {}
    for r in faculty_df.itertuples(index=False):
        rows.append({"id": uid, "email": r.university_email, "password_hash": PASSWORD_HASH,
                     "role": "faculty", "subject_ref": f"faculty:{r.id}", "is_active": True,
                     "last_login_at": None})
        fac_user[r.id] = uid
        uid += 1
    adm_user = {}
    for r in admins_df.itertuples(index=False):
        rows.append({"id": uid, "email": r.university_email, "password_hash": PASSWORD_HASH,
                     "role": "admin", "subject_ref": f"admin:{r.id}", "is_active": True,
                     "last_login_at": None})
        adm_user[r.id] = uid
        uid += 1
    return pd.DataFrame(rows), fac_user, adm_user


# ---------------------------------------------------------------------------
# offerings / enrollments
# ---------------------------------------------------------------------------
TERMS = [
    (AD.CURRENT_TERM, AD.CURRENT_SEM_BY_BATCH, False),
    (AD.PAST_TERM, AD.PAST_SEM_BY_BATCH, True),
]


def _faculty_pool(dept_code, faculty_df):
    pool = list(faculty_df[faculty_df["dept_code"] == dept_code]["id"])
    return pool or list(faculty_df["id"])


def gen_offerings(rng: random.Random, faculty_df, sample: bool, dept_id_by_code, batches):
    """One theory offering per division, one lab offering per lab group, one
    row for project / self-study subjects. Returns (df, list_of_dicts)."""
    pools = {d["code"]: _faculty_pool(d["code"], faculty_df) for d in DEPARTMENTS}
    rows, oid = [], 1
    for term, sem_by_batch, _completed in TERMS:
        for d in STUDENT_DEPARTMENTS:
            for batch, sem in sem_by_batch.items():
                if batch not in batches:
                    continue
                cohort = cohort_size(d["code"], sample)
                ndiv = n_divisions(cohort)
                for code in CURRICULUM[d["code"]][sem]:
                    name, category, *_ = SUBJECTS[code]
                    comp = component(code)
                    owner = AREA_OWNER.get(subject_area(code), d["code"])
                    pool = pools.get(owner) or pools[d["code"]]
                    is_project = category == "PRO" or code == "MOOC" or subject_area(code) == "INT"
                    if is_project:
                        kind = "Self-study" if code == "MOOC" else "Project"
                        rows.append(_offering_row(oid, code, name, d, dept_id_by_code, term, sem,
                                                  batch, rng.choice(pool), kind, "All", "", cohort))
                        oid += 1
                    elif comp == "Lab":
                        for g in range(1, 2 * ndiv + 1):
                            rows.append(_offering_row(oid, code, name, d, dept_id_by_code, term, sem,
                                                      batch, rng.choice(pool), "Lab", "",
                                                      f"{d['letter']}{g}", math.ceil(cohort / (2 * ndiv))))
                            oid += 1
                    else:
                        for div in range(1, ndiv + 1):
                            rows.append(_offering_row(oid, code, name, d, dept_id_by_code, term, sem,
                                                      batch, rng.choice(pool), "Theory", div, "",
                                                      min(DIVISION_SIZE, cohort - (div - 1) * DIVISION_SIZE)))
                            oid += 1
    df = pd.DataFrame(rows)
    return df, rows


def _offering_row(oid, code, name, dept, dept_id_by_code, term, sem, batch, fac_id, kind, div, lab_group, cap):
    return {
        "id": oid, "subject_code": code, "subject_name": name,
        "dept_id": dept_id_by_code[dept["code"]], "dept_code": dept["code"],
        "term": term, "semester": sem, "batch": batch, "faculty_id": fac_id,
        "session_type": kind, "division": div, "lab_group": lab_group,
        "capacity": cap,
    }


def gen_enrollments(rng: random.Random, students, offerings):
    """offering_id -> [student_id]; plus enrollment rows."""
    by_key = {}
    for o in offerings:
        by_key.setdefault((o["dept_code"], o["term"], o["semester"]), []).append(o)
    rows, eid = [], 1
    roster: dict[int, list[int]] = {}
    for s in students:
        for term, sem_by_batch, _c in TERMS:
            if s["batch"] not in sem_by_batch:
                continue
            sem = sem_by_batch[s["batch"]]
            for o in by_key.get((s["dept_code"], term, sem), []):
                if o["session_type"] == "Theory" and o["division"] != s["division"]:
                    continue
                if o["session_type"] == "Lab" and o["lab_group"] != s["lab_group"]:
                    continue
                cat = SUBJECTS[o["subject_code"]][1]
                status = "enrolled"
                if cat in ("PE", "OE") and rng.random() < 0.03:
                    status = "dropped"
                rows.append({"id": eid, "student_id": s["id"], "offering_id": o["id"],
                             "subject_code": o["subject_code"], "term": term, "status": status,
                             "enrolled_on": AD.TERM_WINDOWS[term]["teaching_start"].isoformat()})
                eid += 1
                if status == "enrolled":
                    roster.setdefault(o["id"], []).append(s["id"])
    return pd.DataFrame(rows), roster


# ---------------------------------------------------------------------------
# timetable (current term only)
# ---------------------------------------------------------------------------
LECTURE_DAY_PATTERNS = [[0, 2, 4], [1, 3, 5], [0, 2, 3], [1, 2, 4], [0, 3, 4], [1, 3, 4]]


def gen_timetable(rng: random.Random, offerings, classrooms_df):
    lec_rooms = {}
    lab_rooms = {}
    for r in classrooms_df.itertuples(index=False):
        if r.room_type == "Lecture Hall":
            lec_rooms.setdefault(r.dept_id, []).append(r.id)
        elif r.room_type == "Laboratory":
            lab_rooms.setdefault(r.dept_id, []).append(r.id)
    all_lec = [i for v in lec_rooms.values() for i in v]
    all_lab = [i for v in lab_rooms.values() for i in v]

    busy_room: set[tuple] = set()          # (room_id, day, period_idx)
    busy_section: set[tuple] = set()        # (dept_id, batch, division/lab_group, day, period_idx)
    rows, tid = [], 1

    cur = [o for o in offerings if o["term"] == AD.CURRENT_TERM
           and o["session_type"] in ("Theory", "Lab")]
    for o in cur:
        subj = SUBJECTS[o["subject_code"]]
        if o["session_type"] == "Theory":
            n_meet = min(AD.MAX_LECTURES_PER_WEEK, max(1, subj[2] + subj[3]))
            days = LECTURE_DAY_PATTERNS[o["id"] % len(LECTURE_DAY_PATTERNS)][:n_meet]
            rooms = lec_rooms.get(o["dept_id"], all_lec)
            sect = ("T", o["division"])
            for k, day in enumerate(days):
                pidx = _find_period(rng, o, day, sect, rooms, busy_room, busy_section,
                                    len(AD.PERIODS))
                if pidx is None:
                    continue
                room = _find_room(day, pidx, rooms, busy_room)
                busy_room.add((room, day, pidx))
                busy_section.add((o["dept_id"], o["batch"], sect, day, pidx))
                st, en = AD.PERIODS[pidx]
                rows.append({"id": tid, "offering_id": o["id"], "day_of_week": day,
                             "start_time": st, "end_time": en, "classroom_id": room,
                             "session_type": "Theory"})
                tid += 1
        else:
            rooms = lab_rooms.get(o["dept_id"], all_lab)
            day = [1, 2, 3, 4][o["id"] % 4]
            blk = o["id"] % len(AD.LAB_BLOCKS)
            room = _find_room_generic(day, f"lab{blk}", rooms, busy_room)
            busy_room.add((room, day, f"lab{blk}"))
            st, en = AD.LAB_BLOCKS[blk]
            rows.append({"id": tid, "offering_id": o["id"], "day_of_week": day,
                         "start_time": st, "end_time": en, "classroom_id": room,
                         "session_type": "Lab"})
            tid += 1
    return pd.DataFrame(rows)


def _find_period(rng, o, day, sect, rooms, busy_room, busy_section, n_periods):
    order = list(range(n_periods))
    rng.shuffle(order)
    for pidx in order:
        if (o["dept_id"], o["batch"], sect, day, pidx) in busy_section:
            continue
        if any((r, day, pidx) not in busy_room for r in rooms):
            return pidx
    return None


def _find_room(day, pidx, rooms, busy_room):
    for r in rooms:
        if (r, day, pidx) not in busy_room:
            return r
    return rooms[0]


def _find_room_generic(day, slot, rooms, busy_room):
    for r in rooms:
        if (r, day, slot) not in busy_room:
            return r
    return rooms[0]


# ---------------------------------------------------------------------------
# attendance  (streamed to CSV)
# ---------------------------------------------------------------------------
def _session_dates(term, session_type, offering_id, meets_per_week=3):
    w = AD.TERM_WINDOWS[term]
    end = AD.AS_OF if term == AD.CURRENT_TERM else w["teaching_end"]
    if session_type == "Theory":
        pat = LECTURE_DAY_PATTERNS[offering_id % len(LECTURE_DAY_PATTERNS)][:meets_per_week]
    else:
        pat = [[1, 2, 3, 4][offering_id % 4]]
    out, d = [], w["teaching_start"]
    while d <= end:
        if d.weekday() in pat and AD.is_class_day(d):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def gen_attendance(rng, offerings, roster, students_by_id, out_dir, forced):
    sess_path = out_dir / "attendance_sessions.csv"
    rec_path = out_dir / "attendance_records.csv"
    sid = rid = 1

    with open(sess_path, "w", newline="", encoding="utf-8") as sf, \
         open(rec_path, "w", newline="", encoding="utf-8") as rf:
        sw = csv.writer(sf)
        rw = csv.writer(rf)
        sw.writerow(["id", "offering_id", "subject_code", "session_date", "slot_no",
                     "marked_by", "marked_at", "topic_no"])
        rw.writerow(["id", "session_id", "student_id", "status"])

        teach = [o for o in offerings if o["session_type"] in ("Theory", "Lab")]
        for oi, o in enumerate(teach):
            enrolled = roster.get(o["id"], [])
            if not enrolled:
                continue
            subj = SUBJECTS[o["subject_code"]]
            n_meet = min(AD.MAX_LECTURES_PER_WEEK, max(1, subj[2] + subj[3]))
            dates = _session_dates(o["term"], o["session_type"], o["id"], n_meet)
            if not dates:
                continue
            # per-student present probability for this offering
            probs = {}
            for stu in enrolled:
                key = (o["id"], stu)
                if key in forced["attendance"]:
                    probs[stu] = None  # forced, handled below
                else:
                    ab = students_by_id[stu]["_ability"]
                    probs[stu] = clamp(rng.gauss(0.72 + ab * 0.22, 0.06), 0.5, 0.99)
            forced_plan = {}
            for stu in enrolled:
                if (o["id"], stu) in forced["attendance"]:
                    tgt = forced["attendance"][(o["id"], stu)]
                    npresent = round(len(dates) * tgt / 100.0)
                    forced_plan[stu] = {int(i * len(dates) / max(1, npresent))
                                        for i in range(npresent)}
            for k, day in enumerate(dates):
                sw.writerow([sid, o["id"], o["subject_code"], day.isoformat(),
                             "" if o["session_type"] == "Lab" else (k % 4) + 1,
                             o["faculty_id"], f"{day.isoformat()}T17:30:00", k + 1])
                for stu in enrolled:
                    if stu in forced_plan:
                        st = "present" if k in forced_plan[stu] else "absent"
                    else:
                        p = probs[stu]
                        r = rng.random()
                        if r < p:
                            st = "present"
                        else:
                            r2 = rng.random()
                            st = "absent" if r2 < 0.8 else ("late" if r2 < 0.95 else "excused")
                    rw.writerow([rid, sid, stu, st])
                    rid += 1
                sid += 1
            if (oi + 1) % 400 == 0:
                print(f"  attendance: {oi + 1}/{len(teach)} offerings, {rid:,} records")
    return sid - 1, rid - 1


# ---------------------------------------------------------------------------
# assessments / marks / submissions
# ---------------------------------------------------------------------------
def gen_assessments(rng, offerings, roster, students_by_id, forced):
    a_rows, m_rows, s_rows = [], [], []
    aid = mid = subid = 1
    for o in offerings:
        comp = o["session_type"]
        term = o["term"]
        w = AD.TERM_WINDOWS[term]
        enrolled = roster.get(o["id"], [])
        if not enrolled:
            continue

        if comp == "Theory":
            templates = AD.ASSESSMENT_TEMPLATE
        elif comp == "Lab":
            templates = [("Lab-CIE", "Lab Continuous Evaluation", 50, 60, 10, "lab"),
                         ("Lab-Exam", "Lab End Examination", 50, 40, 17, "lab")]
        else:  # Project / Self-study
            templates = [("Term-Work", "Term Work Evaluation", 100, 100, 16, "project")]

        for (atype, title, maxm, wt, week, kind) in templates:
            due = w["teaching_start"] + dt.timedelta(days=(week - 1) * 7 + rng.randint(0, 4))
            conducted = term == AD.PAST_TERM or due <= AD.AS_OF
            status = "graded" if conducted else "scheduled"
            a_rows.append({"id": aid, "offering_id": o["id"], "subject_code": o["subject_code"],
                           "term": term, "type": atype, "title": title, "max_marks": maxm,
                           "weightage_pct": wt, "due_date": due.isoformat(), "status": status})
            if conducted:
                fail_force = forced["fail"].get((o["id"], atype))
                fail_targets = set()
                if fail_force:
                    k = int(len(enrolled) * fail_force)
                    fail_targets = set(rng.sample(enrolled, k))
                for stu in enrolled:
                    ab = students_by_id[stu]["_ability"]
                    if stu in fail_targets:
                        frac = clamp(rng.gauss(0.28, 0.07), 0.0, 0.39)
                    else:
                        frac = clamp(rng.gauss(ab + 0.08, 0.11), 0.0, 1.0)
                    absent = rng.random() < 0.015
                    m_rows.append({"id": mid, "assessment_id": aid, "student_id": stu,
                                   "score": 0.0 if absent else round(maxm * frac, 1),
                                   "is_absent": absent,
                                   "graded_on": (due + dt.timedelta(days=rng.randint(4, 12))).isoformat()})
                    mid += 1
            if kind == "assignment":
                miss_force = forced["missing"].get((o["id"], atype), 0.05)
                for stu in enrolled:
                    r = rng.random()
                    if r < miss_force:
                        st, ts = "missing", ""
                    elif r < miss_force + 0.12:
                        st = "late"
                        ts = (due + dt.timedelta(days=rng.randint(1, 4))).isoformat() + "T23:00:00"
                    else:
                        st = "submitted"
                        ts = (due - dt.timedelta(days=rng.randint(0, 3))).isoformat() + "T21:00:00"
                    s_rows.append({"id": subid, "assessment_id": aid, "student_id": stu,
                                   "status": st, "submitted_at": ts})
                    subid += 1
            aid += 1
    return pd.DataFrame(a_rows), pd.DataFrame(m_rows), pd.DataFrame(s_rows)


# ---------------------------------------------------------------------------
# results (past term)
# ---------------------------------------------------------------------------
def _grade_point(pct):
    for cut, gp in [(90, 10), (80, 9), (70, 8), (60, 7), (50, 6), (45, 5), (40, 4)]:
        if pct >= cut:
            return gp
    return 0


def gen_results(offerings, assessments_df, marks_df, roster, students_by_id):
    a_by_id = {r.id: r for r in assessments_df.itertuples(index=False)}
    # student -> subject_code -> [(weight, frac)]
    acc: dict[int, dict[str, list]] = {}
    for m in marks_df.itertuples(index=False):
        a = a_by_id[m.assessment_id]
        if a.term != AD.PAST_TERM:
            continue
        frac = 0.0 if a.max_marks == 0 else m.score / a.max_marks
        acc.setdefault(m.student_id, {}).setdefault(a.subject_code, []).append((a.weightage_pct, frac))

    rows, rid = [], 1
    sgpa_by_student = {}
    for stu, subjects in acc.items():
        s = students_by_id[stu]
        tot_cred = tot_pts = cred_earned = 0
        fail_cnt = 0
        for code, parts in subjects.items():
            wsum = sum(w for w, _ in parts) or 1
            pct = sum(w * f for w, f in parts) / wsum * 100
            gp = _grade_point(pct)
            cred = SUBJECTS[code][5]
            tot_cred += cred
            tot_pts += gp * cred
            if gp == 0:
                if SUBJECTS[code][1] in ("PC", "BSC", "ESC"):
                    fail_cnt += 1
            else:
                cred_earned += cred
        sgpa = round(tot_pts / tot_cred, 2) if tot_cred else 0.0
        sgpa_by_student[stu] = sgpa
        rows.append({"id": rid, "student_id": stu, "roll_no": s["roll_no"],
                     "term": AD.PAST_TERM, "semester": AD.PAST_SEM_BY_BATCH[s["batch"]],
                     "credits_registered": tot_cred, "credits_earned": cred_earned,
                     "sgpa": sgpa, "cgpa": sgpa,
                     "result_status": "ATKT" if fail_cnt else "Pass",
                     "backlogs": fail_cnt,
                     "declared_on": AD.TERM_WINDOWS[AD.PAST_TERM]["result_date"].isoformat()})
        rid += 1

    # backfill student cgpa
    for s in students_by_id.values():
        if s["batch"] == 2026:
            s["cgpa"] = None
        else:
            s["cgpa"] = sgpa_by_student.get(s["id"], round(clamp(4.5 + s["_ability"] * 5.5, 5.0, 9.9), 2))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# exam schedule
# ---------------------------------------------------------------------------
def gen_exam_schedule(rng, offerings, classrooms_df, dept_id_by_code):
    halls = list(classrooms_df[classrooms_df["room_type"] == "Examination Hall"]["id"])
    seen = set()
    rows, xid = [], 1
    specs = [
        (AD.PAST_TERM, "End-Sem", AD.TERM_WINDOWS[AD.PAST_TERM]["exam_start"],
         AD.TERM_WINDOWS[AD.PAST_TERM]["exam_end"], "completed"),
        (AD.CURRENT_TERM, "Internal-1", dt.date(2026, 8, 20), dt.date(2026, 8, 25), "completed"),
        (AD.CURRENT_TERM, "Internal-2", dt.date(2026, 9, 21), dt.date(2026, 9, 26), "scheduled"),
        (AD.CURRENT_TERM, "End-Sem", AD.TERM_WINDOWS[AD.CURRENT_TERM]["exam_start"],
         AD.TERM_WINDOWS[AD.CURRENT_TERM]["exam_end"], "scheduled"),
    ]
    for term, xtype, w_start, w_end, status in specs:
        for o in offerings:
            if o["term"] != term or o["session_type"] != "Theory":
                continue
            key = (term, xtype, o["dept_code"], o["semester"], o["subject_code"])
            if key in seen:
                continue
            seen.add(key)
            span = (w_end - w_start).days
            d = w_start + dt.timedelta(days=(o["semester"] + hash(o["subject_code"])) % max(1, span))
            start = rng.choice(["10:00", "10:00", "14:00"])
            end = "12:00" if start == "10:00" else "16:00"
            if xtype != "End-Sem":
                end = "11:30" if start == "10:00" else "15:30"
            rows.append({"id": xid, "term": term, "exam_type": xtype,
                         "subject_code": o["subject_code"], "subject_name": o["subject_name"],
                         "dept_code": o["dept_code"], "semester": o["semester"],
                         "exam_date": d.isoformat(), "start_time": start, "end_time": end,
                         "classroom_id": rng.choice(halls), "status": status})
            xid += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# fees / scholarships / leave / documents
# ---------------------------------------------------------------------------
def gen_fees(rng, students_by_id, forced):
    rows, fid = [], 1
    for s in students_by_id.values():
        base = AD.TUITION_PER_SEM + AD.OTHER_FEES_PER_SEM + (AD.HOSTEL_FEE_PER_SEM if s["is_hosteller"] else 0)
        # past term (senior batches) — fully paid
        if s["batch"] != 2026:
            rows.append({"id": fid, "student_id": s["id"], "roll_no": s["roll_no"],
                         "term": AD.PAST_TERM, "amount_due": base, "amount_paid": base,
                         "status": "paid", "due_date": "2026-01-15",
                         "paid_on": rand_date(rng, dt.date(2026, 1, 3), dt.date(2026, 1, 14)).isoformat()})
            fid += 1
        # current term
        forced_unpaid = s["roll_no"] == forced["fee_roll"]
        status = "unpaid" if forced_unpaid else rng.choice(AD.FEE_STATUSES)
        if status == "paid":
            paid, pon = base, rand_date(rng, dt.date(2026, 6, 20), dt.date(2026, 9, 10)).isoformat()
        elif status == "partial":
            paid, pon = round(base * rng.uniform(0.3, 0.7), -2), rand_date(rng, dt.date(2026, 7, 1), dt.date(2026, 8, 20)).isoformat()
        else:
            paid, pon = 0, ""
        rows.append({"id": fid, "student_id": s["id"], "roll_no": s["roll_no"],
                     "term": AD.CURRENT_TERM, "amount_due": base, "amount_paid": paid,
                     "status": status, "due_date": "2026-09-12", "paid_on": pon})
        fid += 1
    return pd.DataFrame(rows)


def gen_scholarships(rng, students_by_id, forced):
    rows, scid = [], 1
    for s in students_by_id.values():
        forced_row = s["roll_no"] == forced["fee_roll"]
        if not forced_row and rng.random() > 0.18:
            continue
        if forced_row:
            name = forced["fee_scholarship"]
            amount = next(a for n, a in AD.SCHOLARSHIP_NAMES if n == name)
            status = "pending"
        else:
            name, amount = rng.choice(AD.SCHOLARSHIP_NAMES)
            status = rng.choice(AD.SCHOLARSHIP_STATUSES)
        rows.append({"id": scid, "student_id": s["id"], "roll_no": s["roll_no"],
                     "name": name, "amount": amount, "term": AD.CURRENT_TERM, "status": status,
                     "applied_on": rand_date(rng, dt.date(2026, 6, 20), dt.date(2026, 8, 10)).isoformat(),
                     "decided_on": "" if status == "pending" else
                     rand_date(rng, dt.date(2026, 8, 1), dt.date(2026, 8, 25)).isoformat()})
        scid += 1
    return pd.DataFrame(rows)


def gen_leave_requests(rng, students_by_id, faculty_df, dept_faculty, forced):
    rows, lid = [], 1
    pending_rolls = set(forced["pending_leave_rolls"])
    for s in students_by_id.values():
        want = s["roll_no"] in pending_rolls
        if not want and rng.random() > 0.22:
            continue
        n = 1 if not want else 1
        for _ in range(n if not want else 1):
            frm = rand_date(rng, dt.date(2026, 7, 1), dt.date(2026, 8, 20))
            to = frm + dt.timedelta(days=rng.randint(0, 4))
            if want:
                frm = rand_date(rng, dt.date(2026, 9, 1), dt.date(2026, 9, 12))
                to = frm + dt.timedelta(days=rng.randint(1, 3))
                status, decider, decided = "pending", "", ""
            else:
                status = rng.choice(AD.LEAVE_STATUSES)
                if status == "pending":
                    decider, decided = "", ""
                else:
                    decider = rng.choice(dept_faculty.get(s["dept_code"], list(faculty_df["id"])))
                    decided = (to + dt.timedelta(days=rng.randint(1, 5))).isoformat()
            rows.append({"id": lid, "student_id": s["id"], "roll_no": s["roll_no"],
                         "from_date": frm.isoformat(), "to_date": to.isoformat(),
                         "reason": rng.choice(AD.LEAVE_REASONS), "status": status,
                         "applied_on": (frm - dt.timedelta(days=rng.randint(2, 10))).isoformat(),
                         "decided_by": decider, "decided_on": decided})
            lid += 1
    return pd.DataFrame(rows)


def gen_document_requests(rng, students_by_id):
    rows, did = [], 1
    for s in students_by_id.values():
        if rng.random() > 0.16:
            continue
        req = rand_date(rng, dt.date(2026, 6, 20), dt.date(2026, 8, 25))
        status = rng.choice(AD.DOC_STATUSES)
        rows.append({"id": did, "student_id": s["id"], "roll_no": s["roll_no"],
                     "doc_type": rng.choice(AD.DOC_TYPES), "purpose": rng.choice(AD.DOC_PURPOSES),
                     "status": status, "requested_on": req.isoformat(),
                     "ready_on": "" if status not in ("ready",) else
                     (req + dt.timedelta(days=rng.randint(2, 7))).isoformat()})
        did += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# announcements / calendar
# ---------------------------------------------------------------------------
def gen_announcements(rng, offerings, departments_df, faculty_df, fac_user, adm_user, hod_by_dept):
    rows, anid = [], 1
    admin_uids = list(adm_user.values())
    for title, body in AD.UNIVERSITY_ANNOUNCEMENTS:
        rows.append({"id": anid, "author_user_id": rng.choice(admin_uids), "scope": "university",
                     "scope_ref": "", "title": title, "body": body,
                     "audience_roles": "student,faculty,admin",
                     "posted_at": rand_date(rng, dt.date(2026, 7, 15), dt.date(2026, 8, 26)).isoformat() + "T09:00:00"})
        anid += 1
    for d in departments_df.itertuples(index=False):
        if d.code == "SH":
            continue
        hod_fac = hod_by_dept.get(d.id)
        author = fac_user.get(hod_fac, rng.choice(admin_uids))
        for title_t, body_t in rng.sample(AD.DEPT_ANNOUNCEMENT_TEMPLATES, k=2):
            when = rand_date(rng, dt.date(2026, 8, 1), dt.date(2026, 9, 20))
            rows.append({"id": anid, "author_user_id": author, "scope": "department",
                         "scope_ref": d.code,
                         "title": title_t, "body": body_t.format(dept=d.name, date=when.strftime("%d %b %Y")),
                         "audience_roles": "student,faculty",
                         "posted_at": rand_date(rng, dt.date(2026, 7, 20), dt.date(2026, 8, 25)).isoformat() + "T10:30:00"})
            anid += 1
    cur_theory = [o for o in offerings if o["term"] == AD.CURRENT_TERM and o["session_type"] == "Theory"]
    for o in rng.sample(cur_theory, k=min(14, len(cur_theory))):
        title_t, body_t = rng.choice(AD.COURSE_ANNOUNCEMENT_TEMPLATES)
        when = rand_date(rng, dt.date(2026, 8, 10), dt.date(2026, 9, 5))
        rows.append({"id": anid, "author_user_id": fac_user.get(o["faculty_id"], rng.choice(admin_uids)),
                     "scope": "course", "scope_ref": o["subject_code"],
                     "title": title_t.format(course=o["subject_name"]),
                     "body": body_t.format(course=o["subject_name"], date=when.strftime("%d %b %Y")),
                     "audience_roles": "student",
                     "posted_at": rand_date(rng, dt.date(2026, 8, 12), dt.date(2026, 8, 26)).isoformat() + "T18:00:00"})
        anid += 1
    return pd.DataFrame(rows)


def gen_academic_calendar():
    rows = []
    for i, (event, etype, start, end, applies) in enumerate(AD.CALENDAR_EVENTS, start=1):
        term = AD.PAST_TERM if start < dt.date(2026, 6, 14) else AD.CURRENT_TERM
        rows.append({"id": i, "event": event, "event_type": etype,
                     "start_date": start.isoformat(),
                     "end_date": end.isoformat() if end else "",
                     "applies_to": applies, "term": term, "source_chunk_id": ""})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="tiny sample dataset")
    args = ap.parse_args()
    sample = args.sample

    rng = random.Random(SEED)
    batches = SAMPLE_BATCHES if sample else FULL_BATCHES

    out_dir = Path(__file__).resolve().parent.parent / "data" / "synthetic" / ("sample" if sample else "")
    out_dir.mkdir(parents=True, exist_ok=True)

    dept_id_by_code = {d["code"]: i for i, d in enumerate(DEPARTMENTS, start=1)}

    print("reference tables ...")
    departments_df = gen_departments()
    subjects_df = gen_subjects()
    curriculum_df = gen_curriculum(dept_id_by_code)
    classrooms_df = gen_classrooms(dept_id_by_code)

    print("people ...")
    faculty_df, hod_by_dept = gen_faculty(rng, sample, dept_id_by_code)
    for did, fid in hod_by_dept.items():
        departments_df.loc[departments_df["id"] == did, "hod_faculty_id"] = fid
    admins_df = gen_admins(rng)
    students = gen_students(rng, sample, dept_id_by_code)
    students_by_id = {s["id"]: s for s in students}
    users_df, fac_user, adm_user = gen_users(students, faculty_df, admins_df)

    dept_faculty = {d["code"]: list(faculty_df[faculty_df["dept_code"] == d["code"]]["id"])
                    for d in DEPARTMENTS}

    print("offerings / enrollments ...")
    offerings_df, offerings = gen_offerings(rng, faculty_df, sample, dept_id_by_code, batches)
    enrollments_df, roster = gen_enrollments(rng, students, offerings)

    print("timetable ...")
    timetable_df = gen_timetable(rng, offerings, classrooms_df)

    # ---- resolve planted demo cases to concrete ids -----------------------
    roll_to_id = {s["roll_no"]: s["id"] for s in students}
    forced = {
        "attendance": {}, "fail": {}, "missing": {},
        "fee_roll": AD.DEMO["fee_roll"], "fee_scholarship": AD.DEMO["fee_scholarship"],
        "pending_leave_rolls": AD.DEMO["pending_leave_rolls"],
    }
    demo_sid = roll_to_id.get(AD.DEMO["attendance_roll"])
    for o in offerings:
        if o["term"] != AD.CURRENT_TERM:
            continue
        if demo_sid and o["subject_code"] == AD.DEMO["attendance_subject"] \
                and demo_sid in roster.get(o["id"], []):
            forced["attendance"][(o["id"], demo_sid)] = AD.DEMO["attendance_target_pct"]
        if o["subject_code"] == AD.DEMO["fail_subject"] and o["session_type"] == "Theory":
            forced["fail"][(o["id"], AD.DEMO["fail_assessment"])] = AD.DEMO["fail_rate"]
        if o["subject_code"] == AD.DEMO["missing_subject"] and o["session_type"] == "Theory":
            forced["missing"][(o["id"], AD.DEMO["missing_assessment"])] = AD.DEMO["missing_rate"]

    print("assessments / marks / submissions ...")
    assessments_df, marks_df, submissions_df = gen_assessments(rng, offerings, roster, students_by_id, forced)

    print("results ...")
    results_df = gen_results(offerings, assessments_df, marks_df, roster, students_by_id)

    print("exam schedule ...")
    exam_df = gen_exam_schedule(rng, offerings, classrooms_df, dept_id_by_code)

    print("administrative ...")
    fees_df = gen_fees(rng, students_by_id, forced)
    scholarships_df = gen_scholarships(rng, students_by_id, forced)
    leave_df = gen_leave_requests(rng, students_by_id, faculty_df, dept_faculty, forced)
    docs_df = gen_document_requests(rng, students_by_id)
    announcements_df = gen_announcements(rng, offerings, departments_df, faculty_df,
                                        fac_user, adm_user, hod_by_dept)
    calendar_df = gen_academic_calendar()

    print("attendance (streamed) ...")
    n_sess, n_rec = gen_attendance(rng, offerings, roster, students_by_id, out_dir, forced)

    # ---- finalise + write ----------------------------------------------------
    students_df = pd.DataFrame([{k: v for k, v in s.items() if not k.startswith("_")}
                                for s in students])

    tables = {
        "departments": departments_df, "subjects": subjects_df, "curriculum": curriculum_df,
        "classrooms": classrooms_df, "faculty": faculty_df, "admins": admins_df,
        "students": students_df, "users": users_df,
        "course_offerings": offerings_df, "enrollments": enrollments_df,
        "timetable_slots": timetable_df, "assessments": assessments_df, "marks": marks_df,
        "submissions": submissions_df, "results_semester": results_df, "exam_schedule": exam_df,
        "fees": fees_df, "scholarships": scholarships_df, "leave_requests": leave_df,
        "document_requests": docs_df, "announcements": announcements_df,
        "academic_calendar": calendar_df,
    }
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)

    _write_readme(out_dir, tables, n_sess, n_rec, sample)

    print(f"\noutput dir: {out_dir}")
    for name, df in tables.items():
        print(f"  {name:22s} {len(df):>8,}")
    print(f"  {'attendance_sessions':22s} {n_sess:>8,}")
    print(f"  {'attendance_records':22s} {n_rec:>8,}")


def _write_readme(out_dir, tables, n_sess, n_rec, sample):
    d = AD.DEMO
    present_rolls = set(tables["students"]["roll_no"])
    leave_rolls = [r for r in d["pending_leave_rolls"] if r in present_rolls]
    leave_note = "" if len(leave_rolls) == len(d["pending_leave_rolls"]) else \
        " (others are 2024-batch rolls not present in this dataset)"
    lines = [
        "# UniAssist synthetic dataset",
        "",
        f"Generated by `scripts/generate_synthetic_data.py`{'  --sample' if sample else ''} "
        f"(seed {SEED}, deterministic).",
        "",
        f"- Terms: `{AD.CURRENT_TERM}` (in progress, as-of {AD.AS_OF.isoformat()}) "
        f"and `{AD.PAST_TERM}` (completed, with results).",
        "- Names are Gujarati-origin; student home towns are Gujarat-weighted.",
        "",
        "## Login",
        "",
        f"Every row in `users.csv` shares the dev password **`{DEV_PASSWORD}`** "
        "(`password_hash` = PBKDF2-SHA256, 100k iterations, static salt).",
        "Log in with any `university_email` from `students.csv` / `faculty.csv` / `admins.csv`.",
        "",
        "## Tables",
        "",
        "| table | rows |",
        "|---|---|",
    ]
    for name, df in tables.items():
        lines.append(f"| {name} | {len(df):,} |")
    lines += [
        f"| attendance_sessions | {n_sess:,} |",
        f"| attendance_records | {n_rec:,} |",
        "",
        "Not generated here (populated later): `conversations`, `messages`, `documents`, "
        "`doc_chunks`, `audit_log` (runtime + RAG ingest); `syllabus_units`, "
        "`course_outcomes`, `textbooks`, `course_prerequisites` (Phase-3 PDF extractor).",
        "",
        "## Planted demo edge cases",
        "",
        f"- **~68% attendance**: student `{d['attendance_roll']}` in "
        f"`{d['attendance_subject']}` (Database Management System), current term.",
        f"- **~35% Internal-1 fail rate**: `{d['fail_subject']}` (Digital Logic and Design), "
        "current term.",
        f"- **missing Assignment 2**: ~{int(d['missing_rate']*100)}% of the "
        f"`{d['missing_subject']}` cohort, `submissions.status = 'missing'`.",
        f"- **unpaid fees + pending scholarship**: student `{d['fee_roll']}` "
        f"(`fees.status='unpaid'`, `scholarships.status='pending'`).",
        f"- **pending leave requests** (for decide_leave_request): "
        f"{', '.join(leave_rolls)}{leave_note}.",
    ]
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
