"""Reference-free quality signals for one answered turn (shown in the trace panel).

A live question has no gold answer, so nothing here is "accuracy". These are
cheap, deterministic checks on how well the answer is tied to what the turn
actually retrieved and computed - no LLM judge, so no extra latency or tokens:

  retrieval          how many passages came back and from which branch (hybrid = both)
  context precision  share of the retrieved passages the answer went on to cite
  citation coverage  of the answer sentences that restate a retrieved passage, the
                     share that carry a citation marker
  numeric grounding  share of the answer's figures found in the tool results, the
                     passages or the question - to the precision the answer states
                     them at ("68%" matches 67.7) - or the gap between two of them
                     ("7 points short" = 75 - 68)
  tool success       share of tool calls that ran without being refused or failing

The eval harness reuses `score_turn` and adds the reference-based scores
(retrieval recall, fact recall) that need the golden set.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

MARKER = re.compile(r"\[\d{1,2}\]")
_LIST_NUMBER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
# an answer figure: not part of a code (24CS201T), a clause ref (§4.2) or a longer number
_ANSWER_NUMBER = re.compile(r"(?<![\w.§])(\d+(?:,\d{3})*(?:\.\d+)?)(%?)(?!\w)")
_SOURCE_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")  # lenient: "4.2" and "24CS201T" both yield figures
_WORD = re.compile(r"[a-z0-9]+")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?!\[\d{1,2}\])")  # a marker after the full stop belongs to the sentence before it

DERIVED_MAX = 30  # only a gap to a threshold is accepted as worked out; with many source figures a big one would match by chance
SMALL_INT_MAX = 10  # "3 courses", "2 weeks": counts the sources rarely state as a figure, so not scored...
MIN_CLAIM_TOKENS = 4
CLAIM_OVERLAP = 0.6  # ...a sentence "restates" a passage when this share of its content words are in it
MAX_LISTED = 5

_STOP = frozenset(
    "the and for are you your that this with from have has had was were not but can may will shall "
    "who what when where which how any all per its it's their they them than then also only such "
    "into onto over under about being been does did done must should would could there here these those".split()
)


@dataclass(frozen=True)
class Scores:
    """None = the check did not apply this turn (nothing to measure), never 0."""

    # retrieval
    passages: int = 0
    top_score: float | None = None  # best RRF score among the passages that carry one
    both_branches: int = 0  # dense and sparse both found it
    dense_only: int = 0
    sparse_only: int = 0
    # context precision
    cited: int = 0
    context_precision: float | None = None
    # citation coverage
    claims: int = 0  # answer sentences that restate a retrieved passage
    claims_cited: int = 0
    citation_coverage: float | None = None
    # numeric grounding
    numbers: int = 0
    numbers_grounded: int = 0
    numeric_grounding: float | None = None
    ungrounded_numbers: list[str] = field(default_factory=list)
    # tools
    tools_run: int = 0
    tools_ok: int = 0
    tool_success: float | None = None


def score_turn(
    *,
    question: str,
    text: str,
    citations: Sequence[dict[str, Any]],
    passages: Sequence[dict[str, Any]],
    tool_runs: Sequence[Any],
) -> Scores:
    """`text` is the final answer with its resolved `[n]` markers; `tool_runs` are orchestrator ToolRuns."""
    fields: dict[str, Any] = {}
    fields |= _retrieval(passages)
    fields |= _context_precision(passages, citations)
    fields |= _citation_coverage(text, passages)
    fields |= _numeric_grounding(question, text, passages, tool_runs)
    fields |= _tools(tool_runs)
    return Scores(**fields)


def _ratio(hit: int, total: int) -> float | None:
    return hit / total if total else None


# --- retrieval ---------------------------------------------------------------

def _retrieval(passages: Sequence[dict[str, Any]]) -> dict[str, Any]:
    scores = [p["score"] for p in passages if isinstance(p.get("score"), (int, float))]
    dense = [p.get("dense_rank") is not None for p in passages]
    sparse = [p.get("sparse_rank") is not None for p in passages]
    return {
        "passages": len(passages),
        "top_score": round(max(scores), 4) if scores else None,
        "both_branches": sum(d and s for d, s in zip(dense, sparse)),
        "dense_only": sum(d and not s for d, s in zip(dense, sparse)),
        "sparse_only": sum(s and not d for d, s in zip(dense, sparse)),
    }


def _context_precision(passages: Sequence[dict[str, Any]], citations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    offered = {str(p.get("chunk_id")) for p in passages}
    cited = {str(c.get("chunk_id")) for c in citations} & offered
    return {"cited": len(cited), "context_precision": _ratio(len(cited), len(offered))}


# --- citation coverage --------------------------------------------------------

def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) >= 3 and w not in _STOP}


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or set(line) <= set("|-: "):
            continue
        out += [s for s in _SENTENCE_BREAK.split(line) if s.strip()]
    return out


def _citation_coverage(text: str, passages: Sequence[dict[str, Any]]) -> dict[str, Any]:
    bodies = [_tokens(f"{p.get('excerpt') or ''} {p.get('parent') or ''}") for p in passages]
    claims = cited = 0
    for sentence in _sentences(text) if bodies else []:
        words = _tokens(MARKER.sub("", sentence))
        if len(words) < MIN_CLAIM_TOKENS:
            continue
        if any(len(words & body) / len(words) >= CLAIM_OVERLAP for body in bodies):
            claims += 1
            cited += bool(MARKER.search(sentence))
    return {"claims": claims, "claims_cited": cited, "citation_coverage": _ratio(cited, claims)}


# --- numeric grounding --------------------------------------------------------

def _source_figures(question: str, passages: Sequence[dict[str, Any]], tool_runs: Sequence[Any]) -> list[float]:
    blobs = [question]
    for p in passages:
        blobs += [str(p.get("excerpt") or ""), str(p.get("parent") or "")]
    blobs += [getattr(r, "markdown", "") for r in tool_runs if getattr(r, "ok", False)]
    return sorted({float(m.replace(",", "")) for blob in blobs for m in _SOURCE_NUMBER.findall(blob)})


def _near(sorted_values: list[float], x: float, tol: float) -> bool:
    i = bisect_left(sorted_values, x - tol)
    return i < len(sorted_values) and sorted_values[i] <= x + tol


def _numeric_grounding(
    question: str, text: str, passages: Sequence[dict[str, Any]], tool_runs: Sequence[Any]
) -> dict[str, Any]:
    body = _LIST_NUMBER.sub("", MARKER.sub("", text))
    sources = _source_figures(question, passages, tool_runs)
    checked = grounded = 0
    missing: list[str] = []
    for m in _ANSWER_NUMBER.finditer(body):
        raw, percent = m.group(1), m.group(2)
        value = float(raw.replace(",", ""))
        if not percent and "." not in raw and value <= SMALL_INT_MAX:
            continue
        checked += 1
        # "68%" is a fair reading of 67.7: a figure is matched to the precision it was stated at
        tol = 0.5 * 10 ** -(len(raw.split(".")[1]) if "." in raw else 0) + 1e-9
        stated = _near(sources, value, tol)
        # or one the answer worked out: the gap between two stated figures ("7 points short" = 75 - 68)
        worked = value <= DERIVED_MAX and any(_near(sources, s - value, tol) for s in sources)
        if stated or worked:
            grounded += 1
        elif len(missing) < MAX_LISTED and raw + percent not in missing:
            missing.append(raw + percent)
    return {
        "numbers": checked,
        "numbers_grounded": grounded,
        "numeric_grounding": _ratio(grounded, checked),
        "ungrounded_numbers": missing,
    }


# --- reference-based (the eval harness: needs the golden set's expectations) ---------

KS = (1, 3, 5)


def source_matches(passage: dict[str, Any], target: dict[str, str]) -> bool:
    """`target` = {doc, section}: doc is a substring of the passage's document title, section a
    substring of its section label (empty = any section). A clause ref "§4.2" also matches "§4.2.1"."""
    return target["doc"] in (passage.get("document") or "") and target.get("section", "") in (passage.get("section") or "")


def retrieval_metrics(
    passages: Sequence[dict[str, Any]], citations: Sequence[dict[str, Any]], targets: Sequence[dict[str, str]]
) -> dict[str, Any]:
    """How well the retriever, and then the answer's citations, hit an acceptable source (any-of `targets`).

    hit@k        an acceptable passage is among the first k offered to the model (recall@k over a
                 one-answer-suffices question)
    rank         1-based position of the first acceptable passage, None if absent (MRR = mean 1/rank)
    precision    share of the offered passages that are acceptable
    cite_precision  share of the passages the answer cited that are acceptable (None if it cited nothing)
    """
    good = [any(source_matches(p, t) for t in targets) for p in passages]
    rank = next((i + 1 for i, g in enumerate(good) if g), None)
    by_id = {str(p.get("chunk_id")): g for p, g in zip(passages, good)}
    cited = [by_id.get(str(c.get("chunk_id")), False) for c in citations]
    return {
        **{f"hit@{k}": any(good[:k]) for k in KS},
        "rank": rank,
        "precision": _ratio(sum(good), len(good)),
        "cite_precision": _ratio(sum(cited), len(cited)),
    }


def _norm(text: str) -> str:
    text = MARKER.sub("", text).lower().replace(" ", " ")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)  # 40,000 -> 40000
    text = re.sub(r"[*_`]", "", text)
    text = re.sub(r"[‐-―]", "-", text)
    return re.sub(r"\s+", " ", text)


def fact_recall(text: str, facts: Sequence[str | Sequence[str]]) -> tuple[float | None, list[str]]:
    """Share of the expected facts the answer states, and the ones it missed.

    A fact is a string, or a list of acceptable phrasings (any one counts). Matching is a
    case-insensitive substring test after dropping markdown, citation markers and thousands commas,
    so it can miss a valid paraphrase: read a low score as "look at this answer", not "wrong".
    """
    body = _norm(text)
    missing = []
    for fact in facts:
        options = [fact] if isinstance(fact, str) else list(fact)
        if not any(_norm(o) in body for o in options):
            missing.append(options[0])
    return _ratio(len(facts) - len(missing), len(facts)), missing


# --- tools --------------------------------------------------------------------

def _tools(tool_runs: Sequence[Any]) -> dict[str, Any]:
    ok = sum(bool(getattr(r, "ok", False)) for r in tool_runs)
    return {"tools_run": len(tool_runs), "tools_ok": ok, "tool_success": _ratio(ok, len(tool_runs))}
