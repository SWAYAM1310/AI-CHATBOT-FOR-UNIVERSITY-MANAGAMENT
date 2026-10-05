"""Bring the generated CSVs in line with two rules the generator now follows.

    python scripts/fix_dataset.py            # data/synthetic and data/synthetic/sample

1. Marks are whole or half (7, 7.5), never 7.3: every score is rounded to the nearest
   0.5 (half up) and kept inside 0..max_marks.
2. An exam is due the day the exam schedule sits it: Internal-1/2 and End-Sem
   assessments take that subject's exam_schedule date, and a mark graded before
   its exam moves to 2-8 days after it.

Idempotent, so it is safe to run again. The dataset is patched in place rather than
regenerated, because a regeneration used to reshuffle every exam date (see
generate_synthetic_data.exam_date).
"""
from __future__ import annotations

import csv
import datetime as dt
import zlib
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data" / "synthetic"
EXAMS = {"Internal-1", "Internal-2", "End-Sem"}


def read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def half_step(score: Decimal, top: Decimal | None) -> Decimal:
    rounded = (score * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2
    rounded = max(Decimal(0), rounded if top is None else min(top, rounded))
    return rounded.quantize(Decimal("0.1")) if rounded % 1 else rounded.quantize(Decimal("1"))


def fix(folder: Path) -> None:
    offerings = {r["id"]: r for r in read(folder / "course_offerings.csv")[1]}
    exam_day: dict[tuple[str, ...], str] = {}
    for x in read(folder / "exam_schedule.csv")[1]:
        exam_day[(x["term"], x["exam_type"], x["dept_code"], x["semester"], x["subject_code"])] = x["exam_date"]
        exam_day.setdefault((x["term"], x["exam_type"], x["subject_code"]), x["exam_date"])

    a_fields, assessments = read(folder / "assessments.csv")
    moved = 0
    for a in assessments:
        if a["type"] not in EXAMS:
            continue
        o = offerings.get(a["offering_id"], {})
        day = exam_day.get((a["term"], a["type"], o.get("dept_code", ""), o.get("semester", ""), a["subject_code"])) or exam_day.get(
            (a["term"], a["type"], a["subject_code"])
        )
        if day and a["due_date"] != day:
            a["due_date"] = day
            moved += 1
    write(folder / "assessments.csv", a_fields, assessments)
    by_id = {a["id"]: a for a in assessments}

    m_fields, marks = read(folder / "marks.csv")
    rounded = regraded = 0
    for m in marks:
        a = by_id[m["assessment_id"]]
        if m["score"]:
            top = Decimal(a["max_marks"]) if a["max_marks"] else None
            new = half_step(Decimal(m["score"]), top)
            if new != Decimal(m["score"]):  # "8.0" stays as written
                m["score"] = str(new)
                rounded += 1
        if a["type"] in EXAMS and m["graded_on"] and m["graded_on"] < a["due_date"]:
            lag = 2 + zlib.crc32(m["id"].encode()) % 7  # 2..8 days, the same on every run
            m["graded_on"] = (dt.date.fromisoformat(a["due_date"]) + dt.timedelta(days=lag)).isoformat()
            regraded += 1
    write(folder / "marks.csv", m_fields, marks)
    print(f"{folder.name:<10} exam due dates moved {moved:>6}  scores rounded {rounded:>7}  graded_on moved {regraded:>6}")


if __name__ == "__main__":
    for folder in (ROOT, ROOT / "sample"):
        fix(folder)
