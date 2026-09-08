"""Google ADK wiring -- the hackathon's "Agent Framework" requirement.

ADK supports custom `BaseAgent` subclasses with imperative control flow
(see https://adk.dev/agents/custom-agents/), which is what this file uses:
`ContinuityCheckAgent` drives the same extract -> search -> verdict pipeline
as `app.fact_checker.check_script`, but as an ADK agent so it can run inside
ADK's session/event runtime and be deployed via the Gemini Enterprise Agent
Platform / Agent Starter Pack tooling rather than only as a bare FastAPI call.

Kept as a thin wrapper on purpose: the pipeline logic lives once, in
`fact_checker.py`, and is unit-testable without spinning up an ADK
InvocationContext. This file is the integration seam, not a second
implementation.
"""
from __future__ import annotations

from typing import AsyncGenerator

from app.fact_checker import check_script
from app.gemini_client import GeminiClient
from app.parallel_client import ParallelClient


def _lazy_adk_imports():
    try:
        from google.adk.agents import BaseAgent
        from google.adk.agents.invocation_context import InvocationContext
        from google.adk.events import Event
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - exercised only without adk installed
        raise RuntimeError(
            "google-adk is not installed -- `pip install -r requirements-adk.txt`."
        ) from exc
    return BaseAgent, InvocationContext, Event, types


def build_continuity_check_agent(name: str = "continuity_check"):
    """Factory so importing this module never requires google-adk to be
    installed -- only calling this function does. Keeps `fact_checker`
    testable in the default (ADK-less) CI environment.
    """
    BaseAgent, InvocationContext, Event, types = _lazy_adk_imports()

    class ContinuityCheckAgent(BaseAgent):
        """Runs extract_claims -> Parallel Search -> Gemini verdict per
        claim, then writes the structured report into session state under
        `continuity_report` and yields one final Event with it as text.
        """

        def __init__(self, agent_name: str, gemini: GeminiClient, parallel: ParallelClient):
            super().__init__(name=agent_name)
            self._gemini = gemini
            self._parallel = parallel

        async def _run_async_impl(self, ctx: "InvocationContext") -> AsyncGenerator["Event", None]:
            script = ctx.session.state.get("script", "")
            verdicts = check_script(script, gemini=self._gemini, parallel=self._parallel)

            report = [
                {
                    "claim": v.claim.claim,
                    "category": v.claim.category,
                    "source_line": v.claim.source_line,
                    "verdict": v.verdict,
                    "reasoning": v.reasoning,
                    "confidence": v.confidence,
                    "sources": [{"title": s.title, "url": s.url} for s in v.sources],
                    "error": v.error,
                }
                for v in verdicts
            ]
            ctx.session.state["continuity_report"] = report

            summary_lines = [f"Checked {len(report)} claim(s):"]
            for row in report:
                summary_lines.append(f"- [{row['verdict']}] {row['claim']}")
            summary = "\n".join(summary_lines) or "No checkable claims found."

            yield Event(
                author=self.name,
                content=types.Content(role="model", parts=[types.Part(text=summary)]),
            )

    return ContinuityCheckAgent(name, GeminiClient(), ParallelClient())
