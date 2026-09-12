"""Phase 2 step 3 — the three-call turn (plan.md §3).

The provider is scripted, so these tests are offline and deterministic: each
test states exactly what Calls A, B and C return and then asserts on what the
orchestrator did with it. The database is real, so RBAC and the tools are too.
"""
from __future__ import annotations

import json

import pytest

from app.ai.compact import ROW_CAP, compact
from app.ai.orchestrator import run_turn
from app.ai.providers.base import LLMResponse, ToolCall, Usage
from app.ai.tools.registry import REGISTRY
from app.ai.tools.schema import function_schema, required_params, schemas_for
from app.auth.context import Role
from app.db.session import SessionLocal
from tests.conftest import make_ctx

DEMO_STUDENT_ID = 17  # roll 25BCP017


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture()
def student_ctx():
    return make_ctx("student", DEMO_STUDENT_ID)


@pytest.fixture()
def faculty_ctx():
    return make_ctx("faculty")


# --- scripted provider ------------------------------------------------------

class ScriptedProvider:
    """Returns the queued responses in order, recording every request."""

    def __init__(self, *responses: LLMResponse) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, **kwargs) -> LLMResponse:
        self.calls.append(kwargs)
        if not self.responses:
            return LLMResponse(text="(unscripted)")
        return self.responses.pop(0)


def route(intent="data", tools=(), needs_rag=False, tokens=(120, 30), rag_query=None) -> LLMResponse:
    body = {"intent": intent, "candidate_tools": list(tools), "needs_rag": needs_rag}
    if rag_query is not None:
        body["rag_query"] = rag_query
    return LLMResponse(text=json.dumps(body), usage=Usage(*tokens))


def plan(*calls: tuple[str, dict], tokens=(200, 40)) -> LLMResponse:
    return LLMResponse(
        tool_calls=[ToolCall(id=f"c{i}", name=n, arguments=a) for i, (n, a) in enumerate(calls)],
        usage=Usage(*tokens),
    )


def answer(text="You are at 68% in 24CS201T.", tokens=(400, 80)) -> LLMResponse:
    return LLMResponse(text=text, usage=Usage(*tokens))


# --- the schema builder (the gap step 3 had to close first) -----------------

def test_schema_omits_injected_and_identity_parameters():
    schema = function_schema(REGISTRY.get("get_my_fees"))["function"]
    assert schema["name"] == "get_my_fees"
    # ctx, db and the **_ catch-all are the registry's business, not the model's
    assert schema["parameters"]["properties"] == {}
    assert schema["parameters"]["required"] == []


def test_schema_types_and_optionality_come_from_the_signature():
    params = function_schema(REGISTRY.get("get_my_timetable"))["function"]["parameters"]
    assert params["properties"]["day"] == {"type": "integer"}  # `int | None` -> integer
    assert params["required"] == []  # it has a default, so it is optional

    below = function_schema(REGISTRY.get("list_students_below_attendance"))["function"]
    assert below["parameters"]["properties"]["course_code"] == {"type": "string"}
    assert below["parameters"]["properties"]["threshold"] == {"type": "number"}
    assert below["parameters"]["required"] == []  # course_code optional (all taught courses), threshold defaults to 75


def test_identity_arg_never_appears_in_any_schema():
    """Layer 3 strips these at invoke time; they must not be advertised either."""
    for spec in REGISTRY.all():
        props = function_schema(spec)["function"]["parameters"]["properties"]
        assert "student_id" not in props
        assert "faculty_id" not in props
        assert "user_id" not in props


def test_schemas_for_drops_unknown_and_off_limits_names():
    names = ["get_my_courses", "list_course_students", "not_a_tool"]
    got = [s["function"]["name"] for s in schemas_for(names, Role.STUDENT)]
    assert got == ["get_my_courses"]  # the faculty tool and the invented one are gone


def test_required_params_spots_the_no_argument_fast_path():
    assert required_params(REGISTRY.get("get_my_courses")) == []
    assert required_params(REGISTRY.get("list_course_students")) == []  # optional since the live-run fix
    assert required_params(REGISTRY.get("get_course_syllabus")) == ["course"]


# --- result compaction ------------------------------------------------------

def test_compact_renders_rows_as_a_markdown_table():
    md = compact([{"course": "24CS201T", "percent": 68.0}])
    assert md.splitlines()[0] == "| course | percent |"
    assert md.splitlines()[2] == "| 24CS201T | 68 |"


