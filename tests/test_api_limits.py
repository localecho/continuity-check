"""Input caps + rate limit on the public endpoints. The pipeline is monkeypatched so
these run with zero network calls, like the rest of the suite."""
from fastapi.testclient import TestClient

import app.main as m


def _client(monkeypatch):
    monkeypatch.setattr(m, "check_script", lambda script, max_claims=None: [])

    async def fake_adk(script, max_claims=None):
        return []

    monkeypatch.setattr(m, "run_continuity_check_via_adk", fake_adk)
    monkeypatch.setattr(m, "_limiter", m._RateLimiter(limit=3, window_s=600))
    return TestClient(m.app)


def test_empty_and_whitespace_rejected(monkeypatch):
    c = _client(monkeypatch)
    assert c.post("/check-agent", json={"script": ""}).status_code == 400
    assert c.post("/check-agent", json={"script": "   \n"}).status_code == 400


def test_oversized_script_rejected_with_413_before_any_model_call(monkeypatch):
    c = _client(monkeypatch)
    called = []
    monkeypatch.setattr(m, "check_script", lambda *a, **k: called.append(1) or [])
    r = c.post("/check", json={"script": "x" * (m.MAX_SCRIPT_CHARS + 1)})
    assert r.status_code == 413 and "limit is" in r.json()["detail"]
    assert called == []


def test_rate_limit_returns_429_after_window_budget(monkeypatch):
    c = _client(monkeypatch)
    for _ in range(3):
        assert c.post("/check-agent", json={"script": "Apollo 11 landed in 1969."}).status_code == 200
    r = c.post("/check-agent", json={"script": "Apollo 11 landed in 1969."})
    assert r.status_code == 429 and "rate limit" in r.json()["detail"]


def test_rate_limiter_window_slides():
    rl = m._RateLimiter(limit=2, window_s=10)
    assert rl.allow("a", now=0) and rl.allow("a", now=1) and not rl.allow("a", now=2)
    assert rl.allow("a", now=12)          # oldest hit aged out
    assert rl.allow("b", now=2)           # other clients unaffected


def test_max_claims_caps_fan_out(monkeypatch):
    from app import fact_checker as fc
    from app.claim_extractor import Claim

    claims = [Claim(claim=f"claim {i}", source_line="", category="other") for i in range(40)]
    monkeypatch.setattr(fc, "extract_claims", lambda script, client=None: claims)
    searched = []

    class FakeParallel:
        def search(self, q):
            searched.append(q); return []

    class FakeGemini:
        def complete_json(self, prompt):
            return {"verdict": "UNVERIFIABLE", "reasoning": "", "confidence": 0}

    out = fc.check_script("s", FakeGemini(), FakeParallel(), max_claims=25)
    assert len(out) == 25 and len(searched) == 25
