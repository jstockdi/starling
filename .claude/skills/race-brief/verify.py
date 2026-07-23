#!/usr/bin/env python3
"""Score a race brief against what actually blew.

Runs a few hours after the race, once the anemometers have logged the whole
window. Re-fetches the real wind for the race window (the series stored in the
brief JSON was captured at generation time, hours before the start), compares
each station to its nearest forecast fix, and writes the scorecard back into the
day's journal page as a ## Verification section plus a briefs/<date>_verify.json.

Usage:
  python verify.py --date 2026-07-23
"""
import argparse
import datetime as dt
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from fetch import fetch_wind_obs, in_window, load_stations

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
BRIEFS = ROOT / "briefs"
PY = sys.executable


def circular_mean(degs):
    degs = [d for d in degs if d is not None]
    if not degs:
        return None
    x = sum(math.cos(math.radians(d)) for d in degs)
    y = sum(math.sin(math.radians(d)) for d in degs)
    if x == 0 and y == 0:
        return None
    return round(math.degrees(math.atan2(y, x)) % 360)


def circular_diff(a, b):
    """Signed smallest angle a-b, in (-180, 180]."""
    if a is None or b is None:
        return None
    return ((a - b + 540) % 360) - 180


def nearest_fix(fixes, lat, lon):
    return min(fixes, key=lambda f: (f["lat"] - lat) ** 2 + (f["lon"] - lon) ** 2)


def window_forecast(fix, start, end):
    """Forecast avg speed / mean dir / max gust over the race window for one fix."""
    win = [h for h in fix["hours"] if in_window(h["time"], start, end)]
    speeds = [h["speed"] for h in win if h["speed"] is not None]
    gusts = [h["gust"] for h in win if h["gust"] is not None]
    return {
        "avg_speed": round(sum(speeds) / len(speeds), 1) if speeds else None,
        "dir": circular_mean([h["dir"] for h in win]),
        "max_gust": round(max(gusts), 1) if gusts else None,
    }


def window_actual(series, start, end):
    win = [o for o in series if o.get("speed") is not None and in_window(o["time"], start, end)]
    if not win:
        return None
    speeds = [o["speed"] for o in win]
    gusts = [o["gust"] for o in win if o.get("gust") is not None]
    return {
        "avg_speed": round(sum(speeds) / len(speeds), 1),
        "peak_speed": round(max(speeds), 1),
        "peak_gust": round(max(gusts), 1) if gusts else None,
        "dir": circular_mean([o["dir"] for o in win]),
        "n_obs": len(win),
    }


def score(fc, ac):
    """Verdict for one station: ratio of actual/forecast speed + direction error."""
    if not fc or not ac or not fc["avg_speed"] or not ac["avg_speed"]:
        return None
    ratio = round(ac["avg_speed"] / fc["avg_speed"], 2)
    dir_err = circular_diff(ac["dir"], fc["dir"])
    speed_ok = 0.8 <= ratio <= 1.25
    dir_ok = dir_err is None or abs(dir_err) <= 25
    if speed_ok and dir_ok:
        verdict = "good"
    elif 0.6 <= ratio <= 1.5 and (dir_err is None or abs(dir_err) <= 45):
        verdict = "fair"
    else:
        # ratio = actual/forecast: >1 means the breeze beat the forecast (under-called).
        verdict = "under" if ratio > 1 else "over"
    return {"speed_ratio": ratio,
            "speed_err_kt": round(ac["avg_speed"] - fc["avg_speed"], 1),
            "dir_err_deg": dir_err, "verdict": verdict}


