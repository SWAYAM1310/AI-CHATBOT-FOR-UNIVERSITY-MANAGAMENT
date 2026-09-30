"""The reference-free turn scores (app.ai.scoring): pure functions, no database, no provider."""
from __future__ import annotations

from app.ai.orchestrator import ToolRun
from app.ai.scoring import score_turn

FLOOR = {
    "chunk_id": 1, "document": "Part IV", "section": "§4.2", "score": 0.0328, "dense_rank": 1, "sparse_rank": 2,
    "excerpt": "A student must maintain minimum attendance of 75 percent in each course to sit the end-semester examination.",
}
NOISE = {"chunk_id": 2, "document": "Part V", "section": "§9.1", "score": 0.0161, "dense_rank": 3, "sparse_rank": None,
         "excerpt": "Copying in an examination is punished with cancellation of the paper."}
ATTENDANCE = ToolRun("get_my_attendance", {}, "| course | attended | total | percent |\n| --- | --- | --- | --- |\n| 24CS201T | 34 | 50 | 68 |")


def score(text, *, passages=(), cited=(), runs=(ATTENDANCE,), question="am I short on attendance?"):
    citations = [{"n": i + 1, "chunk_id": c} for i, c in enumerate(cited)]
    return score_turn(question=question, text=text, citations=citations, passages=list(passages), tool_runs=list(runs))


def test_retrieval_counts_which_branch_found_each_passage():
    s = score("x", passages=[FLOOR, NOISE, {"chunk_id": 3, "excerpt": "e", "dense_rank": None, "sparse_rank": 1}])
    assert (s.passages, s.both_branches, s.dense_only, s.sparse_only) == (3, 1, 1, 1)
    assert s.top_score == 0.0328


def test_passages_without_scores_still_count():
    s = score("x", passages=[{"chunk_id": 9, "excerpt": "calendar row"}])  # the academic-calendar tool gives no scores
    assert s.passages == 1 and s.top_score is None and s.both_branches == 0


def test_context_precision_is_cited_over_retrieved():
    s = score("Need 75% [1].", passages=[FLOOR, NOISE], cited=[1])
    assert s.cited == 1 and s.context_precision == 0.5


def test_context_precision_ignores_a_citation_that_was_never_offered():
    assert score("x", passages=[FLOOR], cited=[99]).cited == 0


def test_no_retrieval_means_not_applicable_rather_than_zero():
    s = score("You are at 68% in 24CS201T.")
    assert s.context_precision is None and s.citation_coverage is None


def test_citation_coverage_counts_only_sentences_that_restate_a_passage():
    text = (
        "You are at 68% attendance. "  # personal data: not a passage claim, needs no citation
        "A student must maintain minimum attendance of 75 percent in each course to sit the examination [1]. "
        "Students must maintain minimum attendance of 75 percent in each course to sit the end-semester examination."
    )
    s = score(text, passages=[FLOOR], cited=[1])
    assert (s.claims, s.claims_cited) == (2, 1) and s.citation_coverage == 0.5


def test_a_marker_after_the_full_stop_belongs_to_the_sentence_before_it():
    s = score("You need minimum attendance of 75 percent in each course to sit the end-semester examination. [1]",
              passages=[FLOOR], cited=[1])
    assert (s.claims, s.claims_cited) == (1, 1)


def test_numbers_found_in_tool_results_or_passages_are_grounded():
    s = score("You are at 68% in 24CS201T (34 of 50); the floor is 75% [1].", passages=[FLOOR], cited=[1])
    assert (s.numbers, s.numbers_grounded, s.numeric_grounding) == (4, 4, 1.0) and s.ungrounded_numbers == []


def test_a_difference_of_two_stated_figures_counts_as_grounded():
    s = score("You are 7% short of the 75% floor at 68%.", passages=[FLOOR])
    assert s.numeric_grounding == 1.0  # 75 - 68


def test_a_figure_rounded_to_the_precision_it_is_stated_at_is_grounded():
    table = ToolRun("get_my_attendance", {}, "| course | percent |\n| --- | --- |\n| 24CS201T | 67.7 |")
    s = score("You are at 68% and 7% short of the 75% floor [1].", passages=[FLOOR], cited=[1], runs=[table])
    assert s.numeric_grounding == 1.0  # 68 ~ 67.7, and 7 ~ 75 - 67.7 = 7.3
    assert score("You are at 67.9%.", runs=[table]).ungrounded_numbers == ["67.9%"]  # a stated decimal is held to it


