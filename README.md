# Continuity Check

A fact-checking agent for solo video creators and small production teams,
built for [Agentic Cinema: The Blockbuster Hackathon](https://googlecloud.devpost.com/)
(Google Cloud + **Parallel** partner track).

Paste a script or scene excerpt in, get back every checkable factual claim
with a **CONFIRMED / CONTRADICTED / UNVERIFIABLE** verdict and cited sources
-- before you hit record, not after your comment section catches it.

## Inspiration

Solo video creators often have to be their own writer, editor, and
fact-checker. A wrong date, misidentified person, or shaky technical
explanation can slip through when research competes with getting a video
finished. We built Continuity Check to help catch those errors before
publishing, without needing a researcher on staff.

## What it does

1. **Accepts a script or scene excerpt** for a factual review.
2. **Extracts checkable claims** with Gemini, including statements about
   real people, places, dates, organizations, and technical or historical
   facts.
3. **Searches for evidence** by sending each claim to Parallel's Search API
   to retrieve live web sources.
4. **Returns cited verdicts** from Gemini: CONFIRMED, CONTRADICTED, or
   UNVERIFIABLE, so creators can see which claims have support, conflict
   with evidence, or remain unresolved.

## How we built it

Gemini via Vertex AI (`app/gemini_client.py`) extracts factual claims and
renders the final verdicts. Google ADK (`app/adk_orchestrator.py`) wires the
pipeline up as an agent, satisfying the hackathon's Agent Framework
requirement. Parallel's Search API (`app/parallel_client.py`, official
`parallel-web` SDK) grounds every verdict in live web evidence -- the model
is never asked to verdict from its own prior knowledge alone. FastAPI
(`app/main.py`) exposes it as a service, deployed on Cloud Run.

## Architecture

```
POST /check {"script": "..."}
        |
        v
  claim_extractor.py  --(Gemini / Vertex AI)-->  [claims]
        |
        v (per claim)
  parallel_client.py  --(Parallel Search API)-->  [live web evidence]
        |
        v
  fact_checker.py  --(Gemini / Vertex AI, grounded on evidence)-->  verdict
        |
        v
  [{"claim", "verdict", "reasoning", "confidence", "sources": [...]}]
```

`app/adk_orchestrator.py` wraps this same pipeline as a Google ADK
`BaseAgent` (`ContinuityCheckAgent`) so it can run inside ADK's
session/event runtime -- see that file's docstring for why the pipeline
logic lives once, in `fact_checker.py`, rather than being duplicated as ADK
`LlmAgent`s.

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>
export PARALLEL_API_KEY=<your-parallel-api-key>

uvicorn app.main:app --reload
curl -X POST localhost:8000/check \
  -H "Content-Type: application/json" \
  -d "{\"script\": \"$(cat data/sample_script.txt)\"}"
```

`GET /health` reports whether Vertex AI and Parallel Search are actually
reachable with the credentials in your environment -- check this before
recording the demo.

## Tests

```bash
python -m pytest tests/ -q
```

All tests run against fakes for `GeminiClient`/`ParallelClient` -- no
network calls, no GCP project or Parallel API key required. This is a
correctness/control-flow proof; `GET /health` and a manual `curl` against
`/check` are what prove the live integrations work.

## Deploy (Cloud Run)

```bash
gcloud run deploy continuity-check \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>,PARALLEL_API_KEY=<your-parallel-api-key>
```

See `SETUP_TODO.md` for the full turnkey checklist (this repo ships with no
credentials configured).

## Who it's for

Solo creators and small crews -- the person who writes, shoots, edits, and
posts alone, and doesn't have a researcher double-checking every date or
name before it ships.

## License

MIT -- see `LICENSE`.