def test_compact_caps_rows_and_says_how_many_were_hidden():
    md = compact([{"n": i} for i in range(ROW_CAP + 5)])
    assert md.count("\n|") == ROW_CAP + 1  # header rule + capped body rows
    assert f"(5 more rows not shown; {ROW_CAP + 5} in total.)" in md


def test_compact_distinguishes_empty_from_missing():
    assert compact([]) == "(no rows)"
    assert compact(None) == "(no data)"


def test_compact_renders_a_single_dict_as_bullets():
    assert compact({"roll_no": "25BCP017", "cgpa": None}) == "- **roll_no**: 25BCP017\n- **cgpa**: -"


# --- the turn ---------------------------------------------------------------

def test_full_turn_routes_plans_executes_and_synthesizes(student_ctx, db):
    provider = ScriptedProvider(
        route(tools=["get_my_attendance", "get_my_courses"]),
        plan(("get_my_attendance", {"course": "24CS201T"})),
        answer(),
    )
    out = run_turn(
        question="how is my attendance in 24CS201T?",
        ctx=student_ctx,
        db=db,
        provider=provider,
    )

    assert out.path == "full"
    assert len(provider.calls) == 3
    assert [r.name for r in out.tool_runs] == ["get_my_attendance"]
    assert out.text == "You are at 68% in 24CS201T."
    assert out.usage == Usage(720, 150)  # every call is metered into the turn


def test_call_c_is_given_no_tools(student_ctx, db):
    provider = ScriptedProvider(route(tools=["get_my_courses"]), answer())
    run_turn(question="what am I enrolled in?", ctx=student_ctx, db=db, provider=provider)
    synthesis = provider.calls[-1]
    assert not synthesis.get("tools")  # structurally cannot invent a tool call here


def test_call_b_sees_only_the_candidates_full_schemas(student_ctx, db):
    provider = ScriptedProvider(
        route(tools=["get_my_marks", "get_my_results"]),
        plan(("get_my_marks", {})),
        answer(),
    )
    run_turn(question="how did I do?", ctx=student_ctx, db=db, provider=provider)
    sent = [s["function"]["name"] for s in provider.calls[1]["tools"]]
    assert sent == ["get_my_marks", "get_my_results"]


def test_single_no_argument_tool_takes_the_fast_path(student_ctx, db):
    provider = ScriptedProvider(route(tools=["get_my_courses"]), answer())
    out = run_turn(question="what am I enrolled in?", ctx=student_ctx, db=db, provider=provider)

    assert out.path == "fast"
    assert len(provider.calls) == 2  # Call B skipped entirely
    assert [r.name for r in out.tool_runs] == ["get_my_courses"]
    assert "24CS" in out.tool_runs[0].markdown or "|" in out.tool_runs[0].markdown


def test_smalltalk_skips_tools_and_retrieval(student_ctx, db):
    provider = ScriptedProvider(route(intent="smalltalk"), answer(text="Hello!"))
    out = run_turn(question="hi there", ctx=student_ctx, db=db, provider=provider)

    assert out.path == "smalltalk"
    assert out.tool_runs == []
    assert out.text == "Hello!"
    assert len(provider.calls) == 2


def test_route_index_is_filtered_to_the_callers_role(student_ctx, faculty_ctx, db):
    provider = ScriptedProvider(route(intent="smalltalk"), answer())
    run_turn(question="hi", ctx=student_ctx, db=db, provider=provider)
    student_prompt = provider.calls[0]["system"]

    provider = ScriptedProvider(route(intent="smalltalk"), answer())
    run_turn(question="hi", ctx=faculty_ctx, db=db, provider=provider)
    faculty_prompt = provider.calls[0]["system"]

    assert "get_my_fees" in student_prompt
    assert "get_my_fees" not in faculty_prompt  # never told a tool it cannot use exists
    assert "list_course_students" in faculty_prompt
    assert "list_course_students" not in student_prompt


def test_hallucinated_and_off_limits_tool_names_are_dropped(student_ctx, db):
    provider = ScriptedProvider(
        route(tools=["get_my_grades_summary", "list_course_students"]),
        answer(),
    )
    out = run_turn(question="show me everything", ctx=student_ctx, db=db, provider=provider)

    assert out.tool_runs == []  # nothing survived the filter, so nothing ran
    assert len(provider.calls) == 2  # no Call B with an empty candidate set


