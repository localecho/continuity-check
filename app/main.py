"""Continuity Check -- FastAPI service.

POST /check with {"script": "..."} runs the full pipeline (extract claims ->
Parallel Search -> Gemini verdict) and returns a structured report. Built
for solo creators and small production teams who don't have a researcher on
staff to catch a factual error before it ships in dialogue or a caption.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
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
def check(req: CheckRequest) -> list[VerdictOut]:
    if not req.script.strip():
        raise HTTPException(status_code=400, detail="script must not be empty")
    try:
        verdicts = check_script(req.script)
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
async def check_agent(req: CheckRequest) -> list[VerdictOut]:
    """Same pipeline as /check, but run through a real Google ADK
    InMemoryRunner + session (see app/adk_orchestrator.py) instead of
    calling fact_checker.check_script directly -- this is the hackathon's
    Agent Framework requirement as an actually-exercised code path, not
    just an unused module in the repo.
    """
    if not req.script.strip():
        raise HTTPException(status_code=400, detail="script must not be empty")
    try:
        report = await run_continuity_check_via_adk(req.script)
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
