"""Runs the synthetic eval corpus through the REAL app.fact_checker.check_script
pipeline (real claim_extractor + fact_checker control flow, real ADK-shaped
Claim/ClaimVerdict dataclasses) with the GeminiClient/ParallelClient network
boundary swapped for controlled fakes -- same pattern as tests/test_fact_checker.py
(zero network calls, zero credentials, proves control flow + parsing robustness
at scale, not live-API accuracy).

Deliberately injects response-format noise (whitespace, case, malformed
confidence types, junk extraction entries) at real-world-plausible rates so
the harness can catch genuine parsing/normalization bugs, not just replay a
trivial "model always answers cleanly" happy path.

Usage:
    .venv/bin/python -m eval.run_eval [--limit N] [--db PATH]
"""
from __future__ import annotations

import argparse
import random
import sqlite3
import time
from datetime import datetime, timezone

from app.fact_checker import check_script
from app.gemini_client import ModelUnavailable
from app.parallel_client import SearchResult, SearchUnavailable
from eval.generate_corpus import build_corpus

NOISE_SEED = 8675309
DEFAULT_DB = "data/eval_runs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id           TEXT PRIMARY KEY,
    run_type         TEXT NOT NULL,      -- 'synthetic' | 'live'
    category         TEXT NOT NULL,
    fact_key         TEXT,
    claim            TEXT NOT NULL,
    ground_truth     TEXT NOT NULL,
    actual_verdict   TEXT,
    matched          INTEGER NOT NULL,   -- 1/0
    reasoning        TEXT,
    confidence       REAL,
    num_sources      INTEGER,
    noise_type       TEXT,
    extraction_noise INTEGER NOT NULL DEFAULT 0,
    error            TEXT,
    latency_ms       REAL,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_run_type ON runs(run_type);
