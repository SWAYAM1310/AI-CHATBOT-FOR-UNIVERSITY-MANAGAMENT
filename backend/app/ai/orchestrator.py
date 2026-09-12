"""The three-call turn: route -> plan -> execute -> synthesize (plan.md §3).

    Call A  route      gpt-oss-20b   role-filtered tool INDEX (name + one line)
    Call B  plan       gpt-oss-120b  FULL schemas for only the 2-4 candidates
    execute            RBAC layers 2 and 3 in the registry, results compacted
    Call C  synthesize gpt-oss-120b  NO tool schemas — cannot call tools

Splitting the turn is what keeps each call inside the free-tier TPM ceiling, and
it makes routing more accurate by shrinking the decision space. The fast path
(smalltalk, or one unambiguous no-argument tool) skips Call B entirely, which is
where most turns land.

Everything security-relevant happens below the model: the registry re-checks the
role (Layer 2) and strips identity arguments (Layer 3) on every single call, so
a model that ignores its prompt still cannot reach another student's data.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.ai.budget import get_budgeted_provider
from app.ai.cards import cards_for
from app.ai.compact import compact
from app.ai.prompts.system import (
    plan_system,
    route_system,
    synthesize_system,
    synthesize_user,
)
from app.ai.providers import LLMProvider, Msg, Usage, parse_json_object
from app.ai.rag.citations import resolve as resolve_citations
from app.ai.tools.registry import REGISTRY, ToolDenied
from app.ai.tools.schema import model_params, schemas_for
from app.auth.context import AuthContext, Role
from app.config import settings
from app.models import Admin, Faculty, Student

log = logging.getLogger(__name__)

HISTORY_TURNS = 3  # plan.md §4: bounded growth
MAX_CANDIDATES = 4  # plan.md §3: Call A narrows to 2-4
MAX_TOOL_CALLS = 3  # a runaway plan must not fan out into the DB
RAG_TOOL = "search_university_policies"
PASSAGE_TOOLS = {RAG_TOOL, "search_curriculum"}  # retrieval tools: their hits become citable passages
# Personal-record tools whose numbers need a regulation next to them. When one of
# these ran, the matching rule is retrieved even if the router said needs_rag=false:
# the small router model does not always spot the policy dimension, and the
# comparison ("7 points short") is the point of the product.
POLICY_CONTEXT = {
    "get_my_attendance": "minimum attendance percentage required for end-semester examination eligibility and condonation",
    "get_course_attendance_summary": "minimum attendance percentage required for end-semester examination eligibility",
    "list_students_below_attendance": "minimum attendance percentage required for end-semester examination eligibility and condonation",
    "get_my_fees": "semester fee due date, late fee per week and overdue consequences",
    "get_my_marks": "minimum marks for passing and assessment weightage",
    "get_my_results": "grading, grade points and backlogs",
    "get_my_scholarships": "scholarship eligibility, application window and disbursement",
    "get_my_leave_requests": "student leave limits and approval",
}
RAG_TOP_K = 5  # one clause per chunk (~65 tokens): all five retrieved passages fit comfortably


@dataclass(frozen=True)
class ToolRun:
    """One executed tool call, already compacted for the synthesis prompt."""

    name: str
    args: dict[str, Any]
    markdown: str
    ok: bool = True
    error: str | None = None
    preview: dict[str, Any] | None = None  # set by a two-phase-confirm action tool
    passages: list[dict[str, Any]] | None = None  # set by a retrieval tool (PASSAGE_TOOLS)
    cards: list[dict[str, Any]] = field(default_factory=list)  # typed cards for the UI (app.ai.cards)

    def as_prompt_block(self) -> dict[str, Any]:
        return {"name": self.name, "args": self.args, "markdown": self.markdown}


@dataclass(frozen=True)
class TurnResult:
    text: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    cards: list[dict[str, Any]] = field(default_factory=list)
    tool_runs: list[ToolRun] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    intent: str = ""
    path: str = "full"  # full | fast | smalltalk | confirm | error


def run_turn(
    *,
    question: str,
    ctx: AuthContext,
    db: Session,
    history: Sequence[Msg] = (),
    provider: LLMProvider | None = None,
) -> TurnResult:
    """Answer one user question.

    A failing tool degrades to a result row Call C can explain. Provider errors
    propagate on purpose: rate limiting is the budgeted provider's job below
    this layer, and a 429 that outlives its retries has to reach the caller.
    """
    provider = provider or get_budgeted_provider()
    caller = _caller_name(db, ctx)
    recent = _trim(history)
    usage = Usage()

    # --- Call A: route ------------------------------------------------------
    index = REGISTRY.index_for(ctx.role)
    route = provider.chat(
        system=route_system(ctx, index, caller),
        messages=[*recent, {"role": "user", "content": question}],
        model=settings.llm_model_router,
        reasoning_effort="low",
        json_object=True,
    )
    usage += route.usage
    plan = parse_json_object(route.text)
    if not plan and route.tool_calls:
        # gpt-oss sometimes "calls" an index entry instead of writing the JSON; the provider
        # salvages that call from Groq's rejection and the name is exactly the routing we wanted
        plan = {"intent": "information", "candidate_tools": [c.name for c in route.tool_calls]}

    intent = str(plan.get("intent") or "")
    needs_rag = bool(plan.get("needs_rag"))
    rag_query = str(plan.get("rag_query") or "").strip() or question  # the router's rewrite, else the question
    candidates = _candidate_names(plan.get("candidate_tools"), ctx.role)

    # --- fast path ----------------------------------------------------------
    if intent == "smalltalk" and not candidates and not needs_rag:
        reply = provider.chat(
            system=synthesize_system(ctx, caller),
            messages=[*recent, {"role": "user", "content": question}],
            model=settings.llm_model_main,
            reasoning_effort="low",
            max_tokens=300,
        )
        return TurnResult(
            text=reply.text, usage=usage + reply.usage, intent=intent, path="smalltalk"
        )

    calls: list[tuple[str, dict[str, Any]]] = []
    path = "full"

    if len(candidates) == 1 and not model_params(REGISTRY.get(candidates[0])):
        # one unambiguous tool that takes no arguments at all — Call B has nothing to decide.
        # (Optional filters count: "below 75% in 24CS202T" must reach the tool, and only the
        # planner can lift the course out of the question.)
        calls = [(candidates[0], {})]
        path = "fast"
    elif candidates:
        # --- Call B: plan ---------------------------------------------------
        planned = provider.chat(
            system=plan_system(ctx, caller),
            messages=[*recent, {"role": "user", "content": question}],
            model=settings.llm_model_main,
            tools=schemas_for(candidates, ctx.role),
            reasoning_effort="low",
        )
        usage += planned.usage
        calls = [(c.name, c.arguments) for c in planned.tool_calls[:MAX_TOOL_CALLS]]

    # --- execute ------------------------------------------------------------
    runs = [_execute(tool_name, args, ctx, db) for tool_name, args in calls]

    card = _confirmation_card(runs)
    if card is not None:
        # a tool wants confirmation: return the preview and stop before synthesis
        return TurnResult(
            cards=[card], tool_runs=runs, usage=usage, intent=intent, path="confirm"
        )
    data_cards = [c for r in runs for c in r.cards]

    if not needs_rag:
        # a personal-record tool ran whose figures only mean something against a rule
        # (68% against the 75% floor): fetch that rule whatever the router decided
        rag_query = next((POLICY_CONTEXT[r.name] for r in runs if r.ok and r.name in POLICY_CONTEXT), "")
    passages = _retrieve(rag_query, ctx, db) if rag_query else []
    passages = _merge_passages(passages, runs)

    # --- Call C: synthesize (no tools attached, by design) ------------------
    final = provider.chat(
        system=synthesize_system(ctx, caller),
        messages=[
            *recent,
            {
                "role": "user",
                "content": synthesize_user(
                    question, [r.as_prompt_block() for r in runs if r.name not in PASSAGE_TOOLS], passages
                ),
            },
        ],
        model=settings.llm_model_main,
        reasoning_effort="medium",
    )
    usage += final.usage

    if not final.text and final.tool_calls:
        # the model wanted more data mid-answer (salvaged from a no-tools rejection): run
        # those calls through the registry like any others, then synthesize once more
        extra = [_execute(c.name, c.arguments, ctx, db) for c in final.tool_calls[:MAX_TOOL_CALLS]]
        runs += extra
        data_cards += [c for r in extra for c in r.cards]
        passages = _merge_passages(passages, extra)
        final = provider.chat(
            system=synthesize_system(ctx, caller),
            messages=[
                *recent,
                {
                    "role": "user",
                    "content": synthesize_user(
                        question, [r.as_prompt_block() for r in runs if r.name not in PASSAGE_TOOLS], passages
                    ),
                },
            ],
            model=settings.llm_model_main,
            reasoning_effort="medium",
        )
        usage += final.usage

    text, citations = resolve_citations(final.text, passages)
    return TurnResult(
        text=text,
        citations=citations,
        cards=data_cards,
        tool_runs=runs,
        usage=usage,
        intent=intent,
        path=path,
    )


# --- helpers ----------------------------------------------------------------


def _trim(history: Sequence[Msg]) -> list[Msg]:
    """Last HISTORY_TURNS user+assistant pairs (plan.md §4)."""
    return list(history)[-(HISTORY_TURNS * 2) :]


def _candidate_names(raw: Any, role: Role) -> list[str]:
    """Keep only real tools this role may see — Call A is an LLM and can invent."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or item in out or item not in REGISTRY:
            continue
        if REGISTRY.get(item).visible_to(role):
            out.append(item)
    return out[:MAX_CANDIDATES]


