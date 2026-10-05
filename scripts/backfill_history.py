"""Give every student their earlier semesters, which the generator never made.

    python scripts/backfill_history.py        # data/synthetic and data/synthetic/sample

The generator builds two terms only, the past one (2025-26-EVEN) and the current one,
so a semester-3 student had no semester 1, a semester-5 student no semesters 1-3 and a
semester-7 student no semesters 1-5, and everyone's CGPA was just last term's SGPA.
This adds each missing completed semester, the way the generator would have built it:

- offerings from the same curriculum (one theory section per division, one lab per
  lab group, one row for project work), taught by the owning department's faculty
- completed enrollments in the student's own division and lab group
- assessments on the university scheme (see regrade_dataset.py), all graded, with
  marks drawn around the student's own average share in the existing data, so a
  strong student stays strong; IA submissions mostly on time, a few late or missing
- a paid fee record per term
- declared results for every semester, and CGPA recomputed as the credit-weighted
  average over all of them (students.cgpa is the latest)

Attendance is not backfilled: nothing shows a finished term's attendance, and for the
full dataset it would be millions of rows. Idempotent: a dataset that already has a
term before the past one is left alone.
"""
from __future__ import annotations

import csv
import datetime as dt
import random
import statistics
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import academic_data as AD  # noqa: E402
from curriculum_data import CURRICULUM, SUBJECTS, component, subject_area  # noqa: E402
from generate_synthetic_data import AREA_OWNER  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent / "data" / "synthetic"
SEED = 20261005
THEORY = [("IA", "Internal Assessment", 25, 25, 9), ("Mid-Sem", "Mid Semester Exam", 25, 25, 10), ("End-Sem", "End Semester Exam", 100, 50, None)]
LAB = [(atype, title, top, weight, week) for atype, title, top, weight, week, _ in AD.LAB_ASSESSMENT_TEMPLATE]
PROJECT = [("Term-Work", "Term Work Evaluation", 100, 100, 16)]
EXAMS = {"Mid-Sem", "End-Sem", "Mid-Sem-Viva", "Lab-Exam"}  # where a student can be absent


def read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def term_of(batch: int, sem: int) -> str:
    """Batch 2025: semester 1 is 2025-26-ODD, 2 is 2025-26-EVEN, 3 is 2026-27-ODD."""
    y = batch + (sem - 1) // 2
    return f"{y}-{(y + 1) % 100:02d}-{'ODD' if sem % 2 else 'EVEN'}"


def windows(term: str) -> dict[str, dt.date]:
    """The current (odd) or past (even) term's calendar, moved to the term's year."""
    y = int(term[:4])
    odd = term.endswith("ODD")
    base = AD.TERM_WINDOWS[AD.CURRENT_TERM if odd else AD.PAST_TERM]
    shift = y - (int(AD.CURRENT_TERM[:4]) if odd else int(AD.PAST_TERM[:4]))
    return {k: v.replace(year=v.year + shift) for k, v in base.items() if isinstance(v, dt.date)}


def half(x: float, top: float) -> str:
    return str(min(top, max(0.0, int(x * 2 + 0.5) / 2)))


def grade_point(pct: float) -> int:  # generate_synthetic_data._grade_point
    for cut, gp in [(90, 10), (80, 9), (70, 8), (60, 7), (50, 6), (45, 5), (40, 4)]:
        if pct >= cut:
            return gp
    return 0


def fmt(x: float) -> str:
    return str(int(x)) if x == int(x) else str(x)


