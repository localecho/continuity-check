"""Conformance of the Python to verification/ContinuityCheck.lean. Each test names the
theorem it mirrors. If `lean` is on PATH the spec itself is re-checked too."""
import shutil, subprocess
from pathlib import Path

import pytest

from app import fact_checker as fc
from app.claim_extractor import Claim
import app.main as m

ROOT = Path(__file__).resolve().parents[1]


class Gemini:
    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    def complete_json(self, prompt):
        self.calls += 1
        return self.answer


class Parallel:
    def __init__(self, results):
        self.results = results

    def search(self, q):
        return self.results


CLAIM = Claim(claim="The Berlin Wall fell in 1989.", source_line="", category="date")


def test_grade_no_evidence__model_never_consulted():
    g = Gemini({"verdict": "CONFIRMED", "reasoning": "x", "confidence": 1.0})
    v = fc._check_one_claim(CLAIM, g, Parallel([]))
    assert v.verdict == "UNVERIFIABLE" and v.sources == [] and g.calls == 0


def test_grade_sound__verdict_is_passed_through_not_invented():
    ev = [fc.SearchResult(url="https://a", title="a", snippet="s")]
    for said in ("CONFIRMED", "CONTRADICTED", "UNVERIFIABLE"):
        assert fc._check_one_claim(CLAIM, Gemini({"verdict": said}), Parallel(ev)).verdict == said
    # anything outside the three values collapses to UNVERIFIABLE (never upgraded)
    assert fc._check_one_claim(CLAIM, Gemini({"verdict": "PROBABLY TRUE"}), Parallel(ev)).verdict == "UNVERIFIABLE"
    assert fc._check_one_claim(CLAIM, Gemini("not a dict"), Parallel(ev)).verdict == "UNVERIFIABLE"


def test_capClaims_le__and__pipeline_length(monkeypatch):
    claims = [Claim(claim=f"c{i}", source_line="", category="other") for i in range(40)]
    monkeypatch.setattr(fc, "extract_claims", lambda script, client=None: claims)
    ev = [fc.SearchResult(url="https://a", title="a", snippet="s")]
    out = fc.check_script("s", Gemini({"verdict": "CONFIRMED"}), Parallel(ev), max_claims=25)
    assert len(out) == min(25, len(claims))
    out = fc.check_script("s", Gemini({"verdict": "CONFIRMED"}), Parallel(ev), max_claims=100)
    assert len(out) == min(100, len(claims))


def test_limiter_allow_keeps_bound__and__refuses_at_limit():
    rl = m._RateLimiter(limit=3, window_s=100)
    admitted = [rl.allow("k", now=t) for t in (0, 1, 2)]
    assert admitted == [True, True, True]
    assert rl.allow("k", now=3) is False            # refuses_at_limit
    assert len(rl._hits["k"]) <= 3                  # allow_keeps_bound
    assert rl.allow("k", now=101) is True           # window slid


@pytest.mark.skipif(shutil.which("lean") is None, reason="lean not installed")
def test_lean_spec_checks():
    r = subprocess.run(["lean", "ContinuityCheck.lean"], cwd=ROOT / "verification", capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
