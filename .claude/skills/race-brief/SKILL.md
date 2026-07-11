---
name: race-brief
description: Gather hyper-local wind, tide, and tidal-current information for sailboat racing out of Bristol Harbor, RI — courses from the inner harbor out around Hog Island and Poppasquash Point into the East Passage. Produces a plain-English tactical brief plus tide, wind-gradient, and current visuals. Use before a race when asked for a "race brief", wind/tide/current picture, or conditions for Bristol Harbor / Hog Island / the East Passage.
---

# Bristol Harbor Race Brief

Assembles a pre-race conditions brief for racing out of **Bristol Harbor, RI**. All
data comes from **keyless public APIs** (NOAA CO-OPS, Open-Meteo, NWS, NDBC). The
brief covers the full course footprint: tight harbor races out around **Hog Island**
and **Poppasquash Point** into the **East Passage**, where current becomes a
first-order tactical factor.

## Workflow

1. **Determine the race window.** Ask the user for the date and start/end time if
   not given (e.g. "Saturday 1100–1600"). Windows vary per regatta — do not assume.
2. **Fetch** the data:
   ```
   .venv/bin/python .claude/skills/race-brief/fetch.py --date YYYY-MM-DD --start HH:MM --end HH:MM --out briefs/YYYY-MM-DD.json
   ```
   Set `NWS_USER_AGENT` in the environment (or a `.env`) to an identifying string
   with a contact email for the NWS API — never pass an email on the command line
   (a PII guard blocks it).
3. **Render** the visuals:
   ```
   .venv/bin/python .claude/skills/race-brief/plot.py briefs/YYYY-MM-DD.json
   ```
   This writes `briefs/YYYY-MM-DD_tide.png`, `_wind.png`, `_current.png`.
4. **Read the JSON** and **write the tactical prose brief** using the local
   knowledge below. Reference the three images so the user can view them.
5. **Save the brief to the journal.** Write the prose (steps 1–5 of *Brief
   structure* below — no environment/plumbing notes) to `briefs/YYYY-MM-DD.md`
   with front matter:
   ```
   ---
   title: "Sat 11 Jul 2026 · 11:00–16:00"
   headline: "<the one-line headline>"
   ---
   ## Wind
   ...
   ```
   The images are attached automatically — do not embed them in the markdown.
6. **Publish** the GitHub Pages journal, then commit + push:
   ```
   .venv/bin/python .claude/skills/race-brief/publish.py
   git add briefs/ docs/ && git commit -m "Brief: YYYY-MM-DD" && git push
   ```
   `publish.py` rebuilds the whole static site under `docs/` (served from
   `main` `/docs` at <https://jstockdi.github.io/starling/>). Days with a
   `.md` use its prose; days with only JSON are auto-summarised.

## Data sources & stations (see `stations.json`)

| Layer | Source | Station / fix |
|-------|--------|---------------|
| Tide height + hi/lo | NOAA CO-OPS `predictions` | Newport `8452660` (Narragansett Bay reference) |
| Current (harbor mouth) | NOAA CO-OPS `currents_predictions` | `ACT2171` Hog Island NW — flood 011°, ebb 199° |
| Current (East Passage) | NOAA CO-OPS `currents_predictions` | `ACT2156` Dyer Island W |
| Wind forecast (5 fixes) | Open-Meteo, exact lat/lon | inner harbor → Poppasquash → Hog mouth → S of Hog → East Passage |
| Live wind obs | NOAA CO-OPS `wind` | Conimicut Light `8452944` (nearest anemometer) |
| Marine text forecast | NWS `api.weather.gov` | zone `ANZ236` Narragansett Bay |
| Offshore context | NDBC | `44097` Block Island |

## Bristol Harbor / Hog Island local knowledge (for the prose brief)

Use these to interpret the numbers — this is what makes the brief read like a local:

- **SW sea breeze** (dominant summer racing wind): fills early–mid afternoon,
  entering over/around Hog Island from the East Passage. Expect **more pressure on
  the Hog Island side** than the Bristol town shore, a **right-hand bend and light
  patch under Poppasquash Point's lee**. Watch the fix gradient in the wind chart —
  if the outer fixes (Hog south / East Passage) are 3–5 kt stronger, send it out
  when the course allows.
- **Northerlies:** gradient-driven off the Bristol/Poppasquash land — shifty and
  puffy. Reward staying in phase with the shifts over committing to a side.
- **Poppasquash Point rounding:** casts a lee/shadow and bends the breeze on W/N
  winds — expect a soft patch and a shift right at the point.
- **Current — the tactical driver on the outer legs.** Flood sets **NNE up-bay
  (~011°)**, ebb sets **SSW down-bay (~199°)**. Strongest flow is through the
  **entrance gut at Hog Island Shoal** and off the island tips; near-slack inside
  the harbor itself. In the **East Passage** the channel-axis current is materially
  stronger (`ACT2156`). On an **ebb**, favour the shore to duck the SW channel flow
  on a beat; on a **flood** it pays to be in the channel going up-bay. Cross-check
  current slack times against the race window — a mid-race turn changes the
  favoured side.
- **Tide height** matters for shallow marks and committee-boat depth near the
  harbor edges; flag any low water inside the race window.

## Brief structure (what to output)

1. **One-line headline** — the story: wind direction/strength trend + current state.
2. **Wind** — race-window average and gust, the fix gradient (in vs out), expected
   shifts/sea-breeze timing. Cite live Conimicut obs vs. forecast.
3. **Current** — state and slack times at the harbor mouth and in the Passage; which
   side/lane it favours given the wind.
4. **Tide** — hi/lo times and any shallow-water caution.
5. **Tactical call** — where to start, favoured side, in-harbor vs. send-it-out.
6. Reference the three PNGs.

## Fallbacks

- Live obs stations occasionally go offline — the brief still works from forecasts;
  note the gap rather than failing.
- If the East Passage current station returns no data for the date, fall back to the
  harbor-mouth station and note the outer current is inferred.
