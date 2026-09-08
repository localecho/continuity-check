# Architecture

The control flow is **fixed**: the same steps in the same order on every request, no model choosing the next tool. The calls *inside* those steps (Gemini, Parallel Search) are live and not deterministic, so verdicts can change as the web does. The pure decision rules around those calls are specified and proven in [`verification/ContinuityCheck.lean`](verification/ContinuityCheck.lean) and checked against the Python by [`tests/test_spec_conformance.py`](tests/test_spec_conformance.py).

| Rule | Lean theorem | Python |
|---|---|---|
| No evidence ⇒ UNVERIFIABLE, model not consulted | `grade_no_evidence` | `fact_checker._check_one_claim` early return |
| A verdict is passed through, never invented | `grade_confirmed_sound`, `grade_contradicted_sound` | `ALLOWED_VERDICTS` collapse |
| Graded claims ≤ cap | `capClaims_le`, `pipeline_length` | `check_script(max_claims=25)` |
| Admitting a request never exceeds the window limit | `Limiter.allow_keeps_bound`, `Limiter.refuses_at_limit` | `_RateLimiter.allow` |

Check the spec yourself (Lean 4, no Mathlib, seconds): `cd verification && lean ContinuityCheck.lean`.

## UML

### Component diagram — what runs where

![component](docs/uml/component.png)

```mermaid
flowchart LR
    subgraph Client
      B[Browser demo page]
      C[curl / any HTTP client]
    end
    subgraph CloudRun[Google Cloud Run · continuity-check]
      API[FastAPI app.main]
      ADK[Google ADK runtime\nInMemoryRunner · Session]
      AG[ContinuityCheckAgent]
      FC[fact_checker · claim_extractor]
      GC[gemini_client]
      PC[parallel_client\nparallel-web SDK]
    end
    VX[(Vertex AI · Gemini 2.5 Flash)]
    PS[(Parallel Search API)]
    B --> API
    C --> API
    API --> ADK --> AG --> FC
    FC --> GC --> VX
    FC --> PC --> PS
```

### Sequence diagram — one POST /check-agent

![sequence](docs/uml/sequence.png)

```mermaid
sequenceDiagram
    autonumber
    actor Creator
    participant UI as Demo page (GET /)
    participant API as FastAPI (POST /check-agent)
    participant ADK as Google ADK InMemoryRunner + Session
    participant Agent as ContinuityCheckAgent (BaseAgent)
    participant G as Gemini 2.5 Flash (Vertex AI)
    participant P as Parallel Search API
    Creator->>UI: paste script, click Run
    UI->>API: {script}
    API->>API: validate: non-empty, ≤ 8000 chars, rate limit
    API->>ADK: create_session(state.script) · run_async
    ADK->>Agent: _run_async_impl(ctx)
    Agent->>G: EXTRACT_PROMPT(script)
    G-->>Agent: [claims] (capped at 25)
    loop per claim (5-wide thread pool)
        Agent->>P: search(claim)
        P-->>Agent: ≤5 results (url, title, excerpt)
        alt no evidence
            Agent->>Agent: UNVERIFIABLE (no model call)
        else evidence
            Agent->>G: VERDICT_PROMPT(claim, evidence)
            G-->>Agent: {verdict, reasoning, confidence}
        end
    end
    Agent-->>ADK: Event(state_delta.continuity_report)
    ADK-->>API: session.state.continuity_report
    API-->>UI: [VerdictOut]
    UI-->>Creator: cards: CONFIRMED / CONTRADICTED / UNVERIFIABLE + sources
```

### Activity diagram — the fixed control flow (green = the pipeline steps that never vary)

![activity](docs/uml/activity.png)

```mermaid
flowchart TD
    A([POST /check-agent]) --> B{script non-empty?}
    B -- no --> E400[400 empty]
    B -- yes --> C{≤ 8000 chars?}
    C -- no --> E413[413 too long]
    C -- yes --> D{under rate limit?}
    D -- no --> E429[429 rate limit]
    D -- yes --> X[Gemini: extract claims]
    X --> N{any claims?}
    N -- no --> R0([return empty list])
    N -- yes --> K[cap to 25 claims]
    K --> F[[for each claim, 5 in parallel]]
    F --> S[Parallel Search]
    S --> Q{evidence returned?}
    Q -- no --> U[UNVERIFIABLE, no model call]
    Q -- yes --> V[Gemini verdict grounded on evidence]
    V --> J[CONFIRMED / CONTRADICTED / UNVERIFIABLE + reasoning + sources]
    U --> M[collect report]
    J --> M
    M --> R([return report via ADK session state])
    classDef fixed fill:#e7f3ec,stroke:#2e7d4f;
    class X,K,F,S,V,M fixed
```

### Class diagram — the data that flows through

![class](docs/uml/class.png)

```mermaid
classDiagram
    class CheckRequest { +str script }
    class Claim { +str claim +str source_line +str category }
    class SearchResult { +str url +str title +str snippet }
    class ClaimVerdict { +Claim claim +str verdict +str reasoning +float confidence +List~SearchResult~ sources +str error }
    class VerdictOut { +str claim +str category +str source_line +str verdict +str reasoning +float confidence +List~SourceOut~ sources +str error }
    class GeminiClient { +project +model_name +complete(prompt) str +complete_json(prompt) dict|list +preflight() }
    class ParallelClient { +api_key +max_results +search(query) List~SearchResult~ +preflight() }
    class ContinuityCheckAgent { <<google.adk BaseAgent>> -_gemini -_parallel -_max_claims +_run_async_impl(ctx) AsyncGenerator~Event~ }
    class fact_checker { <<module>> +extract_claims(script, client) +check_script(script, gemini, parallel, max_workers, max_claims) }
    CheckRequest --> fact_checker : script
    fact_checker --> Claim : extracts
    fact_checker --> ClaimVerdict : produces
    ClaimVerdict o-- Claim
    ClaimVerdict o-- SearchResult
    ContinuityCheckAgent ..> fact_checker : runs
    ContinuityCheckAgent --> GeminiClient
    ContinuityCheckAgent --> ParallelClient
    ClaimVerdict ..> VerdictOut : serialised as
```

### State diagram — the life of one claim

![state](docs/uml/state.png)

```mermaid
stateDiagram-v2
    [*] --> Extracted : claim found in script
    Extracted --> Searched : Parallel Search
    Searched --> UNVERIFIABLE : no evidence (rule, no model)
    Searched --> Graded : evidence present → Gemini
    Graded --> CONFIRMED : evidence supports
    Graded --> CONTRADICTED : evidence conflicts
    Graded --> UNVERIFIABLE : evidence unclear
    Searched --> UNVERIFIABLE : search error (fail closed)
    Graded --> UNVERIFIABLE : model error (fail closed)
    CONFIRMED --> [*]
    CONTRADICTED --> [*]
    UNVERIFIABLE --> [*]
```

## Request path in prose

`POST /check-agent` → validate (non-empty, ≤ 8000 chars, rate limit) → Google ADK `InMemoryRunner` creates a session holding the script → `ContinuityCheckAgent._run_async_impl` → `check_script`: Gemini extracts claims (capped at 25) → for each claim, 5 in parallel: Parallel Search → no evidence ⇒ UNVERIFIABLE without a model call, else Gemini grades on that evidence only → the agent yields one Event whose `state_delta` carries the report → the endpoint returns it as `VerdictOut[]`.
