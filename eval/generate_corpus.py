"""Generates the >=10,000-example synthetic eval corpus for continuity-check.

Every fact-based example is derived directly from the structured tables in
eval/facts.py -- a TRUE claim states the table's real value, a FALSE claim
swaps in a different, plausible-but-wrong value drawn from the same table
(never a fabricated one). A subjective/opinion bucket exercises the
"no checkable claim" and "no evidence -> UNVERIFIABLE" control-flow paths.

Output: a list of dicts, each:
    claim            -- the exact claim text
    category          -- e.g. "elements_symbol", "capitals", "subjective"
    fact_key          -- the underlying fact's identifying subject (for grouping)
    ground_truth      -- "CONFIRMED" | "CONTRADICTED" | "UNVERIFIABLE" | "NO_CLAIM"
    evidence_snippet  -- text for the fake search result, or None (no evidence)
"""
from __future__ import annotations

import random

from eval import facts

RNG_SEED = 20260920  # deterministic corpus -- rerunning regenerates the same set


def _year_str(year: int) -> str:
    return f"{abs(year)} BC" if year < 0 else str(year)


CAPITALS_TEMPLATES = [
    "The capital of {subject} is {value}.",
    "{value} is the capital city of {subject}.",
    "According to official records, {subject}'s capital is {value}.",
    "Fact: {subject} has {value} as its capital.",
    "In the documentary, the narrator states that the capital of {subject} is {value}.",
    "Is {value} the capital of {subject}? Yes, that is correct.",
    "{subject}'s seat of government is located in {value}.",
    "Geography lesson: the capital city of {subject} is {value}.",
    "As shown on the map, {subject}'s capital is {value}.",
]

ELEMENT_SYMBOL_TEMPLATES = [
    "The chemical symbol for {subject} is {value}.",
    "{subject} is represented by the symbol {value} on the periodic table.",
    "In chemistry class, {value} is used to denote {subject}.",
    "Fact check: the element {subject} has the chemical symbol {value}.",
    "The periodic table lists {subject} under the symbol {value}.",
    "Is {value} the correct chemical symbol for {subject}? Yes.",
    "Scientists abbreviate {subject} as {value}.",
    "{subject}'s symbol on the periodic table is {value}.",
    "The lab report refers to {subject} by its symbol, {value}.",
]

ELEMENT_ATOMIC_TEMPLATES = [
    "The atomic number of {subject} is {value}.",
    "{subject} has atomic number {value} on the periodic table.",
    "In the periodic table, {subject} is element number {value}.",
    "Chemistry fact: {subject}'s atomic number is {value}.",
    "According to the periodic table, element {value} is {subject}.",
    "Is {subject} atomic number {value}? Yes, that's correct.",
    "{subject} sits at position {value} in the periodic table.",
    "The textbook states {subject}'s atomic number as {value}.",
    "Confirmed: {subject} has {value} protons in its nucleus.",
]

PRESIDENT_TEMPLATES = [
    "{subject} became President of the United States in {value}.",
    "{subject} took office as U.S. president in {value}.",
    "The historical record shows {subject} was inaugurated president in {value}.",
    "In {value}, {subject} began serving as President of the United States.",
    "History fact: {subject}'s presidency began in {value}.",
    "Is it true that {subject} became president in {value}? Yes.",
    "{subject} was sworn in as president in {value}.",
    "According to the archives, {subject} assumed the presidency in {value}.",
    "The documentary notes that {subject} took office in {value}.",
]

HISTORICAL_TEMPLATES = [
    "{subject} in {value}.",
    "{subject} in the year {value}.",
    "According to historical records, {subject} in {value}.",
    "History fact: {subject} in {value}.",
    "It is documented that {subject} in {value}.",
    "The event is dated to {value}: {subject}.",
    "Fact check this claim: {subject} in {value}.",
    "As recorded in encyclopedias, {subject} in {value}.",
    "The script's narrator states that {subject} in {value}.",
]

GEOGRAPHY_TEMPLATES = [
    "{subject} is {value}.",
    "According to geography references, {subject} is {value}.",
    "Fact: {subject} is {value}.",
    "Geography lesson: {subject} is {value}.",
    "It is well known that {subject} is {value}.",
    "Is it true that {subject} is {value}? Yes.",
    "{subject}, according to atlases, is {value}.",
    "Confirmed: {subject} is {value}.",
    "The travel guide states that {subject} is {value}.",
]

