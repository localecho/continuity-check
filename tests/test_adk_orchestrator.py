"""Proves the ADK integration is real, not orphaned code -- runs the agent
through an actual google.adk.runners.InMemoryRunner (real session service,
real event loop), with fakes standing in for Gemini/Parallel so it needs no
network access or credentials. Requires google-adk to be installed.
"""
from __future__ import annotations

import asyncio

import pytest

from app.parallel_client import SearchResult
from tests.test_fact_checker import FakeGemini, FakeParallel

adk = pytest.importorskip("google.adk", reason="google-adk not installed")


def test_adk_agent_persists_report_via_state_delta():
    from app.adk_orchestrator import run_continuity_check_via_adk

    gemini = FakeGemini(
        [
            [{"claim": "Marie Curie won two Nobel Prizes.", "source_line": "L1", "category": "person"}],
            {"verdict": "CONFIRMED", "reasoning": "Source [1] confirms it.", "confidence": 0.9},
        ]
    )
    parallel = FakeParallel(
        {
            "Marie Curie won two Nobel Prizes.": [
                SearchResult(url="https://nobelprize.org", title="Marie Curie", snippet="Two prizes.")
            ]
        }
    )

    report = asyncio.run(run_continuity_check_via_adk("some script", gemini=gemini, parallel=parallel))

    assert len(report) == 1
    assert report[0]["verdict"] == "CONFIRMED"
    assert report[0]["claim"] == "Marie Curie won two Nobel Prizes."
    assert report[0]["sources"][0]["url"] == "https://nobelprize.org"


def test_adk_agent_handles_no_claims():
    from app.adk_orchestrator import run_continuity_check_via_adk

    gemini = FakeGemini([[]])
    parallel = FakeParallel()

    report = asyncio.run(run_continuity_check_via_adk("no factual claims here", gemini=gemini, parallel=parallel))

    assert report == []