def backfill(folder: Path) -> None:
    rng = random.Random(SEED)
    o_fields, offerings = read(folder / "course_offerings.csv")
    if any(o["term"] not in (AD.PAST_TERM, AD.CURRENT_TERM) for o in offerings):
        print(f"{folder.name}: history already present")
        return
    _, students = read(folder / "students.csv")
    _, faculty = read(folder / "faculty.csv")
    e_fields, enrollments = read(folder / "enrollments.csv")
    a_fields, assessments = read(folder / "assessments.csv")
    m_fields, marks = read(folder / "marks.csv")
    s_fields, submissions = read(folder / "submissions.csv")
    f_fields, fees = read(folder / "fees.csv")

    # each student's standing: their average share across every mark they already have
    max_of = {a["id"]: float(a["max_marks"]) for a in assessments}
    shares: dict[str, list[float]] = {}
    for m in marks:
        if m["is_absent"] != "True" and m["score"]:
            shares.setdefault(m["student_id"], []).append(float(m["score"]) / max_of[m["assessment_id"]])
    ability = {sid: statistics.mean(v) for sid, v in shares.items()}

    first_fee = {}
    for f in fees:
        first_fee.setdefault(f["student_id"], f)
    pools: dict[str, list[str]] = {}
    for f in faculty:
        pools.setdefault(f["dept_code"], []).append(f["id"])
    first_sem = {}  # student -> earliest semester on record
    sem_of_offering = {o["id"]: int(o["semester"]) for o in offerings}
    for e in enrollments:
        s = sem_of_offering[e["offering_id"]]
        first_sem[e["student_id"]] = min(first_sem.get(e["student_id"], s), s)

    cohorts: dict[tuple[str, int], list[dict[str, str]]] = {}
    for s in students:
        cohorts.setdefault((s["dept_code"], int(s["batch"])), []).append(s)

    next_id = {name: max((int(r["id"]) for r in rows), default=0) + 1
               for name, rows in (("o", offerings), ("e", enrollments), ("a", assessments), ("m", marks), ("s", submissions), ("f", fees))}

    def take(name: str) -> str:
        next_id[name] += 1
        return str(next_id[name] - 1)

    added_terms: set[str] = set()
    for (dept, batch), cohort in sorted(cohorts.items()):
        missing = range(1, min(first_sem.get(s["id"], 1) for s in cohort))
        for sem in missing:
            term = term_of(batch, sem)
            w = windows(term)
            added_terms.add(term)
            divisions = sorted({s["division"] for s in cohort})
            groups = sorted({s["lab_group"] for s in cohort})
            for code in CURRICULUM[dept][sem]:
                name, category, *_ = SUBJECTS[code]
                owner = AREA_OWNER.get(subject_area(code), dept)
                pool = pools.get(owner) or pools[dept]
                if category == "PRO" or code == "MOOC" or subject_area(code) == "INT":
                    sections = [("Self-study" if code == "MOOC" else "Project", "All", "", cohort)]
                elif component(code) == "Lab":
                    sections = [("Lab", "", g, [s for s in cohort if s["lab_group"] == g]) for g in groups]
                else:
                    sections = [("Theory", d, "", [s for s in cohort if s["division"] == d]) for d in divisions]
                for kind, div, group, members in sections:
                    if not members:
                        continue
                    oid = take("o")
                    offerings.append({"id": oid, "subject_code": code, "subject_name": name, "dept_id": cohort[0]["dept_id"],
                                      "dept_code": dept, "term": term, "semester": str(sem), "batch": str(batch),
                                      "faculty_id": rng.choice(pool), "session_type": kind, "division": div,
                                      "lab_group": group, "capacity": len(members)})
                    for s in members:
                        enrollments.append({"id": take("e"), "student_id": s["id"], "offering_id": oid, "subject_code": code,
                                            "term": term, "status": "completed", "enrolled_on": w["teaching_start"].isoformat()})
                    scheme = THEORY if kind == "Theory" else LAB if kind == "Lab" else PROJECT
                    for atype, title, top, weight, week in scheme:
                        spread = zlib.crc32(f"{term}{code}{atype}".encode())
                        if week is None:  # End-Sem: a day in the examination window
                            due = w["exam_start"] + dt.timedelta(days=spread % max(1, (w["exam_end"] - w["exam_start"]).days))
                        else:
                            due = w["teaching_start"] + dt.timedelta(days=(week - 1) * 7 + spread % 5)
                        aid = take("a")
                        assessments.append({"id": aid, "offering_id": oid, "subject_code": code, "term": term, "type": atype,
                                            "title": title, "max_marks": top, "weightage_pct": weight,
                                            "due_date": due.isoformat(), "status": "graded"})
                        for s in members:
                            frac = min(1.0, max(0.0, rng.gauss(ability.get(s["id"], 0.75), 0.09)))
                            absent = atype in EXAMS and rng.random() < 0.015
                            if atype == "IA":
                                r = rng.random()
                                if r < 0.05:
                                    st, at, frac = "missing", "", 0.0
                                elif r < 0.17:
                                    st, at, frac = "late", f"{(due + dt.timedelta(days=rng.randint(1, 3))).isoformat()}T23:00:00", frac * AD.LATE_FACTOR
                                else:
                                    st, at = "submitted", f"{(due - dt.timedelta(days=rng.randint(0, 3))).isoformat()}T21:00:00"
                                submissions.append({"id": take("s"), "assessment_id": aid, "student_id": s["id"], "status": st, "submitted_at": at})
                            marks.append({"id": take("m"), "assessment_id": aid, "student_id": s["id"],
                                          "score": "0.0" if absent else half(top * frac, top), "is_absent": str(absent),
                                          "graded_on": (due + dt.timedelta(days=rng.randint(4, 12))).isoformat()})
            for s in cohort:  # the term's fee, paid like the past term's
                earlier = first_fee.get(s["id"])
                due = dt.date(w["teaching_start"].year, 7, 15) if term.endswith("ODD") else dt.date(w["teaching_start"].year, 1, 15)
                amount = earlier["amount_due"] if earlier else str(AD.TUITION_PER_SEM + AD.OTHER_FEES_PER_SEM)
                fees.append({"id": take("f"), "student_id": s["id"], "roll_no": s["roll_no"], "term": term,
                             "amount_due": amount, "amount_paid": f"{float(amount)}", "status": "paid", "due_date": due.isoformat(),
                             "paid_on": (due - dt.timedelta(days=rng.randint(1, 12))).isoformat()})

    write(folder / "course_offerings.csv", o_fields, offerings)
    write(folder / "enrollments.csv", e_fields, enrollments)
    write(folder / "assessments.csv", a_fields, assessments)
    write(folder / "marks.csv", m_fields, marks)
    write(folder / "submissions.csv", s_fields, submissions)
    write(folder / "fees.csv", f_fields, sorted(fees, key=lambda f: int(f["id"])))
    results(folder, offerings, assessments, marks, students)
    print(f"{folder.name}: added {', '.join(sorted(added_terms)) or 'nothing'}")