def verify(date, start_s, end_s):
    start, end = dt.time.fromisoformat(start_s), dt.time.fromisoformat(end_s)
    json_path = BRIEFS / f"{date}.json"
    if not json_path.exists():
        raise SystemExit(f"no brief JSON for {date}")
    data = json.loads(json_path.read_text())
    st = load_stations()
    fixes = data["fixes"]

    stations = []
    for w in st["wind_obs"]:
        obs = fetch_wind_obs(w["id"], dt.date.fromisoformat(date))
        series = obs.get("series") or []
        ac = window_actual(series, start, end)
        fx = nearest_fix(fixes, w["lat"], w["lon"])
        fc = window_forecast(fx, start, end)
        entry = {"station": w["name"], "fix_key": fx["key"], "fix_name": fx["name"],
                 "forecast": fc, "actual": ac, "score": score(fc, ac)}
        if obs.get("error"):
            entry["error"] = obs["error"]
        stations.append(entry)

    scored = [s for s in stations if s.get("score")]
    verdicts = [s["score"]["verdict"] for s in scored]
    if not scored:
        overall = "no-data"
    elif all(v == "good" for v in verdicts):
        overall = "good"
    elif any(v in ("under", "over") for v in verdicts):
        overall = "miss"
    else:
        overall = "fair"

    return {
        "date": date, "window": {"start": start_s, "end": end_s},
        "verified_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "gate_prior": data.get("wind_check"),  # what the pre-race obs gate predicted
        "stations": stations,
        "overall": overall,
    }


def _fmt(v, unit=""):
    return "—" if v is None else f"{v:g}{unit}"


def scorecard_md(v):
    label = {"good": "GOOD", "fair": "FAIR", "miss": "MISS", "no-data": "NO DATA"}[v["overall"]]
    rows = []
    for s in v["stations"]:
        fc, ac, sc = s["forecast"], s["actual"], s.get("score")
        if not ac:
            rows.append(f"| {s['station']} ({s['fix_name']}) | "
                        f"{_fmt(fc['avg_speed'],' kt')} @ {_fmt(fc['dir'],'°')} | "
                        f"no obs | — | — |")
            continue
        derr = sc["dir_err_deg"] if sc else None
        rows.append(
            f"| {s['station']} ({s['fix_name']}) | "
            f"{_fmt(fc['avg_speed'],' kt')} @ {_fmt(fc['dir'],'°')} | "
            f"{_fmt(ac['avg_speed'],' kt')} @ {_fmt(ac['dir'],'°')} "
            f"(peak {_fmt(ac['peak_speed'],' kt')}) | "
            f"{sc['speed_err_kt']:+g} kt ({sc['speed_ratio']:g}×) | "
            f"{('%+d°' % derr) if derr is not None else '—'} |")
    gate = v.get("gate_prior") or {}
    gate_line = ""
    if gate.get("note"):
        gate_line = (f"\nPre-race obs gate called *{gate['note']}* "
                     f"(ratio {gate.get('ratio')}); ")
    return (
        "## Verification\n"
        f"*Scored from the actual anemometer record over {v['window']['start']}–"
        f"{v['window']['end']}.*\n\n"
        "| Station (≈fix) | Forecast | Actual | Speed error | Dir error |\n"
        "|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n\n"
        f"**Verdict: {label}.**{gate_line}\n")


VERIFY_RE = re.compile(r"\n*## Verification\b.*?(?=\n## |\Z)", re.DOTALL)


def upsert_md(date, section):
    """Append (or replace) the ## Verification section in the day's brief markdown."""
    md_path = BRIEFS / f"{date}.md"
    if not md_path.exists():
        return  # no hand-written brief; the _verify.json still stands alone
    text = md_path.read_text().rstrip("\n")
    text = VERIFY_RE.sub("", text).rstrip("\n")
    md_path.write_text(text + "\n\n" + section.rstrip("\n") + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--start", default="18:00")
    ap.add_argument("--end", default="20:00")
    ap.add_argument("--no-publish", action="store_true")
    args = ap.parse_args()

    v = verify(args.date, args.start, args.end)
    (BRIEFS / f"{args.date}_verify.json").write_text(json.dumps(v, indent=2))
    upsert_md(args.date, scorecard_md(v))
    print(f"verified {args.date}: {v['overall']}")
    for s in v["stations"]:
        sc = s.get("score")
        print(f"  {s['station']:16} {s['fix_name']:32} "
              + (f"{sc['verdict']:5} ratio {sc['speed_ratio']} dir {sc['dir_err_deg']}" if sc else "no obs"))
    if not args.no_publish:
        subprocess.run([PY, str(HERE / "publish.py"), args.date], check=True)


if __name__ == "__main__":
    main()
