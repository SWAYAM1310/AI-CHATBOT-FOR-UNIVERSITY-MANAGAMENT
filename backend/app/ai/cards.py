"""Typed cards for the frontend, derived from tool results (plan.md §9).

Call C writes the prose; a card carries the same data in a shape the UI can
draw — attendance bars against the 75% line, a week grid, a sortable table.
The mapping is by tool name and is deliberately small: a card only exists
where a picture says more than the sentence.

Cards are stored with the turn's tool runs so a reopened transcript shows
them again. Rows are capped: a card is a glance, not an export.
"""
from __future__ import annotations

from typing import Any

ROW_CAP = 100
ATTENDANCE_THRESHOLD = 75  # AR/IV/2026 §4.2

TIMETABLE_TOOLS = {"get_my_timetable", "get_my_teaching_schedule"}
STUDENT_TABLE_TOOLS = {
    "list_students",
    "list_course_students",
    "list_students_below_attendance",
    "identify_at_risk_students",
    "list_missing_submissions",
}


def cards_for(name: str, result: Any, *, ok: bool, error: str | None) -> list[dict[str, Any]]:
    """Cards for one executed tool; [] when nothing about it deserves a picture."""
    if error == "denied":
        return [{"type": "denied", "tool": name}]
    if not ok:
        return []
    rows = _rows(result)
    if name == "get_my_attendance" and rows:
        return [
            {
                "type": "attendance",
                "threshold": ATTENDANCE_THRESHOLD,
                "rows": [
                    {
                        "course": r.get("course"),
                        "name": r.get("name"),
                        "attended": r.get("attended"),
                        "total": r.get("total"),
                        "percent": r.get("percent"),
                    }
                    for r in rows[:ROW_CAP]
                ],
            }
        ]
    if name == "get_my_marks" and rows:
        return [
            {
                "type": "marks",
                "rows": [
                    {
                        "course": r.get("course"),
                        "assessment": r.get("title") or r.get("assessment_type"),
                        "score": r.get("score"),
                        "max_marks": r.get("max_marks"),
                        "absent": bool(r.get("is_absent")),
                    }
                    for r in rows[:ROW_CAP]
                ],
            }
        ]
    if name in TIMETABLE_TOOLS and rows:
        return [
            {
                "type": "timetable",
                "rows": [
                    {
                        "day": r.get("day_of_week"),
                        "start": r.get("start_time"),
                        "end": r.get("end_time"),
                        "course": r.get("course"),
                        "name": r.get("name"),
                        "kind": r.get("session_type"),
                        "room": r.get("room"),
                    }
                    for r in rows[:ROW_CAP]
                ],
            }
        ]
    if name in STUDENT_TABLE_TOOLS and rows:
        columns = list(rows[0].keys())
        return [
            {
                "type": "student_table",
                "title": name.replace("_", " "),
                "columns": columns,
                "rows": [[r.get(c) for c in columns] for r in rows[:ROW_CAP]],
                "total": len(rows),
            }
        ]
    return []


def _rows(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict) and isinstance(result.get("rows"), list):
        result = result["rows"]
    if isinstance(result, list) and all(isinstance(r, dict) for r in result):
        return result
    return []


__all__ = ["cards_for", "ROW_CAP", "ATTENDANCE_THRESHOLD"]
