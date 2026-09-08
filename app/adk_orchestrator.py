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

import asyncio
import uuid
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
            "google-adk is not installed -- `pip install -r requirements.txt`."
        ) from exc
    return BaseAgent, InvocationContext, Event, types


def build_continuity_check_agent(
    name: str = "continuity_check",
    gemini: GeminiClient | None = None,
    parallel: ParallelClient | None = None,
    max_claims: int | None = None,
):
    """Factory so importing this module never requires google-adk to be
    installed -- only calling this function does. Accepts injectable
    clients (mirroring `fact_checker.check_script`) so this agent is
    unit-testable with fakes, same as the rest of the pipeline.
    """
    BaseAgent, InvocationContext, Event, types = _lazy_adk_imports()
    from google.adk.events import EventActions

    gemini = gemini or GeminiClient()
    parallel = parallel or ParallelClient()

    class ContinuityCheckAgent(BaseAgent):
        """Runs extract_claims -> Parallel Search -> Gemini verdict per
        claim, then writes the structured report into session state under
        `continuity_report` and yields one final Event with it as text.
        """

        def __init__(self, agent_name: str, gemini: GeminiClient, parallel: ParallelClient, max_claims: int | None):
            super().__init__(name=agent_name)
            self._gemini = gemini
            self._parallel = parallel
            self._max_claims = max_claims

        async def _run_async_impl(self, ctx: "InvocationContext") -> AsyncGenerator["Event", None]:
            script = ctx.session.state.get("script", "")
            # check_script is synchronous and blocking (it runs a
            # ThreadPoolExecutor internally) -- push it off the event loop
            # rather than block it for the whole 15-40s run.
            verdicts = await asyncio.to_thread(check_script, script, self._gemini, self._parallel, 5, self._max_claims)

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
            summary_lines = [f"Checked {len(report)} claim(s):"]
            for row in report:
                summary_lines.append(f"- [{row['verdict']}] {row['claim']}")
            summary = "\n".join(summary_lines) or "No checkable claims found."

            # State changes must go through actions.state_delta -- mutating
            # ctx.session.state directly does NOT persist back through the
            # session service (found live: get_session() afterward showed
            # only the original 'script' key, the direct-mutation write was
            # silently lost).
            yield Event(
                author=self.name,
                content=types.Content(role="model", parts=[types.Part(text=summary)]),
                actions=EventActions(state_delta={"continuity_report": report}),
            )

    return ContinuityCheckAgent(name, gemini, parallel, max_claims)


async def run_continuity_check_via_adk(
    script: str,
    gemini: GeminiClient | None = None,
    parallel: ParallelClient | None = None,
    max_claims: int | None = None,
) -> list[dict]:
    """Actually run the pipeline through the ADK runtime (InMemoryRunner +
    a real session) instead of just constructing the agent object -- this
    is what makes ADK a genuinely exercised code path rather than an
    unused module. Returns the same report shape as `check_script`, as
    plain dicts (already what the agent writes to session state).
    """
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent = build_continuity_check_agent(gemini=gemini, parallel=parallel, max_claims=max_claims)
    runner = InMemoryRunner(agent=agent, app_name="continuity_check")

    user_id = "demo-user"
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    await runner.session_service.create_session(
        app_name="continuity_check",
        user_id=user_id,
        session_id=session_id,
        state={"script": script},
    )

    async for _event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text="run continuity check")]),
    ):
        pass  # the agent writes its report into session state; no per-event handling needed

    session = await runner.session_service.get_session(
        app_name="continuity_check", user_id=user_id, session_id=session_id
    )
    return session.state.get("continuity_report", [])