def results(folder: Path, offerings, assessments, marks, students) -> None:
    """Declared results for every finished term, SGPA as the generator computes it and
    CGPA as the credit-weighted grade-point average over every semester so far."""
    subjects = {s["subject_code"]: s for s in read(folder / "subjects.csv")[1]}
    a_by_id = {a["id"]: a for a in assessments}
    sem_of = {(o["term"], o["batch"]): int(o["semester"]) for o in offerings}
    batch_of = {s["id"]: s["batch"] for s in students}
    acc: dict[tuple[str, str], dict[str, list[tuple[float, float]]]] = {}
    for m in marks:
        a = a_by_id[m["assessment_id"]]
        if a["term"] == AD.CURRENT_TERM:
            continue
        acc.setdefault((m["student_id"], a["term"]), {}).setdefault(a["subject_code"], []).append(
            (float(a["weightage_pct"]), float(m["score"] or 0) / float(a["max_marks"])))

    r_fields, rows = read(folder / "results_semester.csv")
    by_key = {(r["student_id"], r["term"]): r for r in rows}
    roll_of = {s["id"]: s["roll_no"] for s in students}
    next_id = max((int(r["id"]) for r in rows), default=0) + 1
    running: dict[str, tuple[float, float]] = {}  # student -> (points, credits) so far
    latest: dict[str, str] = {}
    for (sid, term), subjects_taken in sorted(acc.items(), key=lambda kv: (kv[0][0], kv[0][1][:4], kv[0][1].endswith("EVEN"))):
        credits = points = earned = backlogs = 0.0
        for code, parts in subjects_taken.items():
            gp = grade_point(sum(w * f for w, f in parts) / (sum(w for w, _ in parts) or 1) * 100)
            cred = float(subjects[code]["credits"])
            credits += cred
            points += gp * cred
            if gp:
                earned += cred
            elif subjects[code]["category"] in ("PC", "BSC", "ESC"):
                backlogs += 1
        p, c = running.get(sid, (0.0, 0.0))
        running[sid] = (p + points, c + credits)
        sgpa = round(points / credits, 2) if credits else 0.0
        cgpa = round(running[sid][0] / running[sid][1], 2) if running[sid][1] else 0.0
        row = by_key.get((sid, term))
        if row is None:
            row = {"id": str(next_id), "student_id": sid, "roll_no": roll_of[sid], "term": term,
                   "semester": str(sem_of[(term, batch_of[sid])]),
                   "declared_on": windows(term)["result_date"].isoformat()}
            next_id += 1
            rows.append(row)
        row.update({"credits_registered": fmt(credits), "credits_earned": fmt(earned), "sgpa": str(sgpa), "cgpa": str(cgpa),
                    "result_status": "ATKT" if backlogs else "Pass", "backlogs": fmt(backlogs)})
        latest[sid] = str(cgpa)
    write(folder / "results_semester.csv", r_fields, rows)

    st_fields, st_rows = read(folder / "students.csv")
    for s in st_rows:
        if s["id"] in latest:
            s["cgpa"] = latest[s["id"]]
    write(folder / "students.csv", st_fields, st_rows)


if __name__ == "__main__":
    for folder in (ROOT / "sample", ROOT):
        backfill(folder)
