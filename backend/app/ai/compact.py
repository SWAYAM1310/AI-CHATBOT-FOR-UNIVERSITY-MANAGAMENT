"""Tool results -> token-lean Markdown for Call C (plan.md §4).

A tool that returns 400 attendance rows would otherwise blow the whole turn
budget on one call, so results are capped at ROW_CAP and the model is told
plainly how many rows it is not seeing — a truncated table it believes is
complete is worse than no table.
"""
from __future__ import annotations

from typing import Any

ROW_CAP = 40


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(rows: list[dict[str, Any]], cap: int) -> str:
    columns: list[str] = []
    for row in rows[:cap]:
        for key in row:
            if key not in columns:
                columns.append(key)

    head = "| " + " | ".join(columns) + " |"
    rule = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(_cell(row.get(c)) for c in columns) + " |"
        for row in rows[:cap]
    ]
    out = "\n".join([head, rule, *body])

    if len(rows) > cap:
        out += f"\n\n({len(rows) - cap} more rows not shown; {len(rows)} in total.)"
    return out


def compact(result: Any, *, cap: int = ROW_CAP) -> str:
    """Render any tool return value as Markdown a model can read cheaply."""
    if result is None:
        return "(no data)"

    if isinstance(result, dict):
        if isinstance(result.get("rows"), list):
            return compact(result["rows"], cap=cap)
        return "\n".join(f"- **{k}**: {_cell(v)}" for k, v in result.items()) or "(no data)"

    if isinstance(result, list):
        if not result:
            return "(no rows)"
        if all(isinstance(r, dict) for r in result):
            return _table(result, cap)
        return "\n".join(f"- {_cell(r)}" for r in result[:cap])

    return _cell(result)