def test_an_invented_figure_is_reported():
    s = score("You are at 71% and need 80% [1].", passages=[FLOOR], cited=[1])
    assert s.numbers_grounded == 0 and s.ungrounded_numbers == ["71%", "80%"]
    assert s.numeric_grounding == 0.0


def test_the_users_own_numbers_are_a_legitimate_source():
    s = score("At 60% you would be below the floor.", question="what if I am at 60% attendance?", runs=())
    assert s.numbers_grounded == 1


def test_codes_clause_refs_citation_markers_and_small_counts_are_not_figures():
    s = score("Under §4.2 (see [1]) you have 3 courses; 24CS201T is the one.", passages=[FLOOR], cited=[1])
    assert s.numbers == 0 and s.numeric_grounding is None


def test_tool_success_counts_refusals_and_failures():
    denied = ToolRun("list_course_students", {}, "(not available to this caller)", ok=False, error="denied")
    s = score("I can't share that.", runs=[ATTENDANCE, denied])
    assert (s.tools_run, s.tools_ok, s.tool_success) == (2, 1, 0.5)
    assert score("hi", runs=()).tool_success is None


# --- reference-based: what the eval harness adds ---------------------------------------

from app.ai.scoring import fact_recall, retrieval_metrics, source_matches  # noqa: E402

P4 = {"chunk_id": 1, "document": "Academic Regulations Part IV — Attendance", "section": "§4.2 Minimum attendance"}
P5 = {"chunk_id": 2, "document": "Academic Regulations Part V — Examination", "section": "§9.1 Misconduct"}
P6 = {"chunk_id": 3, "document": "Academic Regulations Part IV — Attendance", "section": "§5.3 Condonation"}
FLOOR_OK = [{"doc": "Part IV", "section": "§4.2"}]


def test_source_matching_is_substring_on_document_and_section():
    assert source_matches(P4, {"doc": "Part IV", "section": "§4.2"})
    assert source_matches(P4, {"doc": "Part IV", "section": ""})  # empty section = any clause of that document
    assert not source_matches(P4, {"doc": "Part IV", "section": "§5."})
    assert not source_matches(P5, {"doc": "Part IV", "section": "§4.2"})
    assert source_matches({"document": "d", "section": "§4.2.1 sub"}, {"doc": "d", "section": "§4.2"})


def test_retrieval_metrics_rank_recall_and_precision():
    m = retrieval_metrics([P5, P4, P6], [{"chunk_id": 1}, {"chunk_id": 2}], FLOOR_OK)
    assert (m["hit@1"], m["hit@3"], m["hit@5"], m["rank"]) == (False, True, True, 2)
    assert m["precision"] == 1 / 3  # one of three offered passages is acceptable
    assert m["cite_precision"] == 0.5  # it cited the right one and a wrong one


def test_retrieval_metrics_when_nothing_acceptable_was_offered():
    m = retrieval_metrics([P5], [], FLOOR_OK)
    assert m["rank"] is None and not m["hit@5"] and m["precision"] == 0.0 and m["cite_precision"] is None
    assert retrieval_metrics([], [], FLOOR_OK)["precision"] is None


def test_any_of_targets_accept_either_source():
    both = [{"doc": "Part IV", "section": "§4.2"}, {"doc": "Part V", "section": "§9.1"}]
    assert retrieval_metrics([P5], [], both)["hit@1"]


def test_fact_recall_normalises_markdown_commas_and_markers_and_accepts_alternatives():
    text = "The **Merit-cum-Means** scholarship pays ₹40,000 [1] per semester."
    assert fact_recall(text, [["merit-cum-means", "merit cum means"], "40000"]) == (1.0, [])
    recall, missing = fact_recall("You need 75%.", ["75", ["67.7", "68"], "condon"])
    assert recall == 1 / 3 and missing == ["67.7", "condon"]  # the first phrasing names a missed alternative list
    assert fact_recall("anything", []) == (None, [])
