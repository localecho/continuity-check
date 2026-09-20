"""Deterministic tests -- no network, no GCP/Parallel credentials required.

Fakes stand in for GeminiClient and ParallelClient so these tests prove the
pipeline's control flow and fail-closed behavior, not the live APIs (that's
what `app/main.py`'s /health endpoint and a manual `curl` are for once real
credentials exist -- see SETUP_TODO.md).
"""
from __future__ import annotations

from app.claim_extractor import Claim, extract_claims
from app.fact_checker import check_script
from app.gemini_client import ModelUnavailable
from app.parallel_client import SearchResult, SearchUnavailable


class FakeGemini:
    """Returns canned JSON per call, in order, to drive a specific script path."""

    def __init__(self, json_responses: list):
        self._responses = list(json_responses)
        self.calls: list[str] = []

    def complete_json(self, prompt: str, *, temperature: float = 0.0):
        self.calls.append(prompt)
        if not self._responses:
            raise ModelUnavailable("FakeGemini ran out of canned responses")
        return self._responses.pop(0)


class FakeParallel:
    def __init__(self, results_by_query: dict[str, list[SearchResult]] | None = None, raise_error: bool = False):
        self._results = results_by_query or {}
        self._raise = raise_error
        self.queries: list[str] = []

    def search(self, query: str):
        self.queries.append(query)
        if self._raise:
            raise SearchUnavailable("no PARALLEL_API_KEY set (test double)")
        return self._results.get(query, [])


def test_extract_claims_filters_malformed_entries():
    fake = FakeGemini(
        [
            [
                {"claim": "The Eiffel Tower is in Paris.", "source_line": "L1", "category": "place"},
                {"not_a_claim_field": "junk"},
                {"claim": "", "source_line": "L2", "category": "other"},
            ]
        ]
    )
    claims = extract_claims("some script", client=fake)
    assert len(claims) == 1
    assert claims[0].claim == "The Eiffel Tower is in Paris."
    assert claims[0].category == "place"


def test_extract_claims_rejects_non_list_response():
    fake = FakeGemini([{"oops": "not a list"}])
    try:
        extract_claims("script", client=fake)
        assert False, "expected ModelUnavailable"
    except ModelUnavailable:
        pass


def test_check_script_confirms_claim_with_evidence():
    gemini = FakeGemini(
        [
            [{"claim": "NASA landed Apollo 11 in 1969.", "source_line": "L3", "category": "historical"}],
            {"verdict": "CONFIRMED", "reasoning": "Source [1] confirms the 1969 date.", "confidence": 0.95},
        ]
    )
    parallel = FakeParallel(
        {
            "NASA landed Apollo 11 in 1969.": [
                SearchResult(url="https://nasa.gov/apollo11", title="Apollo 11", snippet="Landed July 20, 1969.")
            ]
        }
    )
    verdicts = check_script("script text", gemini=gemini, parallel=parallel)
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v.verdict == "CONFIRMED"
    assert v.confidence == 0.95
    assert len(v.sources) == 1
    assert v.error is None


def test_check_script_marks_unverifiable_when_search_unavailable():
    gemini = FakeGemini(
        [[{"claim": "Some claim.", "source_line": "L1", "category": "other"}]]
    )
    parallel = FakeParallel(raise_error=True)
    verdicts = check_script("script text", gemini=gemini, parallel=parallel)
    assert len(verdicts) == 1
    assert verdicts[0].verdict == "UNVERIFIABLE"
    assert verdicts[0].error is not None
    assert "PARALLEL_API_KEY" in verdicts[0].error


def test_check_script_no_claims_returns_empty_list():
    gemini = FakeGemini([[]])
    parallel = FakeParallel()
    verdicts = check_script("no factual claims here", gemini=gemini, parallel=parallel)
    assert verdicts == []
    assert parallel.queries == []


def test_check_script_strips_whitespace_around_verdict():
    """Found by eval/run_eval.py's 11k-example synthetic harness: a model
    response of "  CONFIRMED  " (incidental whitespace, common in real LLM
    JSON output) silently collapsed to UNVERIFIABLE because the ALLOWED_VERDICTS
    membership check ran .upper() but never .strip()."""
    gemini = FakeGemini(
        [
            [{"claim": "Water boils at 100 degrees Celsius.", "source_line": "L1", "category": "technical"}],
            {"verdict": "  CONFIRMED  ", "reasoning": "Standard reference value.", "confidence": 0.9},
        ]
    )
    parallel = FakeParallel(
        {"Water boils at 100 degrees Celsius.": [
            SearchResult(url="https://example.test/water", title="Water", snippet="Boils at 100C at sea level.")
        ]}
    )
    verdicts = check_script("script", gemini=gemini, parallel=parallel)
    assert len(verdicts) == 1
    assert verdicts[0].verdict == "CONFIRMED"


def test_check_script_survives_non_numeric_confidence():
    """Found by eval/run_eval.py's synthetic harness: a model returning
    confidence as a non-numeric string ("high") crashed float(...) uncaught,
    taking down the whole check_script call for that batch instead of
    degrading gracefully to a default confidence."""
    gemini = FakeGemini(
        [
            [{"claim": "Gold has the chemical symbol Au.", "source_line": "L1", "category": "technical"}],
            {"verdict": "CONFIRMED", "reasoning": "Standard reference.", "confidence": "high"},
        ]
    )
    parallel = FakeParallel(
        {"Gold has the chemical symbol Au.": [
            SearchResult(url="https://example.test/gold", title="Gold", snippet="Symbol: Au.")
        ]}
    )
    verdicts = check_script("script", gemini=gemini, parallel=parallel)
    assert len(verdicts) == 1
    assert verdicts[0].verdict == "CONFIRMED"
    assert verdicts[0].confidence == 0.0
