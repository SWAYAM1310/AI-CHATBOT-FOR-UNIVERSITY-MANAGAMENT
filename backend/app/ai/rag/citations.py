"""Turn Call C's `[[cite:<chunk_id>]]` markers into numbered citations.

The synthesis prompt hands the model passages keyed by chunk id and asks it to
end every policy claim with `[[cite:<id>]]`. This module resolves those markers
against the passages that were actually offered:

- numbered in order of first appearance, so "[1]" is the first source cited
- a marker the model repeats reuses its number
- a marker for an id that was never offered is removed (the model may not
  invent a source), and the claim is left standing un-cited for the reader to
  judge

`resolve()` returns the rewritten text plus the citation objects the API and
the frontend's citation chips consume.
"""
from __future__ import annotations

import re
from typing import Any

# [[cite:id]] as instructed; also 【cite:id】 and [cite:id], which gpt-oss produces in the wild
_CITE = re.compile(r"\s*(?:\[\[|【|\[)\s*cite:\s*([^\]】]+?)\s*(?:\]\]|】|\])")
SNIPPET_CHARS = 300


def resolve(text: str, passages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """(text with `[n]` markers, citations in first-cited order)."""
    by_id = {str(p.get("chunk_id")): p for p in passages}
    numbers: dict[str, int] = {}
    citations: list[dict[str, Any]] = []

    def replace(m: re.Match[str]) -> str:
        key = m.group(1)
        passage = by_id.get(key)
        if passage is None:
            return ""
        if key not in numbers:
            numbers[key] = len(numbers) + 1
            citations.append(_citation(numbers[key], passage))
        return f" [{numbers[key]}]"

    return _CITE.sub(replace, text).strip(), citations


def _citation(n: int, p: dict[str, Any]) -> dict[str, Any]:
    body = p.get("excerpt") or p.get("content") or ""
    return {
        "n": n,
        "chunk_id": p.get("chunk_id"),
        "document": p.get("document"),
        "section": p.get("section"),
        "page": p.get("page"),
        "snippet": body[:SNIPPET_CHARS],
    }
