"""GET /health calls GeminiClient().preflight() and ParallelClient().preflight() on
EVERY hit, and each preflight() does a real paid API call (a Vertex AI completion, a
Parallel search) -- confirmed by reading app/gemini_client.py and app/parallel_client.py.
Two other live systems (the Carbon Footprint calculator's claims-audit and Portfolio
Carbon Steward's --verify) plus any uptime/health-check probe can hit /health far more
often than a human hits /check, so an uncached preflight silently multiplies paid-API
spend with no traffic-shaping at all. These tests pin a process-wide TTL cache so a
burst of /health hits inside the TTL window makes at most one real call per backend.
"""
import time

from app.gemini_client import GeminiClient
from app.parallel_client import ParallelClient, SearchUnavailable


def test_gemini_preflight_is_cached_within_ttl(monkeypatch):
    calls = []

    def fake_complete(self, prompt, *, temperature=0.0):
        calls.append(1)
        return "ok"

    monkeypatch.setattr(GeminiClient, "complete", fake_complete)
    GeminiClient._preflight_cache.clear()

    now = [1000.0]
    monkeypatch.setattr("app.gemini_client.time.monotonic", lambda: now[0])

    c1 = GeminiClient(project="p", _preflight_ttl_s=60)
    c2 = GeminiClient(project="p", _preflight_ttl_s=60)  # a fresh instance, same project
    assert c1.preflight()[0] is True
    assert c2.preflight()[0] is True
    assert len(calls) == 1, "second preflight within the TTL window should reuse the cached result"

    now[0] += 61  # past the TTL
    assert c1.preflight()[0] is True
    assert len(calls) == 2, "a preflight call after TTL expiry should re-check the backend"


def test_gemini_preflight_cache_keyed_by_project(monkeypatch):
    calls = []
    monkeypatch.setattr(GeminiClient, "complete", lambda self, p, *, temperature=0.0: calls.append(1) or "ok")
    GeminiClient._preflight_cache.clear()
    monkeypatch.setattr("app.gemini_client.time.monotonic", lambda: 0.0)

    GeminiClient(project="a").preflight()
    GeminiClient(project="b").preflight()
    assert len(calls) == 2, "different projects must not share a cached preflight result"


def test_parallel_preflight_is_cached_within_ttl(monkeypatch):
    calls = []

    def fake_search(self, query):
        calls.append(1)
        return []

    monkeypatch.setattr(ParallelClient, "search", fake_search)
    ParallelClient._preflight_cache.clear()

    now = [1000.0]
    monkeypatch.setattr("app.parallel_client.time.monotonic", lambda: now[0])

    c1 = ParallelClient(api_key="k", _preflight_ttl_s=60)
    c2 = ParallelClient(api_key="k", _preflight_ttl_s=60)
    assert c1.preflight()[0] is True
    assert c2.preflight()[0] is True
    assert len(calls) == 1

    now[0] += 61
    assert c1.preflight()[0] is True
    assert len(calls) == 2


def test_gemini_preflight_failure_uses_a_shorter_ttl(monkeypatch):
    """gpt-6-astra cross-check flagged the real risk here: a symmetric TTL means a
    transient outage caches as unhealthy for the same 60s a healthy result would --
    slow to notice recovery. Failures get a short TTL (<= 10s) so recovery is
    detected fast, while healthy results still get the full TTL."""
    from app.gemini_client import ModelUnavailable

    calls = []

    def failing_complete(self, prompt, *, temperature=0.0):
        calls.append(1)
        raise ModelUnavailable("down")

    monkeypatch.setattr(GeminiClient, "complete", failing_complete)
    GeminiClient._preflight_cache.clear()

    now = [1000.0]
    monkeypatch.setattr("app.gemini_client.time.monotonic", lambda: now[0])

    c = GeminiClient(project="p", _preflight_ttl_s=60)
    assert c.preflight()[0] is False
    assert c.preflight()[0] is False
    assert len(calls) == 1, "a repeat hit inside the short failure TTL should still be cached"

    now[0] += 11  # past the short failure TTL, well inside the healthy 60s TTL
    assert c.preflight()[0] is False
    assert len(calls) == 2, "a failure result must expire faster than a healthy one"


def test_parallel_preflight_failure_uses_a_shorter_ttl(monkeypatch):
    calls = []

    def failing_search(self, query):
        calls.append(1)
        raise SearchUnavailable("down")

    monkeypatch.setattr(ParallelClient, "search", failing_search)
    ParallelClient._preflight_cache.clear()

    now = [1000.0]
    monkeypatch.setattr("app.parallel_client.time.monotonic", lambda: now[0])

    c = ParallelClient(api_key="k", _preflight_ttl_s=60)
    assert c.preflight()[0] is False
    assert c.preflight()[0] is False
    assert len(calls) == 1

    now[0] += 11
    assert c.preflight()[0] is False
    assert len(calls) == 2, "a failure result must expire faster than a healthy one"


def test_health_endpoint_does_not_double_call_within_ttl(monkeypatch):
    """The actual /health path: two hits inside the TTL window make one real call each,
    not two -- this is the concrete cost bug the caching fixes."""
    import app.main as m

    gemini_calls = []
    parallel_calls = []
    monkeypatch.setattr(m.GeminiClient, "complete", lambda self, p, *, temperature=0.0: gemini_calls.append(1) or "ok")
    monkeypatch.setattr(m.ParallelClient, "search", lambda self, q: parallel_calls.append(1) or [])
    m.GeminiClient._preflight_cache.clear()
    m.ParallelClient._preflight_cache.clear()
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "p")
    monkeypatch.setenv("PARALLEL_API_KEY", "k")

    from fastapi.testclient import TestClient
    client = TestClient(m.app)
    r1 = client.get("/health")
    r2 = client.get("/health")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["gemini"]["ok"] is True
    assert len(gemini_calls) == 1
    assert len(parallel_calls) == 1
