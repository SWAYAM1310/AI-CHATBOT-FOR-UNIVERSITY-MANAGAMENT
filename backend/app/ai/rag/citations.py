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


class IncrementalCitations:
    """`resolve()`, but fed a growing string one stream chunk at a time.

    Mirrors its numbering (first-appearance order, an id never offered is
    dropped) while text is still arriving, by holding back any tail that could
    be the start of a marker that hasn't closed yet — `[[cite:12` at the end of
    a chunk waits for the rest rather than being shown raw or eaten early. The
    stream's final `done` event still runs the complete text through
    `resolve()`, which stays the source of truth; this only has to look right
    while the answer is still typing.
    """

    def __init__(self, passages: list[dict[str, Any]]) -> None:
        self._by_id = {str(p.get("chunk_id")): p for p in passages}
        self._numbers: dict[str, int] = {}
        self._citations: list[dict[str, Any]] = []
        self._buf = ""

    def feed(self, chunk: str) -> str:
        """Text from `chunk` (plus any held-back tail) that is now safe to show."""
        self._buf += chunk
        cut = _safe_cut(self._buf)
        emit, self._buf = self._buf[:cut], self._buf[cut:]
        return _CITE.sub(self._replace, emit)

    def flush(self) -> str:
        """Whatever is still held back, resolved best-effort at stream end."""
        emit, self._buf = self._buf, ""
        return _CITE.sub(self._replace, emit)

    def _replace(self, m: re.Match[str]) -> str:
        key = m.group(1)
        passage = self._by_id.get(key)
        if passage is None:
            return ""
        if key not in self._numbers:
            self._numbers[key] = len(self._numbers) + 1
            self._citations.append(_citation(self._numbers[key], passage))
        return f" [{self._numbers[key]}]"

    @property
    def citations(self) -> list[dict[str, Any]]:
        return list(self._citations)


_OPEN_CLOSE = re.compile(r"\]\]|】|\]")


def _safe_cut(buf: str) -> int:
    """Index up to which `buf` is safe to emit: not mid-marker."""
    last_open = max(buf.rfind("[["), buf.rfind("【"), buf.rfind("["))
    if last_open == -1:
        return len(buf)
    if _OPEN_CLOSE.search(buf[last_open:]):
        return len(buf)  # the open bracket already has a matching close: nothing pending
    return last_open  # hold back from the open bracket on — it may still be growing
