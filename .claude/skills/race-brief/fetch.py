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
    """Hourly wind + gust + direction from Open-Meteo at an exact fix."""
    params = dict(latitude=lat, longitude=lon,
                  hourly="wind_speed_10m,wind_gusts_10m,wind_direction_10m",
                  wind_speed_unit="kn", timezone="America/New_York",
                  start_date=date.strftime("%Y-%m-%d"),
                  end_date=date.strftime("%Y-%m-%d"))
    h = _get(OPEN_METEO, params).json().get("hourly", {})
    return [
        {"time": t, "speed": s, "gust": g, "dir": d}
        for t, s, g, d in zip(h.get("time", []), h.get("wind_speed_10m", []),
                              h.get("wind_gusts_10m", []), h.get("wind_direction_10m", []))
    ]


def fetch_live_wind(station_id):
    params = dict(application="race-brief", date="latest", station=station_id,
                  time_zone="lst_ldt", units="english", format="json", product="wind")
    try:
        j = _get(COOPS, params).json()
        d = j.get("data", [{}])[0]
        return {"time": d.get("t"), "speed": d.get("s"), "dir": d.get("d"),
                "dir_txt": d.get("dr"), "gust": d.get("g")}
    except Exception as e:  # obs stations go offline; brief still works without
        return {"error": str(e)}


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
    """Race-window average/max and directional trend for one fix."""
    win = [h for h in hours if in_window(h["time"], start, end)]
    if not win:
        return None
    speeds = [h["speed"] for h in win]
    gusts = [h["gust"] for h in win]
    return {
        "avg_speed": round(sum(speeds) / len(speeds), 1),
        "max_gust": max(gusts),
        "dir_start": win[0]["dir"],
        "dir_end": win[-1]["dir"],
        "veer": round(((win[-1]["dir"] - win[0]["dir"] + 540) % 360) - 180),
    }


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
        out["live_wind"].append({**w, "obs": fetch_live_wind(w["id"])})

    rep = next(f for f in st["fixes"] if f["key"] == st["representative_fix"])
    out["nws"] = fetch_nws(rep["lat"], rep["lon"])

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
