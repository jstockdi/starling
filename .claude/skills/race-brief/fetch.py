#!/usr/bin/env python3
"""Fetch wind, tide, and current data for a Bristol Harbor race brief.

Pulls from keyless public APIs (NOAA CO-OPS, Open-Meteo, NWS, NDBC) at a set of
fixes spanning the inner harbor out around Hog Island into the East Passage,
then writes one normalised JSON file that plot.py and the brief prose consume.

Usage:
  python fetch.py --date 2026-07-11 --start 11:00 --end 16:00 --out briefs/2026-07-11.json
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
NWS = "https://api.weather.gov"
NDBC = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"

# Wind models pulled per fix. HRRR (3 km) resolves the sea breeze that the coarse
# best_match blend smears out; ECMWF + GFS ride along for a home-grown spread
# (models agreeing = confidence, diverging = flag it). These are the same models
# Windy renders — pulling them keyless keeps the brief in the team's dialect.
WIND_MODELS = ["ncep_hrrr_conus", "ecmwf_ifs025", "gfs_seamless"]
PRIMARY_MODEL = "ncep_hrrr_conus"
# Field-fallback order when the primary has a gap at an hour (HRRR only runs ~48 h).
MODEL_FALLBACK = ["ncep_hrrr_conus", "gfs_seamless", "ecmwf_ifs025"]
MS_TO_KN = 1.94384  # NDBC reports wind in m/s

# NWS asks for an identifying User-Agent with contact info; never hard-code an
# email (a PII guard blocks that). Read it from the environment instead.
NWS_UA = os.environ.get("NWS_USER_AGENT", "bristol-race-brief-cli")


def _get(url, params=None, headers=None, timeout=20):
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r


def load_stations():
    return json.loads((HERE / "stations.json").read_text())


def fetch_tide(station_id, date):
    """High/low events plus a 6-minute curve for the day."""
    d = date.strftime("%Y%m%d")
    common = dict(application="race-brief", begin_date=d, end_date=d,
                  datum="MLLW", station=station_id, time_zone="lst_ldt",
                  units="english", format="json", product="predictions")
    hilo = _get(COOPS, {**common, "interval": "hilo"}).json().get("predictions", [])
    curve = _get(COOPS, {**common, "interval": "6"}).json().get("predictions", [])
    return {"hilo": hilo, "curve": curve}


def fetch_current(station_id, date):
    d = date.strftime("%Y%m%d")
    params = dict(application="race-brief", begin_date=d, end_date=d,
                  station=station_id, time_zone="lst_ldt", units="english",
                  format="json", product="currents_predictions", interval="MAX_SLACK")
    data = _get(COOPS, params).json().get("current_predictions", {})
    return data.get("cp", []), data.get("units", "")


def fetch_wind_forecast(lat, lon, date):
    """Hourly wind + gust + direction at an exact fix, from three models.

    `hours` carries the primary (HRRR, with per-field fallback to GFS then ECMWF)
    so plot.py and the prose read one clean series. Each hour also keeps a `models`
    map of every model's speed for the spread that summarise_fix() distils.
    """
    params = dict(latitude=lat, longitude=lon,
                  hourly="wind_speed_10m,wind_gusts_10m,wind_direction_10m",
                  wind_speed_unit="kn", timezone="America/New_York",
                  models=",".join(WIND_MODELS),
                  start_date=date.strftime("%Y-%m-%d"),
                  end_date=date.strftime("%Y-%m-%d"))
    h = _get(OPEN_METEO, params).json().get("hourly", {})
    times = h.get("time", [])

    def col(var, model):
        return h.get(f"{var}_{model}", [])

    def pick(var, i):
        """First non-null value across the fallback chain at hour i."""
        for m in MODEL_FALLBACK:
            v = col(var, m)
            if i < len(v) and v[i] is not None:
                return v[i]
        return None

    hours = []
    for i, t in enumerate(times):
        models = {m: col("wind_speed_10m", m)[i]
                  for m in WIND_MODELS
                  if i < len(col("wind_speed_10m", m)) and col("wind_speed_10m", m)[i] is not None}
        hours.append({"time": t,
                      "speed": pick("wind_speed_10m", i),
                      "gust": pick("wind_gusts_10m", i),
                      "dir": pick("wind_direction_10m", i),
                      "models": models})
    return hours


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fetch_wind_obs(station_id, date):
    """Full-day 6-minute anemometer series + the latest ob.

    The old code grabbed only date=latest — a single snapshot from hours before
    an evening race. The series lets the pre-race gate calibrate against the
    afternoon build, and lets a post-race pass score the forecast against truth.
    """
    d = date.strftime("%Y%m%d")
    params = dict(application="race-brief", begin_date=d, end_date=d,
                  station=station_id, time_zone="lst_ldt", units="english",
                  format="json", product="wind")
    try:
        rows = _get(COOPS, params).json().get("data", [])
    except Exception as e:  # obs stations go offline; brief still works without
        return {"error": str(e)}
    series = [{"time": r.get("t"), "speed": _f(r.get("s")), "gust": _f(r.get("g")),
               "dir": _f(r.get("d")), "dir_txt": r.get("dr")} for r in rows]
    return {"series": series, "latest": series[-1] if series else None}


def fetch_offshore(station_id):
    """Latest NDBC buoy obs — the open-ocean signal arriving from the south.

    The wind sensor drops out for stretches (rows come back all `MM`) while the
    wave sensor keeps reporting, so `latest` is the newest *wind-bearing* row and
    `wave_dir` carries the mean wave direction as a fallback southerly-fetch cue.
    """
    def num(x):
        return None if x == "MM" else _f(x)

    try:
        txt = _get(NDBC.format(station=station_id)).text
    except Exception as e:
        return {"error": str(e)}
    rows = []
    for l in [l for l in txt.splitlines() if l and not l.startswith("#")][:8]:
        p = l.split()
        if len(p) < 12:
            continue
        spd, gst = num(p[6]), num(p[7])
        rows.append({
            "time": f"{p[0]}-{p[1]}-{p[2]} {p[3]}:{p[4]} UTC",
            "dir": num(p[5]),
            "speed": round(spd * MS_TO_KN, 1) if spd is not None else None,
            "gust": round(gst * MS_TO_KN, 1) if gst is not None else None,
            "wave_dir": num(p[11]),  # MWD, degT — where the swell is coming from
        })
    with_wind = next((r for r in rows if r["speed"] is not None), None)
    return {"latest": with_wind, "latest_any": rows[0] if rows else None,
            "wind_available": with_wind is not None, "recent": rows}


def fetch_nws(lat, lon):
    try:
        pt = _get(f"{NWS}/points/{lat},{lon}", headers={"User-Agent": NWS_UA}).json()
        p = pt["properties"]
        zone = p.get("forecastZone", "").rstrip("/").split("/")[-1]
        hourly = _get(p["forecastHourly"], headers={"User-Agent": NWS_UA}).json()
        periods = hourly["properties"]["periods"][:24]
        marine = None
        if zone:
            try:
                fz = _get(f"{NWS}/zones/forecast/{zone}/forecast",
                          headers={"User-Agent": NWS_UA}).json()
                marine = fz["properties"]["periods"][:4]
            except Exception:
                pass
        return {"zone": zone, "hourly": periods, "marine": marine}
    except Exception as e:
        return {"error": str(e)}


def in_window(tstr, start, end):
    try:
        t = dt.datetime.strptime(tstr[:16], "%Y-%m-%d %H:%M").time()
    except ValueError:
        t = dt.datetime.fromisoformat(tstr).time()
    return start <= t <= end


def summarise_fix(hours, start, end):
    """Race-window average/max, directional trend, and cross-model spread."""
    win = [h for h in hours if in_window(h["time"], start, end)]
    if not win:
        return None
    speeds = [h["speed"] for h in win if h["speed"] is not None]
    gusts = [h["gust"] for h in win if h["gust"] is not None]
    # Per-model window-average speed → spread = how far the models disagree.
    per_model = {}
    for h in win:
        for m, v in (h.get("models") or {}).items():
            if v is not None:
                per_model.setdefault(m, []).append(v)
    model_avgs = {m: round(sum(vs) / len(vs), 1) for m, vs in per_model.items() if vs}
    spread = round(max(model_avgs.values()) - min(model_avgs.values()), 1) \
        if len(model_avgs) >= 2 else None
    return {
        "avg_speed": round(sum(speeds) / len(speeds), 1) if speeds else None,
        "max_gust": max(gusts) if gusts else None,
        "dir_start": win[0]["dir"],
        "dir_end": win[-1]["dir"],
        "veer": round(((win[-1]["dir"] - win[0]["dir"] + 540) % 360) - 180)
        if win[0]["dir"] is not None and win[-1]["dir"] is not None else None,
        "model_avgs": model_avgs,
        "spread": spread,  # kt between the strongest and weakest model
    }


def wind_check(obs_series, fix_hours):
    """Gate the model against the live anemometer over the hours both cover.

    At generation (early afternoon for an evening race) the obs cover the sea-breeze
    build. If the anemometer is running materially stronger/weaker than the model at
    the same clock hours, the prose should lean toward the obs regime — the miss on
    2026-07-22 was the model calling 6-7 kt while Conimicut already read 18 kt.
    """
    if not obs_series or not fix_hours:
        return None
    # Mean obs speed per clock hour that has obs.
    obs_by_hour = {}
    for o in obs_series:
        t, s = o.get("time"), o.get("speed")
        if t and s is not None:
            obs_by_hour.setdefault(t[11:13], []).append(s)
    obs_hourly = {hh: sum(v) / len(v) for hh, v in obs_by_hour.items()}
    model_hourly = {h["time"][11:13]: h["speed"] for h in fix_hours if h.get("speed") is not None}
    common = sorted(set(obs_hourly) & set(model_hourly))
    if not common:
        return None
    obs_mean = sum(obs_hourly[hh] for hh in common) / len(common)
    model_mean = sum(model_hourly[hh] for hh in common) / len(common)
    ratio = round(obs_mean / model_mean, 2) if model_mean else None
    if ratio is None:
        note = "no model wind to compare"
    elif ratio >= 1.3:
        note = "obs materially STRONGER than model — lean toward the obs regime"
    elif ratio <= 0.77:
        note = "obs materially WEAKER than model — model may be over-blowing"
    else:
        note = "obs and model broadly agree"
    return {"hours_compared": common, "obs_mean_kt": round(obs_mean, 1),
            "model_mean_kt": round(model_mean, 1), "ratio": ratio, "note": note}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--start", default="11:00", help="race window start HH:MM")
    ap.add_argument("--end", default="16:00", help="race window end HH:MM")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    date = dt.date.fromisoformat(args.date)
    start = dt.time.fromisoformat(args.start)
    end = dt.time.fromisoformat(args.end)
    st = load_stations()

    out = {
        "harbor": st["harbor_name"],
        "date": args.date,
        "window": {"start": args.start, "end": args.end},
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tide": {"station": st["tide_station"], **fetch_tide(st["tide_station"]["id"], date)},
        "currents": [],
        "fixes": [],
        "live_wind": [],
        "offshore": None,
        "wind_check": None,
        "nws": None,
    }

    for cs in st["current_stations"]:
        cp, units = fetch_current(cs["id"], date)
        out["currents"].append({**cs, "units": units,
                                "predictions": cp,
                                "window": [c for c in cp if in_window(c["Time"], start, end)]})

    for fx in st["fixes"]:
        hours = fetch_wind_forecast(fx["lat"], fx["lon"], date)
        out["fixes"].append({**fx, "hours": hours,
                             "summary": summarise_fix(hours, start, end)})

    for w in st["wind_obs"]:
        out["live_wind"].append({**w, **fetch_wind_obs(w["id"], date)})

    if st.get("offshore"):
        out["offshore"] = {**st["offshore"], **fetch_offshore(st["offshore"]["id"])}

    rep = next(f for f in st["fixes"] if f["key"] == st["representative_fix"])
    out["nws"] = fetch_nws(rep["lat"], rep["lon"])

    # Gate: primary anemometer (first wind_obs) vs the representative fix's model.
    rep_hours = next((f["hours"] for f in out["fixes"] if f["key"] == st["representative_fix"]), None)
    obs0 = out["live_wind"][0].get("series") if out["live_wind"] else None
    out["wind_check"] = wind_check(obs0, rep_hours)

    dest = Path(args.out) if args.out else HERE.parent.parent.parent / "briefs" / f"{args.date}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(str(dest))


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        sys.exit(1)
