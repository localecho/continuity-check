"""Parallel Search API client -- the hackathon's partner-track integration.

Wraps the official `parallel-web` SDK (per the hackathon's Parallel
requirements: the integration must be in code, not just named in a README).
Fail-closed the same way as gemini_client: no API key -> a named
ModelUnavailable-style error, never a silent empty result mistaken for "no
evidence found."
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import ClassVar

PREFLIGHT_TTL_S = int(os.environ.get("PREFLIGHT_TTL_S", "60"))


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
    _preflight_ttl_s: int = PREFLIGHT_TTL_S
    _sdk_client: object = field(default=None, init=False, repr=False, compare=False)
    _init_lock: object = field(default=None, init=False, repr=False, compare=False)

    # Class-level, process-wide: /health builds a FRESH ParallelClient() on every
    # hit (see app/main.py), so per-instance caching would never help.
    _preflight_cache: ClassVar[dict[str | None, tuple[float, tuple[bool, str], int]]] = {}
    _cache_lock: ClassVar[threading.Lock] = threading.Lock()

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("PARALLEL_API_KEY")
        import threading

        self._init_lock = threading.Lock()

    def _client(self):
        if not self.api_key:
            raise SearchUnavailable(
                "PARALLEL_API_KEY is not set -- get one at platform.parallel.ai "
                "and export PARALLEL_API_KEY."
            )
        # Cache the SDK client instance once per ParallelClient instead of
        # constructing it on every search() call.
        if self._sdk_client is not None:
            return self._sdk_client
        with self._init_lock:
            if self._sdk_client is not None:
                return self._sdk_client
            try:
                from parallel import Parallel
            except ImportError as exc:
                raise SearchUnavailable(
                    "parallel-web SDK is not installed -- `pip install parallel-web`."
                ) from exc
            self._sdk_client = Parallel(api_key=self.api_key)
            return self._sdk_client

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
        # Asymmetric TTL (gpt-6-astra cross-check, 2026-09-20) -- see gemini_client.py.
        key = self.api_key
        now = time.monotonic()
        with self._cache_lock:
            cached = self._preflight_cache.get(key)
            if cached is not None and now - cached[0] < cached[2]:
                return cached[1]
        try:
            results = self.search("Google Cloud Gemini Enterprise Agent Platform")
            result = True, f"Parallel Search reachable, {len(results)} result(s) returned"
            ttl = self._preflight_ttl_s
        except SearchUnavailable as exc:
            result = False, str(exc)
            ttl = min(self._preflight_ttl_s, 10)
        with self._cache_lock:
            self._preflight_cache[key] = (now, result, ttl)
        return result
