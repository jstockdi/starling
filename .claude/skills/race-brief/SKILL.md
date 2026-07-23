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

1. **Determine the race window and course.** Ask for the date and start/end time
   if not given (e.g. "Saturday 1100–1600"). Windows vary per regatta — do not
   assume. Also ask the **course** if the user knows it; it is usually one of the
   four archetypes in *Course & language conventions* below. If the course is
   unknown, keep the tactical call **course-agnostic** — describe where the
   pressure, shifts, and current live geographically and let the sailor map it
   onto whatever gets set.
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
7. **Verify after the race** (a few hours past the finish, once CO-OPS has logged
   the window):
   ```
   .venv/bin/python .claude/skills/race-brief/verify.py --date YYYY-MM-DD
   ```
   Re-fetches the real race-window wind, scores each anemometer against its nearest
   forecast fix (speed ratio + direction error), writes `briefs/<date>_verify.json`,
   appends a `## Verification` scorecard to `briefs/<date>.md`, and republishes.
   In CI the **Verify race brief** workflow runs this automatically at 10:30 PM EDT
   Wednesday. On 2026-07-22 it scored `MISS` (actual ~13 kt vs forecast ~6.7 kt,
   2.0×) — the accountability loop that catches a bust like that one.

## Brief kinds: race vs. weekend daysail

Two products share this pipeline (`weekly_brief.py`, selected by `RACE_KIND`):

- **`race`** (default) — the tactical Wed-evening race brief documented above.
  Window 18:00–20:00. Sections: Wind / Current / Tide / Tactical call.
- **`weekend`** — a friendly recreational **daysail** forecast, not a race brief.
  Window 10:00–18:00, run 7 AM EDT Sat & Sun. Warm, plain-English tone; **no race
  tactics** (no course archetypes, start lines, or favoured side). Sections:
  *The day* (is it a good day + character: mellow / spirited / marginal) / *Wind*
  (fill timing, best window, soft spots) / *Tide & current* (hi-lo, shallow
  cautions, chop heads-up) / *Good to know* (comfort, weather, when to head out).
  Reuses the same local knowledge below for **where** the wind and current live.

  Manual run:
  ```
  RACE_KIND=weekend RACE_DATE=2026-07-25 \
    .venv/bin/python .claude/skills/race-brief/weekly_brief.py
  ```
  The `weekend` brief writes `kind: weekend` into its front matter, so the journal
  labels it **Daysail** instead of **Race window**.

## Course & language conventions

**Speak in compass, never boat-relative.** The course orientation changes race to
race, so "left/right side" is meaningless in a brief. Anchor every tactical call
to **compass bearings and named landmarks**:

- **Poppasquash Neck** is the **west** shore of the harbor; the **Bristol
  waterfront** is the **east** shore. The harbor opens **south** to **Hog Island**;
  the **East Passage** runs **SSW** seaward beyond it.
- Wind shifts: use **veer** (clockwise) / **back** (counter-clockwise), and always
  gloss the endpoint — "veers toward the E", not "shifts right".
- Current: name the **set bearing** — flood ~**011° (NNE, up-bay/into the harbor)**,
  ebb ~**199° (SSW, down-bay/seaward)**.
- Pressure: name the **fix or shore** it sits on — "more breeze to the S/seaward
  (Hog Island, East Passage)", "light under the western Poppasquash shore".

**The course is not known ahead of time.** Brief the geography, then note how it
maps onto the four common courses (state which lens you are using, or stay
course-agnostic):

- **N–S windward/leeward** — beats run roughly N and S; the **E–W pressure/shear
  gradient** across the fixes is the cross-course lever.
- **J-hook out of Bristol Harbor** — starts in the near-slack inner harbor, hooks
  out around a harbor-mouth mark into the stronger mouth/Passage current; the turn
  flips the favored edge, so call it by leg.
- **Around Hog Island** — a lap crosses all four current quadrants; the set
  reverses leg-by-leg, so give each leg its own compass call.
- **Out-and-back (light air)** — a reach/run S toward the East Passage and back;
  the **pressure gradient dominates** (get to the seaward breeze), current secondary.

## Data sources & stations (see `stations.json`)

