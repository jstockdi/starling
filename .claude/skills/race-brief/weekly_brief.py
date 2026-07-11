#!/usr/bin/env python3
"""Generate and publish the upcoming weekend's Bristol Harbor race brief.

Runs the full pipeline unattended (for the weekly GitHub Actions job):

  1. Pick the target race day — the upcoming Saturday (>= today), window 11:00-16:00
     (override with RACE_DATE / RACE_START / RACE_END).
  2. fetch.py  -> briefs/<date>.json
  3. plot.py   -> the three PNGs
  4. Write the tactical prose with the Claude API (the local-knowledge system
     prompt is SKILL.md itself, so the brief stays in sync with the skill) and
     save it as briefs/<date>.md.
  5. publish.py -> rebuild the docs/ journal. CI commits + pushes.

Auth: ANTHROPIC_API_KEY in the environment (a GitHub Actions secret in CI).
Never pass an email to fetch.py on the command line — a PII guard blocks it; set
a non-email NWS_USER_AGENT instead (done here).

Usage: python weekly_brief.py            # next Saturday, 11:00-16:00
       RACE_DATE=2026-07-12 python weekly_brief.py
"""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import anthropic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
BRIEFS = ROOT / "briefs"
PY = sys.executable  # the interpreter running this script (the venv/CI python)
MODEL = os.environ.get("RACE_BRIEF_MODEL", "claude-opus-4-8")


def next_saturday(today):
    """The upcoming Saturday, or today if today is Saturday."""
    return today + dt.timedelta(days=(5 - today.weekday()) % 7)


def run(cmd, **env):
    """Run a pipeline step, streaming its output, and fail loudly."""
    e = {**os.environ, **env}
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, env=e)


def model_input(data):
    """Compact the fetch JSON down to what the brief needs (the raw file is ~60KB)."""
    return {
        "harbor": data["harbor"],
        "date": data["date"],
        "window": data["window"],
        "tide_hilo": [{"time": e["t"], "type": e["type"], "height_ft": e["v"]}
                      for e in data["tide"]["hilo"]],
        "wind_fixes": [{"key": f["key"], "name": f["name"], "summary": f.get("summary")}
                       for f in data["fixes"]],
        "live_wind": data.get("live_wind"),
        "currents": [{"name": c["name"], "id": c["id"],
                      "flood_dir": c.get("flood_dir"), "ebb_dir": c.get("ebb_dir"),
                      "units": c.get("units"),
                      "predictions": c.get("predictions")}
                     for c in data["currents"]],
        "nws_marine": (data.get("nws") or {}).get("marine"),
    }


PROMPT = """\
Write the sailboat-racing journal entry (Markdown) for this Bristol Harbor race,
using the local knowledge, the Course & language conventions, and the Brief
structure in the system prompt. Data for the race window is below as JSON.

Hard rules:
- Output ONLY the Markdown, nothing else.
- Start with a YAML front-matter block, then the body:
  ---
  title: "<Day DD Mon YYYY · HH:MM–HH:MM>"
  headline: "<one-line headline: wind trend + current state + any tide caution>"
  ---
  ## Wind
  ...
  ## Current
  ...
  ## Tide
  ...
  ## Tactical call
  ...
- Compass bearings and named shores only — never boat-relative left/right.
- The course is NOT known. Keep the tactical call course-agnostic, then add a
  short "If the course is set" note mapping to the four archetypes.
- Do NOT include environment/plumbing notes. A one-line data-gap note is fine
  only if a data layer is missing.

JSON:
"""


def write_brief(data, md_path):
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY / profile from env
    system = (HERE / "SKILL.md").read_text()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=12000,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user",
                   "content": PROMPT + json.dumps(model_input(data), indent=2)}],
    )
    if resp.stop_reason == "refusal":
        raise SystemExit(f"model refused: {getattr(resp, 'stop_details', None)}")
    md = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not md.startswith("---"):  # belt-and-suspenders: guarantee front matter
        w = data["window"]
        md = (f'---\ntitle: "{data["date"]} · {w["start"]}–{w["end"]}"\n'
              f'headline: ""\n---\n\n{md}')
    md_path.write_text(md + "\n")
    print(f"wrote {md_path}", flush=True)


def main():
    date = os.environ.get("RACE_DATE") or next_saturday(dt.date.today()).isoformat()
    start = os.environ.get("RACE_START", "11:00")
    end = os.environ.get("RACE_END", "16:00")
    ua = os.environ.get("NWS_USER_AGENT", "starling-race-brief-cli")
    BRIEFS.mkdir(parents=True, exist_ok=True)
    json_path = BRIEFS / f"{date}.json"

    run([PY, str(HERE / "fetch.py"), "--date", date, "--start", start,
         "--end", end, "--out", str(json_path)], NWS_USER_AGENT=ua)
    run([PY, str(HERE / "plot.py"), str(json_path)])
    write_brief(json.loads(json_path.read_text()), BRIEFS / f"{date}.md")
    run([PY, str(HERE / "publish.py"), date])
    print(f"\nBrief published for {date} ({start}-{end}).", flush=True)


if __name__ == "__main__":
    main()