def _execute(name: str, args: dict[str, Any], ctx: AuthContext, db: Session) -> ToolRun:
    """Run one tool through the registry. A failure becomes a result, not a 500."""
    try:
        result = REGISTRY.invoke(name, ctx, db, args)
    except ToolDenied:
        # already audited as 'denied'; Call C turns this into the refusal rule, the UI into a denied card
        return ToolRun(
            name, args, "(not available to this caller)", ok=False, error="denied",
            cards=cards_for(name, None, ok=False, error="denied"),
        )
    except KeyError:
        return ToolRun(name, args, "(no such tool)", ok=False, error="unknown_tool")
    except TypeError as exc:  # the model invented an argument the tool doesn't take
        log.warning("tool %s called with bad arguments %s: %s", name, args, exc)
        return ToolRun(name, args, "(could not run: bad arguments)", ok=False, error="bad_args")
    except Exception as exc:  # noqa: BLE001 - one broken tool must not lose the turn
        log.exception("tool %s failed", name)
        return ToolRun(name, args, "(tool failed)", ok=False, error=str(exc))

    preview = result if isinstance(result, dict) and result.get("needs_confirmation") else None
    passages = None
    if name in PASSAGE_TOOLS and isinstance(result, list):
        passages = [h for h in result if isinstance(h, dict) and "chunk_id" in h]
    elif isinstance(result, dict) and isinstance(result.get("passages"), list):
        # a data tool that also names the document its rows came from (the calendar)
        passages = [h for h in result["passages"] if isinstance(h, dict) and "chunk_id" in h]
        result = {k: v for k, v in result.items() if k != "passages"}  # they go in the passage block, once
    return ToolRun(
        name, args, compact(result), preview=preview, passages=passages,
        cards=cards_for(name, result, ok=True, error=None),
    )


