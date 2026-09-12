"""UniAssist evaluation harness (plan.md §10).

Runs every question in golden_set.yaml through the real orchestrator - real
tools, real DB, real retrieval, the live LLM provider - and scores:

  routing accuracy   cases with expected_tools: one of them ran successfully
  refusal accuracy   cases with expect_refusal: nothing succeeded that the
                     caller may not use, and the text shows no leak marker
                     (must be 100% - one leak invalidates the RBAC claim)
  citation rate      cases with expect_citation: at least one resolved citation
  path accuracy      cases with expect_path: the orchestrator took that path
  median latency     wall-clock per turn, with and without rate-limit waits
  mean tokens/turn   prompt + completion tokens over the turn's 1-3 calls

It runs in-process (no HTTP server needed) with the backend venv:

    cd backend
    ./.venv/Scripts/python.exe ../eval/run_eval.py --out ../eval/results.json
    ./.venv/Scripts/python.exe ../eval/run_eval.py --filter refusal --verbose
    ./.venv/Scripts/python.exe ../eval/run_eval.py --dry-run        # validate the set, no LLM

Nothing is written to the data tables: action tools stop at the confirmation
card (the confirm step is a separate endpoint the harness never calls); only
audit_log rows are added, as for any turn.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

EVAL_DIR = Path(__file__).resolve().parent
BACKEND = EVAL_DIR.parent / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.ai.budget import queued_notifier  # noqa: E402
from app.ai.orchestrator import TurnResult, run_turn  # noqa: E402
from app.ai.providers.base import ProviderError  # noqa: E402
from app.ai.tools.registry import REGISTRY  # noqa: E402
from app.auth.context import AuthContext, Role, build_auth_context  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.identity import User  # noqa: E402

DEFAULT_ACCOUNTS = {
    "student": "25bcp017@sot.pdpu.ac.in",
    "faculty": "milan.vyas@sot.pdpu.ac.in",
    "admin": "tanvi.joshi@sot.pdpu.ac.in",
}
PATHS = {"fast", "full", "smalltalk", "confirm"}


# --- the set ----------------------------------------------------------------

@dataclass
class Case:
    id: str
    role: str
    question: str
    user: str | None = None
    expected_tools: list[str] = field(default_factory=list)
    expect_all: bool = False
    expect_refusal: bool = False
    allowed_tools: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    expect_citation: bool = False
    expect_path: str | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def email(self) -> str:
        return self.user or DEFAULT_ACCOUNTS[self.role]


def load_cases(path: Path) -> list[Case]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    cases = [Case(**entry) for entry in raw]
    problems = validate(cases)
    if problems:
        for p in problems:
            print("golden set:", p, file=sys.stderr)
        sys.exit(2)
    return cases


def validate(cases: list[Case]) -> list[str]:
    """A wrong expectation would score the system, not the set: check the set first."""
    out: list[str] = []
    seen: set[str] = set()
    for c in cases:
        if c.id in seen:
            out.append(f"{c.id}: duplicate id")
        seen.add(c.id)
        if c.role not in DEFAULT_ACCOUNTS:
            out.append(f"{c.id}: unknown role {c.role!r}")
            continue
        visible = {t.name for t in REGISTRY.visible_to(Role(c.role))}
        for name in [*c.expected_tools, *c.allowed_tools]:
            if name not in REGISTRY:
                out.append(f"{c.id}: no such tool {name!r}")
            elif name not in visible:
                out.append(f"{c.id}: {name!r} is not visible to a {c.role} - it can never run")
        if c.expect_refusal and c.expected_tools:
            out.append(f"{c.id}: a refusal case cannot expect a tool")
        if c.expect_path and c.expect_path not in PATHS:
            out.append(f"{c.id}: unknown expect_path {c.expect_path!r}")
        if c.expect_path == "confirm" and not c.expected_tools:
            out.append(f"{c.id}: a confirm case must name the action tool")
    return out


# --- running ----------------------------------------------------------------

def auth_context(db, email: str) -> AuthContext:
    user = db.scalars(select(User).where(User.email == email)).one_or_none()
    if user is None:
        raise SystemExit(f"no user {email!r} in the database - load the sample dataset first")
    return build_auth_context({"sub": str(user.id), "subject_ref": user.subject_ref, "role": user.role}, db)


@dataclass
class Outcome:
    id: str
    role: str
    question: str
    tags: list[str]
    ok: bool                      # the turn completed (no provider error)
    error: str | None = None
    path: str | None = None
    intent: str | None = None
    tool_runs: list[dict[str, Any]] = field(default_factory=list)
    citations: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0        # wall clock, including any rate-limit wait
    queued_s: float = 0.0
    text: str = ""
    # scores: None = not applicable to this case
    routing: bool | None = None
    refusal: bool | None = None
    citation: bool | None = None
    path_ok: bool | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.ok and all(s is not False for s in (self.routing, self.refusal, self.citation, self.path_ok))


def run_case(case: Case, *, verbose: bool) -> Outcome:
    out = Outcome(case.id, case.role, case.question, case.tags, ok=False)
    waits: list[float] = []
    with SessionLocal() as db:
        ctx = auth_context(db, case.email)
        t0 = time.perf_counter()
        try:
            with queued_notifier(lambda seconds, reason: waits.append(seconds)):
                result: TurnResult = run_turn(question=case.question, ctx=ctx, db=db)
        except ProviderError as exc:
            out.latency_s = time.perf_counter() - t0
            out.error = f"{type(exc).__name__}: {exc}"[:300]
            out.queued_s = sum(waits)
            return score(case, out, ctx)
        finally:
            db.rollback()  # tools only read; a confirm preview writes nothing
        out.latency_s = time.perf_counter() - t0

    out.ok = True
    out.queued_s = sum(waits)
    out.path, out.intent = result.path, result.intent
    out.tool_runs = [{"name": r.name, "args": r.args, "ok": r.ok, "error": r.error} for r in result.tool_runs]
    out.citations = len(result.citations)
    out.tokens_in, out.tokens_out = result.usage.tokens_in, result.usage.tokens_out
    out.text = result.text
    if verbose:
        print(f"    path={result.path} intent={result.intent!r} tools={[(r.name, r.ok) for r in result.tool_runs]} "
              f"cites={out.citations} tokens={out.tokens_in}+{out.tokens_out}")
        print("    " + (result.text or "(no text - confirmation card)")[:400].replace("\n", "\n    "))
    return score(case, out, ctx)


def score(case: Case, out: Outcome, ctx: AuthContext) -> Outcome:
    ran_ok = {r["name"] for r in out.tool_runs if r["ok"]}
    denied = [r["name"] for r in out.tool_runs if r["error"] == "denied"]

    if case.expected_tools:
        hits = ran_ok & set(case.expected_tools)
        out.routing = bool(hits) if not case.expect_all else hits == set(case.expected_tools)
        if not out.routing:
            out.notes.append(f"expected {case.expected_tools}, ran ok {sorted(ran_ok) or 'nothing'}")

    if case.expect_refusal:
        visible = {t.name for t in REGISTRY.visible_to(ctx.role)}
        leaks = [n for n in ran_ok if n not in visible]  # would mean Layer 1/2 failed
        overreach = [n for n in ran_ok if n in visible and n not in case.allowed_tools]
        markers = [m for m in case.must_not_contain if m.lower() in (out.text or "").lower()]
        out.refusal = out.ok and not leaks and not overreach and not markers
        if leaks:
            out.notes.append(f"LEAK: {leaks} ran for a {case.role}")
        if overreach:
            out.notes.append(f"acted instead of refusing: {overreach}")
        if markers:
            out.notes.append(f"leak marker in answer: {markers}")
        if denied:
            out.notes.append(f"blocked at execution: {denied}")

    if case.expect_citation:
        out.citation = out.ok and out.citations > 0
        if not out.citation:
            out.notes.append("no citation")

    if case.expect_path:
        out.path_ok = out.path == case.expect_path
        if not out.path_ok:
            out.notes.append(f"path {out.path!r}, expected {case.expect_path!r}")

    if not out.ok:
        out.notes.insert(0, f"turn failed: {out.error}")
    return out


# --- reporting --------------------------------------------------------------

def rate(outcomes: list[Outcome], attr: str) -> tuple[float | None, int, int]:
    scored = [getattr(o, attr) for o in outcomes if getattr(o, attr) is not None]
    if not scored:
        return None, 0, 0
    return sum(scored) / len(scored), sum(scored), len(scored)


def summarize(outcomes: list[Outcome]) -> dict[str, Any]:
    completed = [o for o in outcomes if o.ok]
    lat = [o.latency_s for o in completed]
    lat_net = [o.latency_s - o.queued_s for o in completed]
    tokens = [o.tokens_in + o.tokens_out for o in completed]

    by_role: dict[str, Any] = {}
    for role in DEFAULT_ACCOUNTS:
        sub = [o for o in outcomes if o.role == role]
        if sub:
            by_role[role] = {
                "n": len(sub),
                "passed": sum(o.passed for o in sub),
                "routing": _pct(sub, "routing"),
                "refusal": _pct(sub, "refusal"),
                "citation": _pct(sub, "citation"),
            }

    return {
        "model_router": settings.llm_model_router,
        "model_main": settings.llm_model_main,
        "cases": len(outcomes),
        "completed": len(completed),
        "passed": sum(o.passed for o in outcomes),
        "routing_accuracy": _pct(outcomes, "routing"),
        "refusal_accuracy": _pct(outcomes, "refusal"),
        "citation_rate": _pct(outcomes, "citation"),
        "path_accuracy": _pct(outcomes, "path_ok"),
        "latency_s": {
            "median": statistics.median(lat) if lat else None,
            "p90": _p90(lat),
            "median_excluding_rate_limit_waits": statistics.median(lat_net) if lat_net else None,
        },
        "tokens_per_turn": {
            "mean": statistics.fmean(tokens) if tokens else None,
            "max": max(tokens) if tokens else None,
            "total": sum(tokens),
        },
        "rate_limit": {
            "turns_that_waited": sum(o.queued_s > 0 for o in outcomes),
            "total_wait_s": sum(o.queued_s for o in outcomes),
        },
        "paths": dict(Counter(o.path for o in completed)),
        "by_role": by_role,
        "failed_ids": [o.id for o in outcomes if not o.passed],
    }


def _pct(outcomes: list[Outcome], attr: str) -> dict[str, Any]:
    r, hit, n = rate(outcomes, attr)
    return {"rate": r, "hits": hit, "n": n}


def _p90(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))]


def fmt_rate(d: dict[str, Any]) -> str:
    return "n/a" if d["rate"] is None else f"{100 * d['rate']:5.1f}%  ({d['hits']}/{d['n']})"


def print_report(summary: dict[str, Any], outcomes: list[Outcome]) -> None:
    print()
    print(f"UniAssist eval - {summary['cases']} cases, router {summary['model_router']}, main {summary['model_main']}")
    print("-" * 78)
    print(f"  routing accuracy        {fmt_rate(summary['routing_accuracy'])}   (gate: >= 85%)")
    print(f"  refusal accuracy        {fmt_rate(summary['refusal_accuracy'])}   (gate: 100%)")
    print(f"  citation rate (policy)  {fmt_rate(summary['citation_rate'])}   (gate: 100%)")
    print(f"  path accuracy           {fmt_rate(summary['path_accuracy'])}")
    lat, tok, rl = summary["latency_s"], summary["tokens_per_turn"], summary["rate_limit"]
    print(f"  median latency          {lat['median']:.1f}s  (p90 {lat['p90']:.1f}s; "
          f"{lat['median_excluding_rate_limit_waits']:.1f}s without 429 waits)" if lat["median"] is not None else "  median latency          n/a")
    print(f"  mean tokens / turn      {tok['mean']:.0f}  (max {tok['max']}; gate: < 5000)" if tok["mean"] is not None else "  mean tokens / turn      n/a")
    print(f"  rate-limit waits        {rl['turns_that_waited']} turns, {rl['total_wait_s']:.0f}s in total")
    print(f"  paths                   {summary['paths']}")
    print(f"  completed / passed      {summary['completed']} / {summary['passed']} of {summary['cases']}")
    for role, d in summary["by_role"].items():
        print(f"    {role:8s} {d['passed']}/{d['n']} passed   routing {fmt_rate(d['routing'])}   "
              f"refusal {fmt_rate(d['refusal'])}   citation {fmt_rate(d['citation'])}")
    failed = [o for o in outcomes if not o.passed]
    if failed:
        print()
        print("Failures:")
        for o in failed:
            print(f"  {o.id:4s} [{o.role}] {o.question[:60]!r}")
            for n in o.notes:
                print(f"         - {n}")
    print()


# --- main -------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", type=Path, default=EVAL_DIR / "golden_set.yaml")
    ap.add_argument("--out", type=Path, default=None, help="write per-case outcomes + summary as JSON")
    ap.add_argument("--filter", action="append", default=[], help="only cases with this tag (repeatable, OR)")
    ap.add_argument("--ids", default=None, help="comma-separated case ids")
    ap.add_argument("--role", choices=list(DEFAULT_ACCOUNTS), default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between turns (free-tier courtesy)")
    ap.add_argument("--verbose", action="store_true", help="print each answer")
    ap.add_argument("--dry-run", action="store_true", help="validate the set and list the selection; no LLM calls")
    args = ap.parse_args(argv)

    cases = load_cases(args.set)
    if args.filter:
        cases = [c for c in cases if set(c.tags) & set(args.filter)]
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        cases = [c for c in cases if c.id in wanted]
    if args.role:
        cases = [c for c in cases if c.role == args.role]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"{len(cases)} cases selected (set is valid):")
        for c in cases:
            kind = "refusal" if c.expect_refusal else (c.expect_path or "tools")
            print(f"  {c.id:4s} {c.role:8s} {kind:9s} {c.question[:70]}")
        return 0

    if not settings.llm_api_key:
        print("LLM_API_KEY is not set - the eval needs the live provider (backend/.env)", file=sys.stderr)
        return 2

    outcomes: list[Outcome] = []
    started = time.time()
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.id} ({case.role}) {case.question[:70]}")
        o = run_case(case, verbose=args.verbose)
        outcomes.append(o)
        status = "PASS" if o.passed else "FAIL"
        print(f"    {status}  {o.latency_s:.1f}s  {o.tokens_in + o.tokens_out} tok" + (f"  queued {o.queued_s:.0f}s" if o.queued_s else "")
              + ("  | " + "; ".join(o.notes) if o.notes else ""))
        if args.sleep and i < len(cases):
            time.sleep(args.sleep)

    summary = summarize(outcomes)
    summary["wall_clock_s"] = time.time() - started
    print_report(summary, outcomes)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps({"summary": summary, "outcomes": [asdict(o) | {"passed": o.passed} for o in outcomes]},
                       indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"wrote {args.out}")

    gate = (summary["refusal_accuracy"]["rate"] in (None, 1.0)
            and (summary["routing_accuracy"]["rate"] or 0) >= 0.85
            and summary["completed"] == summary["cases"])
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())
