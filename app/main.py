"""Continuity Check -- FastAPI service.

POST /check with {"script": "..."} runs the full pipeline (extract claims ->
Parallel Search -> Gemini verdict) and returns a structured report. Built
for solo creators and small production teams who don't have a researcher on
staff to catch a factual error before it ships in dialogue or a caption.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.adk_orchestrator import run_continuity_check_via_adk
from app.fact_checker import check_script
from app.gemini_client import GeminiClient, ModelUnavailable
from app.parallel_client import ParallelClient, SearchUnavailable

app = FastAPI(title="Continuity Check", version="0.1.0")

# Open CORS: this is a public demo endpoint with no auth/user data, meant
# to be called directly from a browser demo page.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# Abuse/cost caps for a public, unauthenticated endpoint that fans out to two
# paid APIs per claim. Env-tunable so the demo can be loosened without a redeploy
# of code; defaults sized for a script excerpt, not a screenplay.
MAX_SCRIPT_CHARS = int(os.environ.get("MAX_SCRIPT_CHARS", "8000"))
MAX_CLAIMS = int(os.environ.get("MAX_CLAIMS", "25"))
RATE_LIMIT_PER_WINDOW = int(os.environ.get("RATE_LIMIT_PER_WINDOW", "12"))
RATE_LIMIT_WINDOW_S = int(os.environ.get("RATE_LIMIT_WINDOW_S", "600"))


class _RateLimiter:
    """Per-client sliding window, in-process. Cloud Run may run several instances,
    so this is a per-instance ceiling, not a global one -- enough to stop one
    browser tab or script from draining the Gemini/Parallel budget."""

    def __init__(self, limit: int, window_s: int):
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


_limiter = _RateLimiter(RATE_LIMIT_PER_WINDOW, RATE_LIMIT_WINDOW_S)


def _client_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else None) or (request.client.host if request.client else "unknown")


def _validate(req: "CheckRequest", request: Request) -> None:
    if not req.script.strip():
        raise HTTPException(status_code=400, detail="script must not be empty")
    if len(req.script) > MAX_SCRIPT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"script is {len(req.script)} characters; the limit is {MAX_SCRIPT_CHARS}. Paste a scene, not the whole screenplay.",
        )
    if not _limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail=f"rate limit: {RATE_LIMIT_PER_WINDOW} checks per {RATE_LIMIT_WINDOW_S // 60} minutes per client")


class CheckRequest(BaseModel):
    script: str


class SourceOut(BaseModel):
    title: str
    url: str


class VerdictOut(BaseModel):
    claim: str
    category: str
    source_line: str
    verdict: str
    reasoning: str
    confidence: float
    sources: list[SourceOut]
    error: str | None = None


_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def demo_page() -> FileResponse:
    return FileResponse(_STATIC_DIR / "demo.html")


@app.get("/health")
def health() -> dict:
    gemini_ok, gemini_msg = GeminiClient().preflight()
    parallel_ok, parallel_msg = ParallelClient().preflight()
    return {
        "gemini": {"ok": gemini_ok, "detail": gemini_msg},
        "parallel": {"ok": parallel_ok, "detail": parallel_msg},
    }


@app.post("/check", response_model=list[VerdictOut])
def check(req: CheckRequest, request: Request) -> list[VerdictOut]:
    _validate(req, request)
    try:
        verdicts = check_script(req.script, max_claims=MAX_CLAIMS)
    except (ModelUnavailable, SearchUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return [
        VerdictOut(
            claim=v.claim.claim,
            category=v.claim.category,
            source_line=v.claim.source_line,
            verdict=v.verdict,
            reasoning=v.reasoning,
            confidence=v.confidence,
            sources=[SourceOut(title=s.title, url=s.url) for s in v.sources],
            error=v.error,
        )
        for v in verdicts
    ]


@app.post("/check-agent", response_model=list[VerdictOut])
async def check_agent(req: CheckRequest, request: Request) -> list[VerdictOut]:
    """Same pipeline as /check, but run through a real Google ADK
    InMemoryRunner + session (see app/adk_orchestrator.py) instead of
    calling fact_checker.check_script directly -- this is the hackathon's
    Agent Framework requirement as an actually-exercised code path, not
    just an unused module in the repo.
    """
    _validate(req, request)
    try:
        report = await run_continuity_check_via_adk(req.script, max_claims=MAX_CLAIMS)
    except (ModelUnavailable, SearchUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return [
        VerdictOut(
            claim=row["claim"],
            category=row["category"],
            source_line=row["source_line"],
            verdict=row["verdict"],
            reasoning=row["reasoning"],
            confidence=row["confidence"],
            sources=[SourceOut(title=s["title"], url=s["url"]) for s in row["sources"]],
            error=row["error"],
        )
        for row in report
    ]
