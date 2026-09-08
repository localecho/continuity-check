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
(`ContinuityCheckAgent`), run for real on every request through
`google.adk.runners.InMemoryRunner` with a live session -- the demo page
calls this path (`POST /check-agent`), not a bypass. FastAPI provides the
application's API layer, and the service is deployed on Cloud Run.

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

## Artist statement

We built Continuity Check for the solo video creator who has no researcher
on staff. For Google Cloud's Agentic Cinema hackathon, in the Parallel
track, we wanted to make checking a script's factual claims a practical
part of making a video -- not a resource reserved for a large studio.

Our central design choice is restraint. Every verdict must be grounded
strictly in retrieved live web evidence, never the model's training
knowledge. We don't treat remembered information as a source or let the
model invent a citation. When a search or model call fails, the system
fails closed: it returns UNVERIFIABLE with the real reason, rather than
guessing.

We also chose a test that could expose failure. Our sample script has a
character misremember the Berlin Wall's fall date by twenty years. We want
the tool to catch a real error, not merely confirm easy facts. For us,
useful assistance means making uncertainty visible.

## What's next for Continuity Check

A lightweight paste-and-check UI beyond today's demo page; batching
multiple claims into fewer Parallel Search calls to cut latency further; a
browser extension that runs continuity checks on a Google Doc script draft
inline.

## Built with

Google Cloud (Vertex AI / Gemini), Google ADK, Parallel Search API,
Python, FastAPI, Cloud Run, Docker.

## Links

- GitHub repo: https://github.com/localecho/continuity-check
- Live demo URL: https://continuity-check-231147782258.us-central1.run.app
- Demo video: `<fill in after recording DEMO_SCRIPT.md>`
