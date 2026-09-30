"""The eval harness's own bookkeeping (eval/run_eval.py): the golden set must stay valid, and the
summary must aggregate what the outcomes carry. Nothing here calls the LLM."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RUN_EVAL = Path(__file__).resolve().parents[2] / "eval" / "run_eval.py"


@pytest.fixture(scope="module")
def harness():
    spec = importlib.util.spec_from_file_location("run_eval", RUN_EVAL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its @dataclass classes resolve their string annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def test_the_golden_set_loads_and_validates(harness):
    cases = harness.load_cases(RUN_EVAL.parent / "golden_set.yaml")  # exits non-zero on a bad annotation
    annotated = [c for c in cases if c.expect_sources]
    assert len(annotated) >= 15 and all(c.expect_citation for c in annotated)  # only answers that must cite carry sources


def test_validate_rejects_malformed_expectations(harness):
    good = dict(id="x1", role="student", question="q")
    bad = [
        harness.Case(**good, expect_sources=[{"section": "§1"}]),  # no doc
        harness.Case(**good, expect_facts=[[]]),  # empty alternatives
        harness.Case(**good, expect_facts=[""]),
        harness.Case(**good, expect_refusal=True, expect_facts=["75"]),
    ]
    for case in bad:
        assert harness.validate([case]), case


def _outcome(harness, **kw):
    return harness.Outcome(id="o", role="student", question="q", tags=[], ok=True, **kw)


def test_quality_summary_aggregates_retrieval_facts_and_reference_free_scores(harness):
    hit = {"hit@1": True, "hit@3": True, "hit@5": True, "rank": 1, "precision": 0.5, "cite_precision": 1.0}
    late = {"hit@1": False, "hit@3": True, "hit@5": True, "rank": 2, "precision": 0.25, "cite_precision": None}
    miss = {"hit@1": False, "hit@3": False, "hit@5": False, "rank": None, "precision": 0.0, "cite_precision": None}
    free = {"context_precision": 0.2, "claims": 2, "claims_cited": 1, "numbers": 4, "numbers_grounded": 3,
            "ungrounded_numbers": ["71%"], "tool_success": 1.0}
    outs = [
        _outcome(harness, retrieval=hit, fact_recall=1.0, scores=free),
        _outcome(harness, retrieval=late, fact_recall=0.5, scores=free),
        _outcome(harness, retrieval=miss, fact_recall=0.0, scores=free),
        _outcome(harness),  # no expectations, no scores
    ]
    q = harness.quality(outs)
    r = q["retrieval"]
    assert r["n"] == 3 and r["recall@1"] == pytest.approx(1 / 3) and r["recall@3"] == pytest.approx(2 / 3)
    assert r["mrr"] == pytest.approx((1 + 0.5 + 0) / 3) and r["precision"] == pytest.approx(0.25)
    assert r["citation_precision"] == 1.0  # only one case cited anything
    assert q["facts"] == {"n": 3, "recall": pytest.approx(0.5), "answers_complete": 1}
    rf = q["reference_free"]
    assert rf["numeric_grounding"]["rate"] == 0.75 and rf["numeric_grounding"]["answers_with_ungrounded"] == 3
    assert rf["citation_coverage"] == {"hits": 3, "n": 6, "rate": 0.5}


def test_stage_latency_skips_stages_that_did_not_run(harness):
    outs = [
        _outcome(harness, timings={"route_ms": 100, "plan_ms": None, "total_ms": 900}),
        _outcome(harness, timings={"route_ms": 300, "plan_ms": 500, "total_ms": 1500}),
    ]
    st = harness.stage_latency(outs)
    assert st["route_ms"]["median"] == 200 and st["route_ms"]["n"] == 2
    assert st["plan_ms"] == {"median": 500, "p90": 500, "n": 1}
    assert st["retrieve_ms"]["n"] == 0 and st["retrieve_ms"]["median"] is None
