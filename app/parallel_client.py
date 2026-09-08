"""Parallel Search API client -- the hackathon's partner-track integration.

Wraps the official `parallel-web` SDK (per the hackathon's Parallel
requirements: the integration must be in code, not just named in a README).
Fail-closed the same way as gemini_client: no API key -> a named
ModelUnavailable-style error, never a silent empty result mistaken for "no
evidence found."
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


class SearchUnavailable(RuntimeError):
    pass


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str


@dataclass
class ParallelClient:
    api_key: str | None = None
    max_results: int = 5

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("PARALLEL_API_KEY")

    def _client(self):
        if not self.api_key:
            raise SearchUnavailable(
                "PARALLEL_API_KEY is not set -- get one at platform.parallel.ai "
                "and export PARALLEL_API_KEY."
            )
        try:
            from parallel import Parallel
        except ImportError as exc:
            raise SearchUnavailable(
                "parallel-web SDK is not installed -- `pip install parallel-web`."
            ) from exc
        return Parallel(api_key=self.api_key)

    def search(self, query: str) -> list[SearchResult]:
        client = self._client()
        try:
            resp = client.search(objective=query, search_queries=[query])
        except Exception as exc:  # noqa: BLE001
            raise SearchUnavailable(f"Parallel Search API call failed: {exc}") from exc
        results = []
        for r in list(getattr(resp, "results", []) or [])[: self.max_results]:
            excerpts = getattr(r, "excerpts", None) or []
            results.append(
                SearchResult(
                    url=getattr(r, "url", ""),
                    title=getattr(r, "title", "") or "",
                    snippet=" ".join(excerpts)[:600] if excerpts else "",
                )
            )
        return results

    def preflight(self) -> tuple[bool, str]:
        try:
            results = self.search("Google Cloud Gemini Enterprise Agent Platform")
            return True, f"Parallel Search reachable, {len(results)} result(s) returned"
        except SearchUnavailable as exc:
            return False, str(exc)
