#!/usr/bin/env bash
# Submission-morning preflight: is the hosted project alive and correct RIGHT NOW?
# Usage: bash tools/preflight.sh      (exit 0 = safe to submit; anything else = read the line)
set -u
U="${CONTINUITY_CHECK_URL:-https://continuity-check-231147782258.us-central1.run.app}"
ok=0; fail=0
say() { printf '%s %s\n' "$1" "$2"; }
H=$(curl -s -m 60 -w '\n%{http_code} %{time_total}' "$U/health"); code=$(echo "$H" | tail -1 | cut -d' ' -f1); t=$(echo "$H" | tail -1 | cut -d' ' -f2)
if [ "$code" = "200" ] && echo "$H" | grep -q '"gemini":{"ok":true' && echo "$H" | grep -q '"parallel":{"ok":true'; then say "PASS" "/health 200 in ${t}s — Gemini + Parallel reachable"; ok=$((ok+1)); else say "FAIL" "/health -> $code: $(echo "$H" | head -1 | cut -c1-160)"; fail=$((fail+1)); fi
P=$(curl -s -m 20 "$U/"); if echo "$P" | grep -q 'id="script"' && echo "$P" | grep -q 'check-agent'; then say "PASS" "demo page serves the paste UI and calls /check-agent"; ok=$((ok+1)); else say "FAIL" "demo page missing textarea or /check-agent wiring"; fail=$((fail+1)); fi
R=$(curl -s -m 240 -X POST "$U/check-agent" -H 'Content-Type: application/json' -d '{"script":"MAYA: Apollo 11 landed on the Moon on July 20th, 1969. DEREK: The Berlin Wall came down that same summer, right?"}' -w '\n%{http_code} %{time_total}'); code=$(echo "$R" | tail -1 | cut -d' ' -f1); t=$(echo "$R" | tail -1 | cut -d' ' -f2)
if [ "$code" = "200" ] && echo "$R" | grep -q '"verdict":"CONTRADICTED"' && echo "$R" | grep -q 'Berlin'; then say "PASS" "/check-agent 200 in ${t}s — Berlin Wall claim CONTRADICTED with sources"; ok=$((ok+1)); else say "FAIL" "/check-agent -> $code in ${t}s: $(echo "$R" | head -1 | cut -c1-200)"; fail=$((fail+1)); fi
V=$(gh api repos/localecho/continuity-check -q '"\(.visibility) \(.license.spdx_id)"' 2>/dev/null); if [ "$V" = "public MIT" ]; then say "PASS" "repo public, MIT detected in About"; ok=$((ok+1)); else say "FAIL" "repo visibility/license: '$V' (want 'public MIT')"; fail=$((fail+1)); fi
REV=$(gcloud run services describe continuity-check --region us-central1 --format='value(status.latestReadyRevisionName)' 2>/dev/null); say "INFO" "serving revision ${REV:-unknown} (expected continuity-check-00007-4bj or later)"
printf '\n%d PASS · %d FAIL — %s\n' "$ok" "$fail" "$([ "$fail" = 0 ] && echo 'SAFE TO SUBMIT' || echo 'DO NOT SUBMIT YET — fix the FAIL line first')"
[ "$fail" = 0 ]