SCIENCE_TEMPLATES = [
    "{subject} is {value}.",
    "Science fact: {subject} is {value}.",
    "According to textbooks, {subject} is {value}.",
    "It is scientifically established that {subject} is {value}.",
    "Fact check this claim: {subject} is {value}.",
    "As taught in school, {subject} is {value}.",
    "Confirmed by scientists: {subject} is {value}.",
    "The documentary states that {subject} is {value}.",
    "Reference books list {subject} as {value}.",
]

SUBJECTIVE_TEMPLATES = [
    "{subject} is the best {noun} of all time.",
    "In my opinion, {subject} is better than most alternatives.",
    "I predict {subject} will become mainstream within the next decade.",
    "{subject} feels like the most exciting {noun} in recent memory.",
    "Everyone agrees that {subject} is overrated.",
    "{subject} will probably win next year's award.",
    "Honestly, {subject} is a bit disappointing compared to expectations.",
    "{subject} might be the greatest {noun} ever made, depending on who you ask.",
    "Some critics think {subject} is a masterpiece, others disagree.",
]


def _fact_examples(table, templates, fmt_value, category: str) -> list[dict]:
    """Given a fact table of (subject, value) pairs (value may need fmt_value
    to render), produce TRUE + FALSE examples across all templates."""
    out = []
    n = len(table)
    for i, row in enumerate(table):
        subject, value = row[0], row[1]
        value_str = fmt_value(value)
        # false value: a different entry's value, deterministic offset so it's
        # never accidentally the same value (guards against duplicate values,
        # e.g. two presidents/elements sharing a coincidental figure)
        for offset in (1, 2, 3):
            other = table[(i + offset) % n]
            false_value = fmt_value(other[1])
            if false_value != value_str:
                break
        for t_idx, template in enumerate(templates):
            true_claim = template.format(subject=subject, value=value_str)
            false_claim = template.format(subject=subject, value=false_value)
            out.append({
                "claim": true_claim, "category": category, "fact_key": str(subject),
                "ground_truth": "CONFIRMED",
                "evidence_snippet": f"{subject} -- verified value: {value_str}.",
            })
            out.append({
                "claim": false_claim, "category": category, "fact_key": str(subject),
                "ground_truth": "CONTRADICTED",
                "evidence_snippet": f"{subject} -- verified value: {value_str} (not {false_value}).",
            })
    return out


def build_corpus() -> list[dict]:
    examples: list[dict] = []

    examples += _fact_examples(facts.CAPITALS, CAPITALS_TEMPLATES, str, "capitals")
    examples += _fact_examples(
        [(name, sym) for name, sym, _ in facts.ELEMENTS], ELEMENT_SYMBOL_TEMPLATES, str, "elements_symbol"
    )
    examples += _fact_examples(
        [(name, num) for name, _, num in facts.ELEMENTS], ELEMENT_ATOMIC_TEMPLATES, str, "elements_atomic"
    )
    examples += _fact_examples(
        [(name, year) for name, year, _ in facts.PRESIDENTS], PRESIDENT_TEMPLATES, str, "presidents"
    )
    examples += _fact_examples(facts.HISTORICAL_EVENTS, HISTORICAL_TEMPLATES, _year_str, "historical")
    examples += _fact_examples(facts.GEOGRAPHY_FACTS, GEOGRAPHY_TEMPLATES, str, "geography")
    examples += _fact_examples(facts.SCIENCE_FACTS, SCIENCE_TEMPLATES, str, "science")

    # Subjective bucket: half "filtered at extraction" (NO_CLAIM), half
    # "extracted but no evidence returned" (UNVERIFIABLE via the Lean-spec
    # no-evidence short-circuit) -- both real control-flow branches.
    rng = random.Random(RNG_SEED)
    subj_pool = []
    for adj in facts.SUBJECTIVE_ADJECTIVES:
        for noun in facts.SUBJECTIVE_NOUNS:
            subj_pool.append((f"{adj} {noun}", noun))
    subj_idx = 0
    for subject, noun in subj_pool:
        for template in SUBJECTIVE_TEMPLATES:
            claim = template.format(subject=subject.capitalize(), noun=noun)
            no_claim = (subj_idx % 2 == 0)
            examples.append({
                "claim": claim, "category": "subjective", "fact_key": noun,
                "ground_truth": "NO_CLAIM" if no_claim else "UNVERIFIABLE",
                "evidence_snippet": None,
            })
            subj_idx += 1

    rng.shuffle(examples)
    for i, ex in enumerate(examples):
        ex["run_id"] = f"syn-{i:06d}"
    return examples


if __name__ == "__main__":
    corpus = build_corpus()
    print(f"corpus size: {len(corpus)}")
    from collections import Counter
    print(Counter(ex["category"] for ex in corpus))
    print(Counter(ex["ground_truth"] for ex in corpus))
