---
description: Full pre-race wind/tide/current brief for Bristol Harbor (text + visuals)
argument-hint: [date] [start-end], e.g. 2026-07-11 1100-1600
---

Produce a complete Bristol Harbor race brief using the `race-brief` skill.

Race window: **$ARGUMENTS**

If the date or start/end time is missing, ask me for it (windows vary per regatta —
don't assume). Then:

1. Run `fetch.py` then `plot.py` from the skill for the given date and window.
2. Read the resulting JSON and write the tactical prose brief per the skill's brief
   structure and Bristol Harbor / Hog Island local knowledge.
3. Show me the three visuals (tide, wind gradient, current).