| Layer | Source | Station / fix |
|-------|--------|---------------|
| Tide height + hi/lo | NOAA CO-OPS `predictions` | Newport `8452660` (Narragansett Bay reference) |
| Current (harbor mouth) | NOAA CO-OPS `currents_predictions` | `ACT2171` Hog Island NW — flood 011°, ebb 199° |
| Current (East Passage) | NOAA CO-OPS `currents_predictions` | `ACT2156` Dyer Island W |
| Wind forecast (5 fixes) | Open-Meteo, 3 models per fix | inner harbor → Poppasquash → Hog mouth → S of Hog → East Passage |
| Live wind obs | NOAA CO-OPS `wind` | Newport `8452660` (Passage mouth) + Conimicut Light `8452944` (up-bay) |
| Marine text forecast | NWS `api.weather.gov` | zone `ANZ236` Narragansett Bay |
| Offshore context | NDBC `44097` | Block Island — the southerly ocean signal |

**Wind model & confidence.** Each fix pulls **HRRR (3 km, primary), ECMWF, and GFS**.
HRRR drives the numbers (it resolves the sea breeze the old best_match blend smeared
out); ECMWF + GFS give a home-grown spread. Read two derived signals before writing
the wind section:

- **`summary.spread` / `summary.model_avgs`** per fix — kt between the strongest and
  weakest model over the window. Small (≲2 kt) → state the strength confidently; large
  (≳4 kt) → hedge ("models split 5–13 kt; treat strength as low-confidence").
- **`wind_check`** — the live anemometer vs the model over the hours both cover. If it
  says obs are **materially stronger/weaker**, trust the obs regime over the model
  narrative. (On 2026-07-22 the model called 6–7 kt easing while Conimicut already read
  18 kt; the obs were right — a solid 12–16 kt held the whole window.)

## Bristol Harbor / Hog Island local knowledge (for the prose brief)

Use these to interpret the numbers — this is what makes the brief read like a local:

- **SW sea breeze** (dominant summer racing wind): fills early–mid afternoon,
  entering from the **S/SSW** up the East Passage over/around Hog Island. Expect
  **more pressure to the S/seaward (Hog Island, East Passage)** than up inside the
  harbor, the breeze **veering (toward the W/SW) as it fills**, and a **light patch
  under the western Poppasquash shore**. Watch the fix gradient in the wind chart —
  if the outer/seaward fixes (Hog south / East Passage) are 3–5 kt stronger, work
  toward them when the course allows.
- **Northerlies:** gradient-driven off the Bristol/Poppasquash land to the **N** —
  shifty and puffy. Reward staying in phase with the veers/backs over committing to
  one side of the course.
- **Poppasquash Neck (west shore):** casts a lee to its **E/SE** on W/N winds —
  expect a soft patch and the breeze **veering (toward the E/S)** as you clear its
  shadow.
- **Current — the tactical driver on the seaward legs.** Flood sets **NNE up-bay
  (~011°, into the harbor)**, ebb sets **SSW down-bay (~199°, seaward)**. Strongest
  flow is through the **entrance gut at Hog Island Shoal** and off the island tips;
  near-slack inside the harbor itself. In the **East Passage** the channel-axis
  current is materially stronger (`ACT2156`). On an **ebb**, stay out of the
  mid-channel SSW set — work the shallower shore edges; on a **flood**, ride the
  channel when heading up-bay (N). Cross-check current slack times against the race
  window — a mid-race turn reverses the favored lane.
- **Tide height** matters for shallow marks and committee-boat depth near the
  harbor edges; flag any low water inside the race window.

## Brief structure (what to output)

1. **One-line headline** — the story: wind direction/strength trend + current state.
2. **Wind** — race-window average and gust, the fix gradient (in vs out), expected
   shifts/sea-breeze timing. Cite the live anemometers (Newport, Conimicut) vs.
   forecast, and let `wind_check` + model `spread` set your confidence (see *Wind
   model & confidence* above).
3. **Current** — state and slack times at the harbor mouth and in the Passage; the
   set bearing and which **compass lane/shore** it favours given the wind.
4. **Tide** — hi/lo times and any shallow-water caution.
5. **Tactical call** — expressed in **compass + landmarks** (never left/right): the
   favoured **compass side / shore**, pressure vs. current trade-off, in-harbor vs.
   seaward. Give the call **per course archetype** if the course is known, else
   course-agnostic.
6. Reference the three PNGs.

## Fallbacks

- Live obs stations occasionally go offline — the brief still works from forecasts;
  note the gap rather than failing.
- If the East Passage current station returns no data for the date, fall back to the
  harbor-mouth station and note the outer current is inferred.