def test_rbac_still_blocks_a_tool_the_planner_asks_for_anyway(student_ctx, db):
    """Layer 1 filtered the index; if a call gets through anyway, Layer 2 denies it."""
    provider = ScriptedProvider(
        route(tools=["get_my_courses", "get_my_marks"]),
        plan(("list_course_students", {"course_code": "24CS201T"})),
        answer(),
    )
    out = run_turn(question="who else is in my class?", ctx=student_ctx, db=db, provider=provider)

    run = out.tool_runs[0]
    assert run.ok is False
    assert run.error == "denied"
    assert "not available" in run.markdown


def test_identity_args_from_the_model_are_stripped_before_the_tool_runs(student_ctx, db):
    """The planner names another student; Layer 3 drops it and self-scope holds."""
    provider = ScriptedProvider(
        route(tools=["get_my_attendance", "get_my_courses"]),
        plan(("get_my_attendance", {"student_id": 999})),
        answer(),
    )
    out = run_turn(question="attendance for student 999", ctx=student_ctx, db=db, provider=provider)

    run = out.tool_runs[0]
    assert run.ok is True
    assert "999" not in run.markdown


def test_invented_argument_does_not_lose_the_turn(student_ctx, db):
    provider = ScriptedProvider(
        route(tools=["get_my_courses", "get_my_marks"]),
        plan(("get_my_courses", {"sort_by": "credits"})),
        answer(),
    )
    out = run_turn(question="my courses by credits", ctx=student_ctx, db=db, provider=provider)

    # every tool takes **_, so an unknown kwarg is absorbed rather than raising
    assert out.tool_runs[0].ok is True
    assert out.text  # synthesis still ran


def test_malformed_route_reply_degrades_instead_of_raising(student_ctx, db):
    provider = ScriptedProvider(LLMResponse(text="I'm not sure what to do"), answer())
    out = run_turn(question="???", ctx=student_ctx, db=db, provider=provider)

    assert out.tool_runs == []
    assert out.text  # Call C still answers, with no data to ground on


def test_needs_rag_retrieves_passages_and_resolves_only_cited_ones(student_ctx, db, monkeypatch):
    passages = [
        {"chunk_id": 11, "document": "Attendance Policy", "section": "3.1", "excerpt": "75% required."},
        {"chunk_id": 12, "document": "Attendance Policy", "section": "3.2", "excerpt": "Condonation."},
        {"chunk_id": 13, "document": "Exam Rules", "section": "9", "excerpt": "Debarred below 75%."},
        {"chunk_id": 14, "document": "Exam Rules", "section": "10", "excerpt": "Not retrieved."},
    ]
    monkeypatch.setattr("app.ai.orchestrator._retrieve", lambda *a, **k: passages[:3])

    provider = ScriptedProvider(
        route(tools=["get_my_attendance"], needs_rag=True),
        answer(text="You need 75% [[cite:11]] and you are below it [[cite:13]]. [[cite:99]]"),
    )
    out = run_turn(question="am I short on attendance?", ctx=student_ctx, db=db, provider=provider)

    assert [c["chunk_id"] for c in out.citations] == [11, 13]  # 12 uncited, 99 unknown
    assert [c["n"] for c in out.citations] == [1, 2]
    assert out.text == "You need 75% [1] and you are below it [2]."  # markers numbered, unknown dropped
    prompt = provider.calls[-1]["messages"][-1]["content"]
    assert "[[cite:11]] Attendance Policy - 3.1" in prompt


