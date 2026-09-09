# Submit Continuity Check — 2026-09-09, deadline 2:00 PM PDT (Agentic Cinema, Parallel track)

Budget: ~25 minutes. Do these in order. Everything else is already done and verified.

## 0. Preflight (1 min, terminal)
    bash ~/projects/agentic-cinema-hackathon/tools/preflight.sh
Expect `4 PASS · 0 FAIL — SAFE TO SUBMIT`. If any FAIL, stop and fix that line first (revision to fall back to: `continuity-check-00007-4bj`).

## 1. Upload the video (≈10 min)
- File: `continuity-check-demo.mp4` in this folder (2:42, under the 3-min cap, English captions burned in).
- YouTube Studio → Create → Upload. Paste title / description / tags from `YOUTUBE_UPLOAD.md`. Visibility: Unlisted or Public.
- Optional: Subtitles → upload `continuity-check-demo.srt` (English).
- Wait for processing to finish, then copy the watch URL. Open it once in a private window to confirm it plays.

## 2. Devpost form (≈10 min)
Open https://agentic-cinema.devpost.com/ → your submission (sign in with the account tied to brighamhall@gmail.com).
Field values are in `DEVPOST_FORM_READY.md` (this folder). In short:
- Project name: **Continuity Check**
- Tagline: from the form sheet
- Project story: paste `DEVPOST.md` (this folder) — sections Inspiration → Links
- **Partner track: Parallel**
- Hosted project URL: https://continuity-check-231147782258.us-central1.run.app
- Repo URL: https://github.com/localecho/continuity-check
- Demo video URL: the YouTube URL from step 1 (also paste it into the "Links" block at the end of the project story)
- Built with: Google Cloud (Vertex AI / Gemini 2.5 Flash), Google ADK, Parallel Search API (parallel-web SDK), Python, FastAPI, Cloud Run, Docker, Lean 4
- Click **Submit**. Screenshot the confirmation.

## 3. After submit (2 min)
- Reply "submitted" here so the pipeline can mark the Dropbox folder 🟢 Submitted (100%) and update Linear TES-8811.
- Optional after judging: `gcloud run services update continuity-check --region us-central1 --min-instances 0` (removes the small idle charge).

## If something is wrong
- Video won't process: upload the same file to Vimeo instead; Devpost accepts either.
- Live URL down: `bash tools/preflight.sh` names the failing piece; redeploy with `cd ~/projects/agentic-cinema-hackathon && gcloud run deploy continuity-check --source . --region us-central1 --quiet`.
- Rules doubt: only Google Cloud AI + Parallel are called at runtime; Lean and the video tooling are not in the runtime path.
