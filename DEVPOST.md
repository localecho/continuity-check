# Devpost submission draft -- Continuity Check

Paste this into the Devpost submission form once the checklist in
`SETUP_TODO.md` is done. Written with `openai/gpt-6-astra` via OpenRouter,
lightly edited for accuracy against the actual code.

**Track:** Google Cloud + Parallel

## Inspiration

Solo video creators often have to be their own writer, editor, and
fact-checker. A wrong date, misidentified person, or shaky technical
explanation can slip through when research competes with getting a video
finished. We built Continuity Check to help catch those errors before
publishing, without needing a researcher on staff.

## What it does

1. Accepts a script or scene excerpt for a factual review.
2. Extracts checkable claims with Gemini, including statements about real
   people, places, dates, organizations, and technical or historical facts.
3. Searches for evidence by sending each claim to Parallel's Search API to
   retrieve live web sources.
4. Returns cited verdicts from Gemini: CONFIRMED, CONTRADICTED, or
   UNVERIFIABLE, so creators can see which claims have support, conflict
   with evidence, or remain unresolved.

## How we built it

Gemini via Vertex AI extracts factual claims and evaluates the evidence
retrieved through the Parallel Search API. Google ADK (Agent Development
Kit) wires the extract -> search -> verdict pipeline into an agent
(`ContinuityCheckAgent`). FastAPI provides the application's API layer, and
the service is deployed on Cloud Run.

## Challenges we ran into

Getting a Google Cloud project authenticated and Vertex AI enabled was the
actual bottleneck, not the agent logic -- see `SETUP_TODO.md`. Keeping the
pipeline provider-agnostic in its unit tests (fakes for Gemini and Parallel,
zero network calls) meant the control-flow logic could be proven correct
before real credentials existed, so the live-credential step was purely
mechanical once it happened.

## Accomplishments we're proud of

A deterministic, multi-step agent where every verdict is traceable to a
specific cited source -- no hallucinated citations, and claims the search
can't confirm are explicitly labeled UNVERIFIABLE rather than guessed at.

## What we learned

Grounding an LLM's verdict strictly on retrieved evidence (not its own
training knowledge) is a small prompt change with an outsized trust payoff
for a fact-checking tool specifically.

## What's next for Continuity Check

A lightweight web UI for pasting a script directly (today it's an API);
batching claims per Parallel Search call to cut latency; a browser
extension that runs continuity checks on a Google Doc script draft inline.

## Built with

Google Cloud (Vertex AI / Gemini), Google ADK, Parallel Search API,
Python, FastAPI, Cloud Run, Docker.

## Links

- GitHub repo: `<fill in after `gh repo create` -- see SETUP_TODO.md>`
- Live demo URL: `<fill in after Cloud Run deploy>`
- Demo video: `<fill in after recording DEMO_SCRIPT.md>`
