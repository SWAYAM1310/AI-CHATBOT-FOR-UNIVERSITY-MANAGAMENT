"""Convert the generated CSVs to the university's grading scheme.

    python scripts/regrade_dataset.py        # data/synthetic and data/synthetic/sample

Every course is out of 100:

    Theory     IA 25 (one per semester: the assignment/project the instructor sets)
               Mid-Sem 25
               End-Sem 50 (written out of 100, counted as 50)
    Practical  Mid-Sem viva 25, practical lab file 25, end-semester practical exam 50
    Project    Term-Work 100 (unchanged)

The old scheme (Quiz-1, Assignment-1/2, Internal-1/2, Lab-CIE) is folded into the new
components, so each student keeps their standing rather than getting fresh random marks:

    IA            Quiz-1 + Assignment-1/2 by their old weightage, rescaled to 25. The IA is
                  the one submitted piece of work: Assignment-2's submission record becomes
                  the IA's, and a missing submission scores 0, a late one loses 25 per cent
                  (Examination Regulations 2.4). Dated and graded like Assignment-2.
    Mid-Sem       Internal-1 rescaled from 20 to 25, on Internal-1's exam day.
                  Internal-2 has no counterpart and is dropped.
    End-Sem       unchanged marks out of 100; weightage 40 -> 50.
    Mid-Sem viva  Lab-CIE's share with a small per-student wobble, on Lab-CIE's day.
    Lab file      the same, due a week before the practical exam.
    Lab-Exam      unchanged marks out of 50; weightage 40 -> 50.

The exam schedule, academic calendar and announcements are renamed to match, and the
declared past-term results (SGPA, credits, backlogs, the student's CGPA) are recomputed
from the converted marks the same way the generator computes them.

Idempotent: a dataset already on the new scheme is left alone. Patched in place rather
than regenerated, for the reason given in fix_dataset.py.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data" / "synthetic"
AS_OF = dt.date(2026, 8, 27)  # academic_data.AS_OF: what the generator treats as already held
PAST_TERM = "2025-26-EVEN"

OLD_TYPES = {"Quiz-1", "Assignment-1", "Assignment-2", "Internal-1", "Internal-2", "Lab-CIE"}
IA_PARTS = {"Quiz-1": 5, "Assignment-1": 7, "Assignment-2": 8}  # their old weightage
LATE_FACTOR = 0.75

# type, title, max_marks, weightage_pct
THEORY = [("IA", "Internal Assessment", 25, 25), ("Mid-Sem", "Mid Semester Exam", 25, 25), ("End-Sem", "End Semester Exam", 100, 50)]
LAB = [
    ("Mid-Sem-Viva", "Mid Semester Viva", 25, 25),
    ("Lab-File", "Practical Lab File", 25, 25),
    ("Lab-Exam", "End Semester Practical Exam", 50, 50),
]

ANNOUNCEMENT_TEXT = [
    ("Internal Test 1 timetable published", "Mid Semester Examination timetable published"),
    ("The consolidated Internal Test 1 schedule", "The consolidated Mid Semester Examination schedule"),
    ("Tests run from 20 to 25 August 2026.", "Examinations run from 20 to 25 August 2026."),
    ("Internal Test 1 will cover these units.", "The mid-semester exam will cover these units."),
    ("Assignment 2 deadline reminder", "IA submission deadline reminder"),
    ("Assignment 2 for ", "The IA work for "),
]


def read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def half_step(x: float, top: float) -> str:
    """Whole or half marks (7, 7.5), inside 0..top, written as the generator writes them."""
    return str(min(top, max(0.0, math.floor(x * 2 + 0.5) / 2)))


def wobble(*key: object) -> float:
    """A stable -0.06..0.06 nudge, so a viva and a lab file are not copies of each other."""
    return (zlib.crc32("|".join(map(str, key)).encode()) % 1201 - 600) / 10000


def share(m: dict[str, str], top: float) -> float:
    return 0.0 if m["is_absent"] == "True" or not m["score"] else float(m["score"]) / top


def fmt(x: float) -> str:
    return str(int(x)) if x == int(x) else str(x)


def grade_point(pct: float) -> int:  # generate_synthetic_data._grade_point
    for cut, gp in [(90, 10), (80, 9), (70, 8), (60, 7), (50, 6), (45, 5), (40, 4)]:
        if pct >= cut:
            return gp
    return 0


def convert(folder: Path) -> None:
    a_fields, assessments = read(folder / "assessments.csv")
    if not any(a["type"] in OLD_TYPES for a in assessments):
        print(f"{folder.name}: already on the new scheme")
        return
    m_fields, marks = read(folder / "marks.csv")
    s_fields, submissions = read(folder / "submissions.csv")
    session = {o["id"]: o["session_type"] for o in read(folder / "course_offerings.csv")[1]}

    marks_of: dict[str, dict[str, dict[str, str]]] = {}
    for m in marks:
        marks_of.setdefault(m["assessment_id"], {})[m["student_id"]] = m
    subs_of: dict[str, dict[str, dict[str, str]]] = {}
    for s in submissions:
        subs_of.setdefault(s["assessment_id"], {})[s["student_id"]] = s

    by_offering: dict[str, dict[str, dict[str, str]]] = {}
    for a in assessments:
        by_offering.setdefault(a["offering_id"], {})[a["type"]] = a

    new_a: list[dict[str, str]] = []
    new_m: list[dict[str, str]] = []
    new_s: list[dict[str, str]] = []

    def add(src: dict[str, str], spec: tuple, due: str, status: str) -> str:
        atype, title, top, weight = spec
        aid = str(len(new_a) + 1)
        new_a.append({**src, "id": aid, "type": atype, "title": title, "max_marks": str(top),
                      "weightage_pct": str(weight), "due_date": due, "status": status})
        return aid

    def mark(aid: str, student: str, score: str, absent: bool, graded_on: str) -> None:
        new_m.append({"id": str(len(new_m) + 1), "assessment_id": aid, "student_id": student,
                      "score": score, "is_absent": str(absent), "graded_on": graded_on})

    for offering, old in by_offering.items():
        kind = session.get(offering)
        if kind == "Theory":
            a2, int1, end = old["Assignment-2"], old["Internal-1"], old["End-Sem"]

            ia = add(a2, THEORY[0], a2["due_date"], a2["status"])
            for sub in subs_of.get(a2["id"], {}).values():
                new_s.append({**sub, "id": str(len(new_s) + 1), "assessment_id": ia})
            for student, m2 in marks_of.get(a2["id"], {}).items():
                parts = [(w, marks_of.get(old[t]["id"], {}).get(student), float(old[t]["max_marks"])) for t, w in IA_PARTS.items()]
                parts = [(w, m, top) for w, m, top in parts if m is not None]
                absent = all(m["is_absent"] == "True" for _, m, _ in parts)
                frac = sum(w * share(m, top) for w, m, top in parts) / sum(w for w, _, _ in parts)
                status = subs_of.get(a2["id"], {}).get(student, {}).get("status")
                frac = 0.0 if status == "missing" else frac * LATE_FACTOR if status == "late" else frac
                mark(ia, student, "0.0" if absent else half_step(25 * frac, 25), absent, m2["graded_on"])

            mid = add(int1, THEORY[1], int1["due_date"], int1["status"])
            for student, m in marks_of.get(int1["id"], {}).items():
                absent = m["is_absent"] == "True"
                mark(mid, student, "0.0" if absent else half_step(25 * share(m, 20), 25), absent, m["graded_on"])

            ese = add(end, THEORY[2], end["due_date"], end["status"])
            for m in marks_of.get(end["id"], {}).values():
                mark(ese, m["student_id"], m["score"], m["is_absent"] == "True", m["graded_on"])

        elif kind == "Lab":
            cie, exam = old["Lab-CIE"], old["Lab-Exam"]
            cie_marks = marks_of.get(cie["id"], {})

            viva = add(cie, LAB[0], cie["due_date"], cie["status"])
            for student, m in cie_marks.items():
                absent = m["is_absent"] == "True"
                score = "0.0" if absent else half_step(25 * (share(m, 50) + wobble(student, offering, "viva")), 25)
                mark(viva, student, score, absent, m["graded_on"])

            file_due = dt.date.fromisoformat(exam["due_date"]) - dt.timedelta(days=7)
            held = cie["term"] == PAST_TERM or file_due <= AS_OF
            lab_file = add(cie, LAB[1], file_due.isoformat(), "graded" if held else "scheduled")
            if held:
                for student, m in cie_marks.items():
                    graded_on = (file_due + dt.timedelta(days=3 + zlib.crc32(f"{student}{offering}".encode()) % 6)).isoformat()
                    mark(lab_file, student, half_step(25 * (share(m, 50) + wobble(student, offering, "file")), 25), False, graded_on)

            pex = add(exam, LAB[2], exam["due_date"], exam["status"])
            for m in marks_of.get(exam["id"], {}).values():
                mark(pex, m["student_id"], m["score"], m["is_absent"] == "True", m["graded_on"])

        else:  # project / internship: one Term-Work out of 100, as before
            for a in old.values():
                aid = add(a, (a["type"], a["title"], a["max_marks"], a["weightage_pct"]), a["due_date"], a["status"])
                for m in marks_of.get(a["id"], {}).values():
                    mark(aid, m["student_id"], m["score"], m["is_absent"] == "True", m["graded_on"])

    write(folder / "assessments.csv", a_fields, new_a)
    write(folder / "marks.csv", m_fields, new_m)
    write(folder / "submissions.csv", s_fields, new_s)

    # exam schedule: Internal Test 1's sitting is the mid-semester exam; Internal Test 2 is gone
    x_fields, exams = read(folder / "exam_schedule.csv")
    exams = [{**x, "exam_type": "Mid-Sem" if x["exam_type"] == "Internal-1" else x["exam_type"]} for x in exams if x["exam_type"] != "Internal-2"]
    write(folder / "exam_schedule.csv", x_fields, exams)

    c_fields, calendar = read(folder / "academic_calendar.csv")
    calendar = [{**c, "event": "Mid Semester Examination" if c["event"] == "Internal Test 1" else c["event"]} for c in calendar if c["event"] != "Internal Test 2"]
    write(folder / "academic_calendar.csv", c_fields, calendar)

    n_fields, notices = read(folder / "announcements.csv")
    for n in notices:
        for field in ("title", "body"):
            for old_text, new_text in ANNOUNCEMENT_TEXT:
                n[field] = n[field].replace(old_text, new_text)
    write(folder / "announcements.csv", n_fields, notices)

    recompute_results(folder, new_a, new_m)
    print(f"{folder.name}: {len(new_a)} assessments, {len(new_m)} marks, {len(new_s)} submissions")


def recompute_results(folder: Path, assessments: list[dict[str, str]], marks: list[dict[str, str]]) -> None:
    """generate_synthetic_data.gen_results over the converted marks."""
    subjects = {s["subject_code"]: s for s in read(folder / "subjects.csv")[1]}
    a_by_id = {a["id"]: a for a in assessments}
    acc: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for m in marks:
        a = a_by_id[m["assessment_id"]]
        if a["term"] != PAST_TERM:
            continue
        frac = float(m["score"] or 0) / float(a["max_marks"])
        acc.setdefault(m["student_id"], {}).setdefault(a["subject_code"], []).append((float(a["weightage_pct"]), frac))

    r_fields, results = read(folder / "results_semester.csv")
    sgpa_of: dict[str, str] = {}
    for r in results:
        subjects_taken = acc.get(r["student_id"])
        if r["term"] != PAST_TERM or not subjects_taken:
            continue
        credits = points = earned = backlogs = 0.0
        for code, parts in subjects_taken.items():
            pct = sum(w * f for w, f in parts) / (sum(w for w, _ in parts) or 1) * 100
            gp = grade_point(pct)
            cred = float(subjects[code]["credits"])
            credits += cred
            points += gp * cred
            if gp:
                earned += cred
            elif subjects[code]["category"] in ("PC", "BSC", "ESC"):
                backlogs += 1
        sgpa = str(round(points / credits, 2)) if credits else "0.0"
        r.update({"credits_registered": fmt(credits), "credits_earned": fmt(earned), "sgpa": sgpa, "cgpa": sgpa,
                  "result_status": "ATKT" if backlogs else "Pass", "backlogs": str(int(backlogs))})
        sgpa_of[r["student_id"]] = sgpa
    write(folder / "results_semester.csv", r_fields, results)

    st_fields, students = read(folder / "students.csv")
    for s in students:
        if s["id"] in sgpa_of:
            s["cgpa"] = sgpa_of[s["id"]]
    write(folder / "students.csv", st_fields, students)


if __name__ == "__main__":
    for folder in (ROOT, ROOT / "sample"):
        convert(folder)