def test_retrieval_uses_the_routers_rag_query_when_given(student_ctx, db, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr("app.ai.orchestrator._retrieve", lambda q, *a, **k: seen.append(q) or [])

    provider = ScriptedProvider(route(needs_rag=True, rag_query="minimum attendance for exam eligibility"), answer())
    run_turn(question="am I short on attendance?", ctx=student_ctx, db=db, provider=provider)
    provider = ScriptedProvider(route(needs_rag=True), answer())
    run_turn(question="am I short on attendance?", ctx=student_ctx, db=db, provider=provider)
    provider = ScriptedProvider(route(needs_rag=True, rag_query="   "), answer())
    run_turn(question="am I short on attendance?", ctx=student_ctx, db=db, provider=provider)

    assert seen == ["minimum attendance for exam eligibility", "am I short on attendance?", "am I short on attendance?"]


def test_turn_runs_through_the_budgeted_provider(student_ctx, db):
    """The step-4 wrapper is a drop-in LLMProvider: a whole turn goes through it."""
    from app.ai.budget import BudgetedProvider

    scripted = ScriptedProvider(route(tools=["get_my_courses"]), answer(text="Nine courses."))
    provider = BudgetedProvider(scripted, tpm=100_000, rpm=1000, sleeper=lambda s: None)

    out = run_turn(question="what am I enrolled in?", ctx=student_ctx, db=db, provider=provider)

    assert out.text == "Nine courses."
    assert provider.meter.calls == 2
    assert provider.meter.usage == out.usage  # the meter and the turn agree


def test_history_is_trimmed_to_the_last_three_turns(student_ctx, db):
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(12)
    ]
    provider = ScriptedProvider(route(intent="smalltalk"), answer())
    run_turn(question="hi", ctx=student_ctx, db=db, history=history, provider=provider)

    sent = provider.calls[0]["messages"]
    assert len(sent) == 7  # 6 history messages + this question
    assert sent[0]["content"] == "m6"


def test_a_personal_record_tool_pulls_its_regulation_even_when_the_router_says_no_rag(student_ctx, db, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr("app.ai.orchestrator._retrieve", lambda q, *a, **k: seen.append(q) or [])
    provider = ScriptedProvider(route(tools=["get_my_attendance"], needs_rag=False), answer())
    run_turn(question="am I short on attendance?", ctx=student_ctx, db=db, provider=provider)
    assert seen and "attendance" in seen[0] and "eligibility" in seen[0]

    seen.clear()
    provider = ScriptedProvider(route(intent="smalltalk"), answer("hi"))
    run_turn(question="hi", ctx=student_ctx, db=db, provider=provider)
    assert seen == []  # no tool with a policy counterpart, no retrieval


# --- salvaged phantom tool calls (live finding: Groq 400 tool_use_failed) ----

def test_a_salvaged_router_tool_call_is_the_candidate(student_ctx):
    """The router 'called' get_my_exam_schedule instead of writing JSON: that is the route."""
    provider = ScriptedProvider(
        LLMResponse(tool_calls=[ToolCall(id="salvaged", name="get_my_exam_schedule", arguments={"term": "x"})]),
        answer("Exams run 17-28 Nov."),
    )
    with SessionLocal() as db:
        out = run_turn(question="when are the end-sem exams?", ctx=student_ctx, db=db, provider=provider)
    assert out.path == "fast" and [r.name for r in out.tool_runs] == ["get_my_exam_schedule"]
    assert out.tool_runs[0].ok and out.text == "Exams run 17-28 Nov."


def test_a_salvaged_synthesis_tool_call_runs_the_tool_and_synthesizes_again(student_ctx):
    """Call C asked for data it lacked: run it through the registry (RBAC intact), then Call C once more."""
    provider = ScriptedProvider(
        route(tools=["get_my_courses"]),
        LLMResponse(tool_calls=[ToolCall(id="salvaged", name="get_my_fees", arguments={})]),  # phantom in Call C
        answer("Fees are paid; you take 9 courses."),
    )
    with SessionLocal() as db:
        out = run_turn(question="am I all set?", ctx=student_ctx, db=db, provider=provider)
    assert [r.name for r in out.tool_runs] == ["get_my_courses", "get_my_fees"] and all(r.ok for r in out.tool_runs)
    assert len(provider.calls) == 3 and "tools" not in provider.calls[2] or provider.calls[2].get("tools") is None
    assert "get_my_fees" in provider.calls[2]["messages"][-1]["content"]
    assert out.text == "Fees are paid; you take 9 courses."

    # a phantom call to a forbidden tool is still denied, and the second synthesis sees that
    provider = ScriptedProvider(
        route(tools=["get_my_courses"]),
        LLMResponse(tool_calls=[ToolCall(id="salvaged", name="list_students", arguments={})]),
        answer("Not available to your role."),
    )
    with SessionLocal() as db:
        out = run_turn(question="list everyone", ctx=student_ctx, db=db, provider=provider)
    assert out.tool_runs[-1].error == "denied" and any(c["type"] == "denied" for c in out.cards)
