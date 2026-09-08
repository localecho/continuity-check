/-!
# Continuity Check — the decision rules, specified and proven

The pipeline's *control flow* is fixed (extract → search → grade), but its model calls and web
evidence are not deterministic. What CAN be made exact is the small set of pure decision rules
around them. This file states those rules in Lean 4 (no Mathlib, `lean ContinuityCheck.lean`
checks it in seconds) and proves the properties the Python enforces and tests
(`tests/test_spec_conformance.py`):

1. `grade`: with no evidence, the verdict is UNVERIFIABLE — the model is never consulted.
2. `grade`: a model verdict is only ever *passed through*, never upgraded or invented.
3. `capClaims`: the number of graded claims never exceeds the cap (bounds the paid fan-out).
4. `pipeline`: report length = min(#claims, cap) — one row per checked claim, no more, no less.
5. `RateLimiter.allow`: admitting a request never puts a client over the per-window limit.

These are specifications of `app/fact_checker.py` and `app/main.py`, kept deliberately small so
the correspondence is readable by eye. Nothing in the runtime imports Lean; this is the proof,
the Python tests are the conformance check.
-/

namespace ContinuityCheck

inductive Verdict
  | confirmed
  | contradicted
  | unverifiable
  deriving DecidableEq, Repr

/-- One retrieved evidence item (url/title/excerpt collapsed to an opaque token here). -/
abbrev Evidence := String

/-- Rule 1+2: grading is a pure function of the evidence and the model's answer. -/
def grade (evidence : List Evidence) (model : Option Verdict) : Verdict :=
  if evidence.isEmpty then .unverifiable else model.getD .unverifiable

/-- With no evidence the verdict is UNVERIFIABLE whatever the model would have said. -/
theorem grade_no_evidence (m : Option Verdict) : grade [] m = .unverifiable := by
  simp [grade]

/-- A verdict is never invented: if the result is CONFIRMED or CONTRADICTED, the model said so
    AND there was evidence. -/
theorem grade_confirmed_sound (ev : List Evidence) (m : Option Verdict)
    (h : grade ev m = .confirmed) : ev ≠ [] ∧ m = some .confirmed := by
  unfold grade at h
  split at h
  · exact absurd h (by decide)
  · rename_i hne
    refine ⟨by simpa [List.isEmpty_iff] using hne, ?_⟩
    cases m with
    | none => simp at h
    | some v => cases v <;> simp_all

theorem grade_contradicted_sound (ev : List Evidence) (m : Option Verdict)
    (h : grade ev m = .contradicted) : ev ≠ [] ∧ m = some .contradicted := by
  unfold grade at h
  split at h
  · exact absurd h (by decide)
  · rename_i hne
    refine ⟨by simpa [List.isEmpty_iff] using hne, ?_⟩
    cases m with
    | none => simp at h
    | some v => cases v <;> simp_all

/-- Rule 3: the claim cap. -/
def capClaims (cap : Nat) (claims : List α) : List α := claims.take cap

theorem capClaims_le (cap : Nat) (claims : List α) : (capClaims cap claims).length ≤ cap := by
  rw [capClaims, List.length_take]
  exact Nat.min_le_left _ _

theorem capClaims_length (cap : Nat) (claims : List α) :
    (capClaims cap claims).length = min cap claims.length := by
  simp [capClaims, List.length_take]

/-- Rule 4: the fixed pipeline. `extract`, `search`, `model` are parameters — they stand for the
    non-deterministic Gemini/Parallel calls; the *shape* of the computation is what we prove. -/
def pipeline (cap : Nat) (extract : String → List String)
    (search : String → List Evidence) (model : String → List Evidence → Option Verdict)
    (script : String) : List (String × Verdict) :=
  (capClaims cap (extract script)).map fun c =>
    let ev := search c
    (c, grade ev (model c ev))

theorem pipeline_length (cap : Nat) extract search model (script : String) :
    (pipeline cap extract search model script).length = min cap (extract script).length := by
  simp [pipeline, capClaims_length]

/-- Every row's verdict obeys the grading rule for the evidence that row actually retrieved. -/
theorem pipeline_rows_graded (cap : Nat) extract search model (script : String) :
    ∀ row ∈ pipeline cap extract search model script,
      row.2 = grade (search row.1) (model row.1 (search row.1)) := by
  intro row hrow
  simp [pipeline, List.mem_map] at hrow
  obtain ⟨c, _, rfl⟩ := hrow
  rfl

/-- Rule 5: sliding-window rate limiter (mirrors `_RateLimiter.allow` in app/main.py). -/
structure Limiter where
  limit  : Nat
  window : Nat

/-- Hits inside the window at time `now`. -/
def Limiter.live (L : Limiter) (hits : List Nat) (now : Nat) : List Nat :=
  hits.filter fun t => now - t ≤ L.window

def Limiter.allow (L : Limiter) (hits : List Nat) (now : Nat) : Bool :=
  (L.live hits now).length < L.limit

/-- If a request is admitted and recorded, the client is still within the limit. -/
theorem Limiter.allow_keeps_bound (L : Limiter) (hits : List Nat) (now : Nat)
    (h : L.allow hits now = true) :
    (L.live (now :: hits) now).length ≤ L.limit := by
  unfold Limiter.allow at h
  simp only [decide_eq_true_eq] at h
  simp [Limiter.live] at *
  omega

/-- A client at the limit is refused. -/
theorem Limiter.refuses_at_limit (L : Limiter) (hits : List Nat) (now : Nat)
    (h : (L.live hits now).length = L.limit) : L.allow hits now = false := by
  unfold Limiter.allow
  simp [h]

end ContinuityCheck