def _merge_passages(passages: list[dict[str, Any]], runs: list[ToolRun]) -> list[dict[str, Any]]:
    """Retrieval-tool hits join the passage list (deduplicated by chunk id), so the answer can cite them.

    Those runs are then left out of the "Tool results" block: a passage carries
    a chunk id, a markdown table of the same text would not.
    """
    out = list(passages)
    seen = {str(p.get("chunk_id")) for p in out}
    for run in runs:
        for hit in run.passages or []:
            key = str(hit.get("chunk_id"))
            if key not in seen:
                seen.add(key)
                out.append(hit)
    return out


def _confirmation_card(runs: list[ToolRun]) -> dict[str, Any] | None:
    """Two-phase confirm (plan.md §7).

    An action tool returns {"needs_confirmation": True, ...}; the turn stops
    here and the preview goes back to the UI instead of an answer. No action
    tools are registered yet, so today this is always None.
    """
    for run in runs:
        if run.ok and run.preview is not None:
            return {"type": "confirm", "tool": run.name, "args": run.args, **run.preview}
    return None


def _retrieve(question: str, ctx: AuthContext, db: Session) -> list[dict[str, Any]]:
    """Policy passages for the grounding rule.

    Routed through the registry like any other tool so retrieval is audited too.
    Returns [] when nothing is ingested or retrieval fails — Call C is told to
    say the policy could not be found rather than invent one.
    """
    if RAG_TOOL not in REGISTRY:
        return []
    try:
        hits = REGISTRY.invoke(RAG_TOOL, ctx, db, {"query": question})
    except Exception:  # noqa: BLE001
        log.exception("policy retrieval failed")
        return []
    return list(hits or [])[:RAG_TOP_K]


def _caller_name(db: Session, ctx: AuthContext) -> str | None:
    """First name only — enough to address the caller, nothing extra in the prompt."""
    row: Any = None
    if ctx.role is Role.STUDENT:
        row = db.get(Student, ctx.student_id)
    elif ctx.role is Role.FACULTY:
        row = db.get(Faculty, ctx.faculty_id)
    else:
        row = db.get(Admin, ctx.admin_id)
    full = getattr(row, "full_name", None)
    return full.split()[0] if full else None
