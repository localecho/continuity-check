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
from dataclasses import dataclass

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


class ModelUnavailable(RuntimeError):
    pass


@dataclass
class GeminiClient:
    project: str | None = None
    location: str = "us-central1"
    model_name: str = GEMINI_MODEL

    def __post_init__(self) -> None:
        self.project = self.project or os.environ.get("GOOGLE_CLOUD_PROJECT")

    def _model(self):
        if not self.project:
            raise ModelUnavailable(
                "GOOGLE_CLOUD_PROJECT is not set -- run `gcloud config set "
                "project <id>` and export GOOGLE_CLOUD_PROJECT, or pass "
                "project= explicitly."
            )
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
        except ImportError as exc:
            raise ModelUnavailable(
                "google-cloud-aiplatform is not installed -- "
                "`pip install -r requirements.txt`."
            ) from exc
        vertexai.init(project=self.project, location=self.location)
        return GenerativeModel(self.model_name)

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
        try:
            self.complete("Reply with the single word: ok", temperature=0.0)
            return True, f"Vertex AI reachable, project={self.project}, model={self.model_name}"
        except ModelUnavailable as exc:
            return False, str(exc)
