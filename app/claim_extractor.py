"""Step 1 of the pipeline: pull checkable factual claims out of a script/brief.

A "checkable claim" is anything a Parallel Search query could confirm or
contradict -- a real person, place, date, brand, technical or historical
fact referenced in dialogue or scene description. Vague creative choices
("the room feels tense") are deliberately excluded; the extractor is
instructed to skip them.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.gemini_client import GeminiClient, ModelUnavailable

EXTRACT_PROMPT = """You are a continuity researcher for a film/video production.
Read the script excerpt below and extract every CHECKABLE factual claim --
statements about real people, places, dates, organizations, technical specs,
historical events, or brands that a web search could confirm or contradict.

Skip subjective or purely fictional statements (mood, character feelings,
invented character names/places that aren't presented as real).

Script excerpt:
---
{script}
---

Return a JSON array of objects, each with:
  "claim": the claim as a short standalone factual statement
  "source_line": the line of dialogue/description it came from
  "category": one of "person", "place", "date", "organization", "technical", "historical", "other"

If there are no checkable claims, return [].
"""


@dataclass
class Claim:
    claim: str
    source_line: str
    category: str


def extract_claims(script: str, client: GeminiClient | None = None) -> list[Claim]:
    client = client or GeminiClient()
    try:
        raw = client.complete_json(EXTRACT_PROMPT.format(script=script))
    except ModelUnavailable:
        raise
    if not isinstance(raw, list):
        raise ModelUnavailable(f"Expected a JSON array of claims, got: {type(raw)}")
    claims = []
    for item in raw:
        if not isinstance(item, dict) or "claim" not in item:
            continue
        claims.append(
            Claim(
                claim=str(item.get("claim", "")).strip(),
                source_line=str(item.get("source_line", "")).strip(),
                category=str(item.get("category", "other")).strip() or "other",
            )
        )
    return [c for c in claims if c.claim]
