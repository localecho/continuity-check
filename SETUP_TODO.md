# Turnkey checklist -- the two things only you can do

Deadline: **2026-09-09, 2:00pm PDT**. Everything code-side is done and
tested (`python -m pytest tests/ -q` -- 5/5 passing, no credentials
required). What's left is entirely credentials + submission logistics.

This is the *same blocker* that killed the August "All Things Agentic"
hackathon three weeks ago (`~/projects/agentic-hackathon/DEPLOY_TOMORROW.md`:
"no GCP account exists yet"). As of this morning, `gcloud auth list` still
says "No credentialed accounts" on this machine. Do Step 0 first, today,
not the night before -- it's the one step I can't do for you.

## Step 0 -- GCP auth (~10 min, blocking everything else)

```bash
gcloud auth login
gcloud projects create continuity-check-bdl --name="Continuity Check"
gcloud config set project continuity-check-bdl
gcloud beta billing projects link continuity-check-bdl --billing-account=<YOUR_BILLING_ACCOUNT_ID>
gcloud services enable run.googleapis.com aiplatform.googleapis.com
export GOOGLE_CLOUD_PROJECT=continuity-check-bdl
```

If you don't have a billing account yet: sign up for the no-cost trial at
https://cloud.google.com/free, or use the hackathon's $100-credit form if
it's still open (the post says the deadline for that was August 31, so
likely closed -- the free trial is the fallback).

## Step 1 -- Parallel API key (~5 min)

Sign up at https://platform.parallel.ai, grab an API key, then:

```bash
export PARALLEL_API_KEY=<your-key>
```

## Step 2 -- confirm both are live

```bash
cd /Users/brighamhall/projects/agentic-cinema-hackathon
source .venv/bin/activate  # already created, has fastapi/pydantic
pip install -r requirements.txt
uvicorn app.main:app --reload &
curl localhost:8000/health
```

Expect `{"gemini": {"ok": true, ...}, "parallel": {"ok": true, ...}}`. If
either is `false`, the `detail` field names exactly what's missing --
`gemini_client.py` and `parallel_client.py` are written fail-closed on
purpose, so this should never silently look healthy when it isn't.

## Step 3 -- run the real demo call

```bash
curl -s -X POST localhost:8000/check \
  -H "Content-Type: application/json" \
  -d "{\"script\": \"$(cat data/sample_script.txt | sed 's/"/\\"/g')\"}" | python3 -m json.tool
```

Confirm the Berlin Wall claim in `data/sample_script.txt` comes back
CONTRADICTED and the Apollo 11 / Marie Curie claims come back CONFIRMED,
each with real source URLs -- that's the proof this isn't a mocked demo.

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