CREATE INDEX IF NOT EXISTS idx_runs_category ON runs(category);
CREATE INDEX IF NOT EXISTS idx_runs_matched ON runs(matched);
"""


class FakeGemini:
    """Ordered canned-JSON queue -- same pattern as tests/test_fact_checker.py."""

    def __init__(self, json_responses: list):
        self._responses = list(json_responses)
        self.calls: list[str] = []

    def complete_json(self, prompt: str, *, temperature: float = 0.0):
        self.calls.append(prompt)
        if not self._responses:
            raise ModelUnavailable("FakeGemini ran out of canned responses")
        return self._responses.pop(0)


class FakeParallel:
    def __init__(self, results_by_query: dict[str, list[SearchResult]] | None = None):
        self._results = results_by_query or {}
        self.queries: list[str] = []

    def search(self, query: str):
        self.queries.append(query)
        return self._results.get(query, [])


def _noise_pick(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.70:
        return "clean"
    if r < 0.80:
        return "whitespace"
    if r < 0.90:
        return "lowercase"
    if r < 0.95:
        return "confidence_string_numeric"
    return "confidence_non_numeric"


def _apply_noise(verdict_label: str, noise: str, rng: random.Random) -> dict:
    verdict_str = verdict_label
    confidence = round(rng.uniform(0.5, 0.99), 2)
    if noise == "whitespace":
        verdict_str = f"  {verdict_label}  "
    elif noise == "lowercase":
        verdict_str = verdict_label.lower()
    elif noise == "confidence_string_numeric":
        confidence = str(confidence)
    elif noise == "confidence_non_numeric":
        confidence = rng.choice(["high", "very confident", "n/a", ""])
    return {
        "verdict": verdict_str,
        "reasoning": f"Based on source [1], the claim is {verdict_label.lower()}.",
        "confidence": confidence,
    }


def _build_extraction_response(example: dict, add_junk: bool, rng: random.Random) -> list:
    if example["ground_truth"] == "NO_CLAIM":
        return []
    entries = [{
        "claim": example["claim"],
        "source_line": "L1",
        "category": example["category"],
    }]
    if add_junk:
        junk_variants = [
            {"not_a_claim_field": "junk"},
            {"claim": "", "source_line": "L2", "category": "other"},
            "not even a dict",
        ]
        entries.append(rng.choice(junk_variants))
    return entries


def run_one(example: dict, rng: random.Random) -> dict:
    add_junk = example["ground_truth"] in ("CONFIRMED", "CONTRADICTED") and rng.random() < 0.05
    extraction_response = _build_extraction_response(example, add_junk, rng)

    gemini_responses = [extraction_response]
    parallel_results = {}
    noise_type = None

    needs_verdict_call = example["ground_truth"] in ("CONFIRMED", "CONTRADICTED")
    if needs_verdict_call:
        noise_type = _noise_pick(rng)
        gemini_responses.append(_apply_noise(example["ground_truth"], noise_type, rng))
        parallel_results[example["claim"]] = [
            SearchResult(url="https://example-source.test/fact", title="Reference",
                         snippet=example["evidence_snippet"])
        ]
    # UNVERIFIABLE (subjective, no evidence): parallel_results stays empty for
    # this claim -> real code's no-evidence short-circuit fires, gemini's
    # verdict response is never consumed (only the extraction response queued).
    # NO_CLAIM: extraction returns [], check_script returns [] before ever
    # touching parallel/gemini again.

    gemini = FakeGemini(gemini_responses)
    parallel = FakeParallel(parallel_results)

    t0 = time.perf_counter()
    error = None
    actual_verdict = None
    reasoning = None
    confidence = None
    num_sources = None
    matched = 0
    try:
        results = check_script(example["claim"], gemini=gemini, parallel=parallel, max_workers=1)
        if example["ground_truth"] == "NO_CLAIM":
            matched = 1 if results == [] else 0
            actual_verdict = "NO_CLAIM" if results == [] else f"UNEXPECTED({len(results)} claims)"
        else:
            if len(results) != 1:
                actual_verdict = f"UNEXPECTED({len(results)} claims)"
            else:
                v = results[0]
                actual_verdict = v.verdict
                reasoning = v.reasoning
                confidence = v.confidence
                num_sources = len(v.sources)
                matched = 1 if actual_verdict == example["ground_truth"] else 0
    except Exception as exc:  # noqa: BLE001 -- the harness must survive a real crash to report it
        error = f"{type(exc).__name__}: {exc}"
        actual_verdict = "ERROR"
        matched = 0
    latency_ms = (time.perf_counter() - t0) * 1000

    return {
        "run_id": example["run_id"],
        "run_type": "synthetic",
        "category": example["category"],
        "fact_key": example["fact_key"],
        "claim": example["claim"],
        "ground_truth": example["ground_truth"],
        "actual_verdict": actual_verdict,
        "matched": matched,
        "reasoning": reasoning,
        "confidence": confidence,
        "num_sources": num_sources,
        "noise_type": noise_type,
        "extraction_noise": 1 if add_junk else 0,
        "error": error,
        "latency_ms": latency_ms,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--db", default=DEFAULT_DB)
    args = ap.parse_args()

    corpus = build_corpus()
    if args.limit:
        corpus = corpus[: args.limit]

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM runs WHERE run_type = 'synthetic'")

    rng = random.Random(NOISE_SEED)
    rows = []
    t0 = time.perf_counter()
    for example in corpus:
        rows.append(run_one(example, rng))
        if len(rows) >= 500:
            _flush(conn, rows)
            rows = []
    _flush(conn, rows)
    conn.commit()
    elapsed = time.perf_counter() - t0

    total, matched, errors = conn.execute(
        "SELECT COUNT(*), SUM(matched), SUM(CASE WHEN actual_verdict='ERROR' THEN 1 ELSE 0 END) "
        "FROM runs WHERE run_type='synthetic'"
    ).fetchone()
    print(f"ran {total} synthetic examples in {elapsed:.1f}s "
          f"({total / elapsed:.0f}/s) -> matched {matched}/{total} ({100*matched/total:.2f}%), "
          f"{errors} error(s)")
    print("\nconfusion by category (mismatches only):")
    for row in conn.execute(
        "SELECT category, ground_truth, actual_verdict, COUNT(*) c FROM runs "
        "WHERE run_type='synthetic' AND matched=0 GROUP BY category, ground_truth, actual_verdict "
        "ORDER BY c DESC LIMIT 20"
    ):
        print(f"  {row[0]:16s} {row[1]:12s} -> {row[2]:20s}  x{row[3]}")
    print("\nby noise_type (mismatches only):")
    for row in conn.execute(
        "SELECT noise_type, COUNT(*) c FROM runs WHERE run_type='synthetic' AND matched=0 "
        "GROUP BY noise_type ORDER BY c DESC"
    ):
        print(f"  {row[0]}: {row[1]}")
    conn.close()


def _flush(conn, rows):
    if not rows:
        return
    conn.executemany(
        "INSERT OR REPLACE INTO runs "
        "(run_id, run_type, category, fact_key, claim, ground_truth, actual_verdict, matched, "
        " reasoning, confidence, num_sources, noise_type, extraction_noise, error, latency_ms, created_at) "
        "VALUES (:run_id, :run_type, :category, :fact_key, :claim, :ground_truth, :actual_verdict, "
        " :matched, :reasoning, :confidence, :num_sources, :noise_type, :extraction_noise, :error, "
        " :latency_ms, :created_at)",
        rows,
    )


if __name__ == "__main__":
    main()
