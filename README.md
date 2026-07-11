# starling

Hyper-local **wind, tide, and tidal-current race briefs** for sailboat racing out of
**Bristol Harbor, RI** — courses from the inner harbor out around Hog Island and
Poppasquash Point into the East Passage.

All data comes from **keyless public APIs**: NOAA CO-OPS (tide + currents),
Open-Meteo (wind forecast), NWS (marine text), and NDBC (offshore context).

## Layout

| Path | What |
|------|------|
| `.claude/skills/race-brief/` | The `race-brief` skill — `fetch.py`, `plot.py`, `stations.json`, `SKILL.md` |
| `.claude/commands/` | `/race-brief`, `/wind`, `/tide` slash commands |
| `briefs/` | Generated briefs — one JSON + three PNGs (`_tide`, `_wind`, `_current`) per race day |
| `docs/` | Published brief journal (GitHub Pages) |

## Running a brief

```sh
python -m venv .venv && .venv/bin/pip install -r .claude/skills/race-brief/requirements.txt

# Fetch + render a race window
.venv/bin/python .claude/skills/race-brief/fetch.py --date 2026-07-11 --start 11:00 --end 16:00 --out briefs/2026-07-11.json
.venv/bin/python .claude/skills/race-brief/plot.py briefs/2026-07-11.json
```

Set `NWS_USER_AGENT` (in a local `.env`, never on the command line) to an
identifying string with a contact email for the NWS API.

## Brief journal

Published briefs are archived at the GitHub Pages site under `docs/`.
