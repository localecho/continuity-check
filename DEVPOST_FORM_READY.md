# Devpost form — paste-ready (prepared 2026-09-08; deadline 2026-09-09 2:00pm PDT)

Form: https://agentic-cinema.devpost.com/ → "Enter a submission" (login: the Devpost account tied to brighamhall@gmail.com)

| Field | Value |
|---|---|
| Project name | Continuity Check |
| Tagline (≤ 200 chars) | Paste a script, get every factual claim back CONFIRMED / CONTRADICTED / UNVERIFIABLE with live cited sources — a Gemini + Parallel Search agent for solo creators, before you hit record. |
| Partner track | **Parallel** |
| Hosted project URL | https://continuity-check-231147782258.us-central1.run.app |
| Code repository URL | https://github.com/localecho/continuity-check (public, MIT visible in About) |
| Demo video URL | `<paste the YouTube/Vimeo URL after upload — file: demo-assets/continuity-check-demo.mp4>` |
| Built with | Google Cloud (Vertex AI / Gemini 2.5 Flash), Google ADK, Parallel Search API (parallel-web SDK), Python, FastAPI, Cloud Run, Docker, Lean 4 (proofs of the decision rules, not runtime) |
| Team | solo |

## Project story (paste the whole block below into the description field)

(Copy verbatim from `DEVPOST.md` in this repo — sections: Inspiration · What it does · How we built it · Challenges · Accomplishments · What we learned · Artist statement · What's next · Built with · Links. It is already the scrubbed version.)

## Pre-submit checklist (each verified 2026-09-08 unless marked)
- [x] Hosted URL live: `/health` OK, `/check-agent` returns verdicts with sources (revision 00007, min-instances 1)
- [x] Repo public, MIT detected in About
- [x] Runtime use of Google Cloud (Vertex AI Gemini) AND Parallel Search (official SDK) — imported and called in `app/gemini_client.py`, `app/parallel_client.py`
- [x] Google ADK agent exercised at runtime via `POST /check-agent`
- [ ] Demo video uploaded (public or unlisted), English or English subtitles, ≤ 3 min, shows the project functioning
- [ ] Devpost form submitted before 2:00pm PDT

## If asked "Did you use any AI tools not permitted by the rules?"
The shipped project's runtime calls only Vertex AI (Gemini) and Parallel Search. No other AI model, framework or API is imported or called at runtime (`grep -rn import app/` shows google-cloud-aiplatform, google-adk, parallel-web, fastapi, pydantic only).
