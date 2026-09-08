# Demo video script (~3 min, matches Devpost's limit)

Drafted with `openai/gpt-6-astra` (pitch copy) and `moonshotai/kimi-k3`
(this beat sheet) via OpenRouter, then hand-edited to match the actual
sample data in `data/sample_script.txt` (Apollo 11 / Berlin Wall / Marie
Curie) instead of the model's invented placeholder claims -- record against
this file, not a paraphrase of it.

1. **0:00-0:08** -- Show a YouTube comments section full of corrections.
   "You said the Berlin Wall fell in '69. It fell in '89. Your comment
   section found out before you did."

2. **0:08-0:20** -- "Big channels have researchers. Solo creators have
   themselves. I built Continuity Check to close that gap." Title card on
   screen.

3. **0:20-0:45** -- "Continuity Check is an agent that reads your script,
   extracts every factual claim, and returns a verdict -- confirmed,
   contradicted, or unverifiable -- with cited sources, before you hit
   record."

4. **0:45-1:00** -- Show `data/sample_script.txt` in an editor: a 1969
   newsroom scene. Maya correctly cites the Apollo 11 landing date; Derek
   wrongly guesses the Berlin Wall fell "that same summer."

5. **1:00-1:15** -- "Four checkable claims in six lines of dialogue: Apollo
   11's landing date, the Berlin Wall date Derek gets wrong, and Marie
   Curie's two Nobel Prizes."

6. **1:15-1:30** -- Cut to terminal. "One call: `POST /check-agent` with
   the script text -- runs through a real Google ADK agent session." Run
   the curl command from the README.

7. **1:30-1:50** -- JSON response on screen. "Every claim comes back with a
   verdict, a reasoning line, and its sources."

8. **1:50-2:05** -- Highlight the CONTRADICTED verdict. "Derek's Berlin
   Wall claim: contradicted. It fell November 9th, 1989 -- twenty years
   later, not that summer -- with the citation that proves it."

9. **2:05-2:15** -- "Apollo 11 and Marie Curie's two Nobel Prizes: both
   confirmed, both cited."

10. **2:15-2:30** -- Show the architecture diagram from the README.
    "Gemini on Vertex AI extracts the claims and renders the verdicts.
    Google ADK runs the agent as `ContinuityCheckAgent`."

11. **2:30-2:45** -- "Every verdict is grounded in live web evidence from
    Parallel's Search API -- the model never verdicts from memory alone.
    Deployed on Cloud Run."

12. **2:45-3:00** -- "If you're a solo creator who's also your own
    fact-checker, this is your researcher. Code's on GitHub." GitHub link
    on screen.
