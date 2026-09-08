# Turnkey checklist -- one thing left, now that Step 0 is done

Deadline: **2026-09-09, 2:00pm PDT**. Everything code-side is done and
tested (`python -m pytest tests/ -q` -- 5/5 passing, no credentials
required).

## Step 0 -- GCP auth -- DONE 2026-09-08

`gcloud auth login` + `gcloud auth application-default login` both
completed. Project `continuity-check-bdl` created, billed to the
BlueDuckLLC account, `run.googleapis.com` + `aiplatform.googleapis.com`
enabled. Live-verified: `GeminiClient().preflight()` reaches Vertex AI, and
a real `extract_claims()` call against `data/sample_script.txt` correctly
pulled out 8 claims including the deliberately-wrong Berlin Wall date.
`export GOOGLE_CLOUD_PROJECT=continuity-check-bdl` before running anything
(see `.env.example`).

## Step 1 -- Parallel API key -- DONE 2026-09-08

Key obtained, stored in `.env` (gitignored, chmod 600) -- never committed.
`ParallelClient().preflight()` confirmed reachable.

## Step 2 -- confirm both are live -- DONE 2026-09-08

`GET /health` path live-verified via direct calls to both clients (not
just the endpoint): Gemini and Parallel both reachable.

## Step 3 -- run the real demo call -- DONE 2026-09-08

Ran `check_script()` directly (equivalent to `POST /check`) against the
real `data/sample_script.txt`. Confirmed live: the Berlin Wall claim comes
back CONTRADICTED (cites en.wikipedia.org/wiki/Fall_of_the_Berlin_Wall +
history.state.gov), and Apollo 11 / Neil Armstrong / Marie Curie all come
back CONFIRMED with real NASA / Wikipedia / Nobel Prize source URLs. This
is the hero shot for the demo video -- not a mocked response.

To re-run it yourself via the actual HTTP endpoint:

```bash
cd /Users/brighamhall/projects/agentic-cinema-hackathon
source .venv/bin/activate
set -a; source .env; set +a
uvicorn app.main:app --reload &
curl -s -X POST localhost:8000/check \
  -H "Content-Type: application/json" \
  -d "{\"script\": \"$(cat data/sample_script.txt | sed 's/"/\\"/g')\"}" | python3 -m json.tool
```

## Step 4 -- Cloud Run deploy (~10 min)

```bash
gcloud run deploy continuity-check \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=continuity-check-bdl,PARALLEL_API_KEY=$PARALLEL_API_KEY
```

Note the printed service URL -- that's the "hosted project URL" Devpost
wants.

## Step 5 -- public repo

```bash
cd /Users/brighamhall/projects/agentic-cinema-hackathon
git add -A
git commit -m "Continuity Check: Gemini + Parallel fact-checking agent for Agentic Cinema hackathon"
gh repo create localecho/continuity-check --public --source=. --push
```

(Swap `localecho` for whichever GitHub account/org you want the entry
under.) LICENSE (MIT) is already in the repo -- satisfies the "complete
open-source license" requirement.

## Step 6 -- record the demo video

Script is in `DEMO_SCRIPT.md`, timed to the ~3-minute limit and built
around `data/sample_script.txt` so what's on screen matches what's in the
repo. Screen-record the terminal + JSON response per the script's beats,
upload to YouTube/Vimeo (unlisted is fine, Devpost just needs a URL).

## Step 7 -- Devpost submission form

Copy `DEVPOST.md` in. Fields it doesn't cover: hosted project URL (Step 4),
repo URL (Step 5), demo video URL (Step 6), partner track = **Parallel**.

## What's NOT done and why that's fine

- No web UI -- it's an API by design; the demo shows curl + JSON, which is
  enough to prove the agent works and keeps the surface area small for a
  same-day build.
- Firestore/persistence -- not needed, each `/check` call is stateless.
- Batched Parallel calls -- each claim gets its own search call today;
  fine for a script-length input, named as a "what's next" in DEVPOST.md
  rather than silently glossed over.
