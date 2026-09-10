"""Load the synthetic CSV dataset into Postgres.

    python -m app.seed.load_csv --dataset sample --reset      # default
    python -m app.seed.load_csv --dataset full --reset

`--reset` truncates every data table first (RESTART IDENTITY CASCADE). Tables are
loaded in FK-dependency order; identity sequences are bumped past MAX(id) afterwards
so later ORM inserts don't collide.

Only the 24 CSV-backed tables are touched. The AI-layer tables (conversations,
messages, documents, doc_chunks, audit_log) have no CSV and are left empty.

Note: uses chunked executemany. Fine for `sample`; `full` (~2M attendance rows)
works but is slow — swap to psycopg COPY if that path is needed often.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import MetaData, Table, text

from app.config import REPO_ROOT
from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401  - populate Base.metadata

# FK-dependency order. `departments` is loaded first with hod_faculty_id held back
# (it points at faculty, loaded later) and patched at the end.
LOAD_ORDER = [
    "departments",
    "subjects",
    "curriculum",
    "classrooms",
    "faculty",
    "admins",
    "students",
    "users",
    "course_offerings",
    "teaching_assignments",
    "enrollments",
    "timetable_slots",
    "assessments",
    "attendance_sessions",
    "attendance_records",
    "marks",
    "submissions",
    "results_semester",
    "exam_schedule",
    "fees",
    "scholarships",
    "leave_requests",
    "document_requests",
    "announcements",
    "academic_calendar",
]

CHUNK = 5000


def _data_dir(dataset: str) -> Path:
    base = REPO_ROOT / "data" / "synthetic"
    return base if dataset == "full" else base / "sample"


def _coerce(value: str, sa_type) -> object:
    """Turn a raw CSV cell into a Python value matching the column type."""
    if value is None or value == "":
        return None
    tname = sa_type.__class__.__name__
    try:
        if tname == "Boolean":
            return value.strip().lower() in {"true", "t", "1", "yes"}
        if tname in {"Integer", "BigInteger", "SmallInteger"}:
            return int(float(value)) if value not in {"", "nan"} else None
        if tname in {"Numeric", "Float"}:
            return Decimal(value)
        if tname == "Date":
            return dt.date.fromisoformat(value)
        if tname == "Time":
            return dt.time.fromisoformat(value)
        if tname in {"DateTime", "TIMESTAMP"}:
            return dt.datetime.fromisoformat(value)
    except (ValueError, InvalidOperation):
        # keep the raw string; let the DB raise if it is truly bad
        return value
    return value


def _rows(path: Path, table: Table) -> list[dict]:
    cols = {c.name: c.type for c in table.columns}
    out: list[dict] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            out.append({k: _coerce(v, cols[k]) for k, v in raw.items() if k in cols})
    return out


def _insert(conn, table: Table, rows: list[dict]) -> int:
    for i in range(0, len(rows), CHUNK):
        conn.execute(table.insert(), rows[i : i + CHUNK])
    return len(rows)


def load(dataset: str, reset: bool) -> None:
    data_dir = _data_dir(dataset)
    if not data_dir.is_dir():
        raise SystemExit(f"dataset dir not found: {data_dir}")

    md: MetaData = Base.metadata
    tables = {name: md.tables[name] for name in LOAD_ORDER}

    with engine.begin() as conn:
        if reset:
            joined = ", ".join(f'"{n}"' for n in LOAD_ORDER)
            conn.execute(text(f"TRUNCATE {joined} RESTART IDENTITY CASCADE"))
            print(f"truncated {len(LOAD_ORDER)} tables")

        # departments: defer hod_faculty_id until faculty exists
        dept_path = data_dir / "departments.csv"
        dept_rows = _rows(dept_path, tables["departments"])
        hod_patch = [
            (r["id"], r["hod_faculty_id"])
            for r in dept_rows
            if r.get("hod_faculty_id") is not None
        ]
        for r in dept_rows:
            r["hod_faculty_id"] = None
        _insert(conn, tables["departments"], dept_rows)
        print(f"{'departments':<22} {len(dept_rows):>8}")

        for name in LOAD_ORDER[1:]:
            path = data_dir / f"{name}.csv"
            if not path.exists():
                print(f"{name:<22} {'MISSING':>8}  (skipped)")
                continue
            rows = _rows(path, tables[name])
            _insert(conn, tables[name], rows)
            print(f"{name:<22} {len(rows):>8}")

        if hod_patch:
            conn.execute(
                text("UPDATE departments SET hod_faculty_id = :hod WHERE id = :id"),
                [{"id": i, "hod": h} for i, h in hod_patch],
            )
            print(f"patched {len(hod_patch)} department HODs")

        # bump identity sequences past MAX(id)
        for name in LOAD_ORDER:
            if "id" not in tables[name].columns:
                continue
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM \"{name}\"), 1))"
                )
            )
    print("done.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", choices=["sample", "full"], default="sample")
    ap.add_argument("--reset", action="store_true", help="truncate tables first")
    args = ap.parse_args()
    load(args.dataset, args.reset)


if __name__ == "__main__":
    main()
