"""Gemini client for the Continuity Check agent.

Fail-closed by design: every method raises ModelUnavailable with a *named*
reason (missing project, missing package, missing credentials) instead of
crashing on import or silently falling back to a different provider. This
repo's Devpost track requires Google Cloud AI as the only model backend, so
there is no fallback provider to swap to -- if this raises, the demo is
broken and should say so loudly.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import ClassVar

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
PREFLIGHT_TTL_S = int(os.environ.get("PREFLIGHT_TTL_S", "60"))


class ModelUnavailable(RuntimeError):
    pass


@dataclass
class GeminiClient:
    project: str | None = None
    location: str = "us-central1"
    model_name: str = GEMINI_MODEL
    _preflight_ttl_s: int = PREFLIGHT_TTL_S
    _model_instance: object = field(default=None, init=False, repr=False, compare=False)
    _init_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)

    # Class-level, process-wide: /health builds a FRESH GeminiClient() on every hit
    # (see app/main.py), so per-instance caching would never help. Keyed by the
    # bits of state that actually change the answer (project + model), not by
    # object identity. Guarded by _cache_lock since Cloud Run can serve /health
    # concurrently.
    _preflight_cache: ClassVar[dict[tuple[str | None, str], tuple[float, tuple[bool, str], int]]] = {}
    _cache_lock: ClassVar[threading.Lock] = threading.Lock()

    def __post_init__(self) -> None:
        self.project = self.project or os.environ.get("GOOGLE_CLOUD_PROJECT")

    def _model(self):
        if not self.project:
            raise ModelUnavailable(
                "GOOGLE_CLOUD_PROJECT is not set -- run `gcloud config set "
                "project <id>` and export GOOGLE_CLOUD_PROJECT, or pass "
                "project= explicitly."
            )
        # vertexai.init() + GenerativeModel() do real credential/metadata
        # round-trips -- cache once per client instance instead of paying
        # that cost on every complete() call (measured: this was the
        # dominant cost in an 8-claim script taking 60-120s end-to-end).
        if self._model_instance is not None:
            return self._model_instance
        with self._init_lock:
            if self._model_instance is not None:
                return self._model_instance
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel
            except ImportError as exc:
                raise ModelUnavailable(
                    "google-cloud-aiplatform is not installed -- "
                    "`pip install -r requirements.txt`."
                ) from exc
            vertexai.init(project=self.project, location=self.location)
            self._model_instance = GenerativeModel(self.model_name)
            return self._model_instance

    def complete(self, prompt: str, *, temperature: float = 0.2) -> str:
        model = self._model()
        try:
            resp = model.generate_content(
                prompt,
                generation_config={"temperature": temperature},
            )
        except Exception as exc:  # noqa: BLE001 -- surfaced as ModelUnavailable
            raise ModelUnavailable(f"Vertex AI call failed: {exc}") from exc
        if not resp.candidates:
            raise ModelUnavailable("Vertex AI returned no candidates.")
        return resp.text

    def complete_json(self, prompt: str, *, temperature: float = 0.0) -> dict | list:
        raw = self.complete(prompt + "\n\nRespond with ONLY valid JSON, no prose.", temperature=temperature)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            cleaned = cleaned.removeprefix("json").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ModelUnavailable(f"Model did not return valid JSON: {exc}\nraw={raw!r}") from exc

    def preflight(self) -> tuple[bool, str]:
        # Asymmetric TTL (gpt-6-astra cross-check, 2026-09-20): a symmetric cache
        # would report a transient outage as unhealthy for the full TTL, same as
        # it would report healthy -- slow to notice recovery. Failures expire
        # fast; healthy results get the full TTL.
        key = (self.project, self.model_name)
        now = time.monotonic()
        with self._cache_lock:
            cached = self._preflight_cache.get(key)
            if cached is not None and now - cached[0] < cached[2]:
                return cached[1]
        try:
            self.complete("Reply with the single word: ok", temperature=0.0)
            result = True, f"Vertex AI reachable, project={self.project}, model={self.model_name}"
            ttl = self._preflight_ttl_s
        except ModelUnavailable as exc:
            result = False, str(exc)
            ttl = min(self._preflight_ttl_s, 10)
        with self._cache_lock:
            self._preflight_cache[key] = (now, result, ttl)
        return result
