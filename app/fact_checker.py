"""Step 2+3 of the pipeline: ground each claim in live web evidence (Parallel
Search) and have Gemini render a verdict citing that evidence.

This is the deterministic, multi-step agent the hackathon asks for:
  extract_claims (Gemini) -> search (Parallel) -> verdict (Gemini, grounded
  on the search results it was actually given -- never asked to verdict
  from its own prior knowledge alone).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.claim_extractor import Claim, extract_claims
from app.gemini_client import GeminiClient, ModelUnavailable
from app.parallel_client import ParallelClient, SearchResult, SearchUnavailable

VERDICT_PROMPT = """You are fact-checking one claim from a film/video script
against live web search results. Do not use outside knowledge -- base your
verdict ONLY on the evidence below.

Claim: {claim}

Evidence (from live web search):
{evidence}

Return a JSON object with:
  "verdict": one of "CONFIRMED", "CONTRADICTED", "UNVERIFIABLE"
  "reasoning": one sentence explaining the verdict, citing which source (by number) it relies on
  "confidence": a number 0-1

Use UNVERIFIABLE if the evidence is empty, irrelevant, or doesn't clearly confirm or contradict the claim.
"""


@dataclass
class ClaimVerdict:
    claim: Claim
    verdict: str
    reasoning: str
    confidence: float
    sources: list[SearchResult] = field(default_factory=list)
    error: str | None = None


def _format_evidence(results: list[SearchResult]) -> str:
    if not results:
        return "(no search results returned)"
    lines = []
    for i, r in enumerate(results, start=1):
        lines.append(f"[{i}] {r.title} -- {r.url}\n    {r.snippet}")
    return "\n".join(lines)


def _check_one_claim(
    claim: Claim, gemini: GeminiClient, parallel: ParallelClient
) -> ClaimVerdict:
    try:
        results = parallel.search(claim.claim)
    except SearchUnavailable as exc:
        return ClaimVerdict(claim=claim, verdict="UNVERIFIABLE", reasoning="", confidence=0.0, error=str(exc))

    try:
        parsed = gemini.complete_json(
            VERDICT_PROMPT.format(claim=claim.claim, evidence=_format_evidence(results))
        )
    except ModelUnavailable as exc:
        return ClaimVerdict(
            claim=claim, verdict="UNVERIFIABLE", reasoning="", confidence=0.0, sources=results, error=str(exc)
        )

    if not isinstance(parsed, dict):
        parsed = {}
    return ClaimVerdict(
        claim=claim,
        verdict=str(parsed.get("verdict", "UNVERIFIABLE")),
        reasoning=str(parsed.get("reasoning", "")),
        confidence=float(parsed.get("confidence", 0.0) or 0.0),
        sources=results,
    )


def check_script(
    script: str,
    gemini: GeminiClient | None = None,
    parallel: ParallelClient | None = None,
    max_workers: int = 5,
    max_claims: int | None = None,
) -> list[ClaimVerdict]:
    gemini = gemini or GeminiClient()
    parallel = parallel or ParallelClient()

    claims = extract_claims(script, client=gemini)
    if not claims:
        return []
    if max_claims is not None and len(claims) > max_claims:
        # Bound the fan-out: every claim costs one Parallel search + one Gemini
        # call. The first N claims in script order are checked; the rest are
        # dropped here rather than silently timing out the whole request.
        claims = claims[:max_claims]

    # Each claim's search+verdict is independent of the others, so run them
    # concurrently -- sequentially, an 8-claim script took 60-120s (measured
    # live against Cloud Run); a script-length claim count stays well under
    # both APIs' rate limits at this concurrency.
    with ThreadPoolExecutor(max_workers=min(max_workers, len(claims))) as pool:
        return list(pool.map(lambda c: _check_one_claim(c, gemini, parallel), claims))
