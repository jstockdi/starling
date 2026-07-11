#!/usr/bin/env python3
"""Render the Bristol Harbor race-brief visuals from a fetch.py JSON file.

Produces three PNGs next to the JSON:
  <stem>_tide.png     tide curve for the day, race window shaded
  <stem>_wind.png     wind speed gradient across all fixes + gust band + dir barbs
  <stem>_current.png  current velocity for harbor-mouth and East Passage stations

Usage: python plot.py briefs/2026-07-11.json
"""
import datetime as dt
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

# Muted, high-contrast palette that reads in daylight on a phone.
INK = "#1b2a3a"
GRID = "#d5dde5"
WINDOW = "#f2c14e"          # race-window shade
SERIES = ["#2a6f97", "#468faf", "#61a5c2", "#89c2d9", "#a9d6e5"]  # inner -> outer
FLOOD = "#2a9d8f"
EBB = "#e76f51"

plt.rcParams.update({
    "figure.dpi": 140, "font.size": 10, "axes.edgecolor": INK,
    "axes.labelcolor": INK, "text.color": INK, "xtick.color": INK,
    "ytick.color": INK, "axes.grid": True, "grid.color": GRID,
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def _parse(t):
    return dt.datetime.strptime(t[:16].replace("T", " "), "%Y-%m-%d %H:%M")


def _window_span(data):
    d = data["date"]
    s = dt.datetime.fromisoformat(f"{d}T{data['window']['start']}")
    e = dt.datetime.fromisoformat(f"{d}T{data['window']['end']}")
    return s, e


def _shade_window(ax, data):
    s, e = _window_span(data)
    ax.axvspan(s, e, color=WINDOW, alpha=0.22, zorder=0, label="race window")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))


def plot_tide(data, out):
    curve = data["tide"]["curve"]
    if not curve:
        return None
    ts = [_parse(p["t"]) for p in curve]
    hs = [float(p["v"]) for p in curve]
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.plot(ts, hs, color=SERIES[0], lw=2)
    ax.fill_between(ts, hs, min(hs) - 0.3, color=SERIES[0], alpha=0.08)
    _shade_window(ax, data)
    for ev in data["tide"]["hilo"]:
        t, v, kind = _parse(ev["t"]), float(ev["v"]), ev["type"]
        ax.annotate(f"{'HW' if kind=='H' else 'LW'} {v:.1f}ft\n{ev['t'][11:16]}",
                    (t, v), textcoords="offset points", xytext=(0, 8 if kind == "H" else -22),
                    ha="center", fontsize=8, color=INK)
        ax.plot(t, v, "o", color=INK, ms=4)
    ax.set_ylabel("Height (ft, MLLW)")
    ax.set_title(f"Tide — {data['tide']['station']['name']} — {data['date']}", loc="left", fontweight="bold")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def plot_wind(data, out):
    fig, ax = plt.subplots(figsize=(9, 3.8))
    outer = None
    for i, fx in enumerate(data["fixes"]):
        hrs = fx["hours"]
        if not hrs:
            continue
        ts = [_parse(h["time"]) for h in hrs]
        sp = [h["speed"] for h in hrs]
        ax.plot(ts, sp, color=SERIES[i % len(SERIES)], lw=1.8, label=fx["name"])
        outer = fx
    # gust band for the outermost fix (most exposed)
    if outer:
        ts = [_parse(h["time"]) for h in outer["hours"]]
        sp = [h["speed"] for h in outer["hours"]]
        gu = [h["gust"] for h in outer["hours"]]
        ax.fill_between(ts, sp, gu, color=SERIES[-1], alpha=0.18, label=f"gusts ({outer['name']})")
        # wind-direction barbs along the top for the representative harbor-mouth fix
        rep = next((f for f in data["fixes"] if f["key"] == "hog_mouth"), outer)
        rh = rep["hours"][::2]
        rt = [_parse(h["time"]) for h in rh]
        top = max(gu) * 1.08
        for h, t in zip(rh, rt):
            rad = math.radians(h["dir"])
            u, v = -math.sin(rad), -math.cos(rad)  # meteorological "from"
            ax.barbs(mdates.date2num(t), top, u * h["speed"], v * h["speed"],
                     length=5.5, color=INK, zorder=5)
    _shade_window(ax, data)
    ax.set_ylabel("Wind (kn)")
    ax.set_ylim(bottom=0)
    ax.set_title(f"Wind gradient (inner harbor → East Passage) — {data['date']}",
                 loc="left", fontweight="bold")
    ax.legend(loc="upper left", fontsize=7, ncol=2, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def plot_current(data, out):
    fig, ax = plt.subplots(figsize=(9, 3.2))
    styles = ["-", "--"]
    for i, cs in enumerate(data["currents"]):
        cp = cs.get("predictions", [])
        pts = [(_parse(c["Time"]), c["Velocity_Major"]) for c in cp if c.get("Type") != "slack"
               or c.get("Velocity_Major") == 0]
        cp_all = [(_parse(c["Time"]), c["Velocity_Major"]) for c in cp]
        if not cp_all:
            continue
        ts = [t for t, _ in cp_all]
        vs = [v for _, v in cp_all]
        ax.plot(ts, vs, styles[i % 2], color=INK, lw=1.4, marker="o", ms=3,
                label=cs["name"], zorder=3)
    ax.axhline(0, color=INK, lw=1)
    # colour flood (up-bay) vs ebb (down-bay)
    ax.fill_between(ax.get_xlim(), 0, 3, color=FLOOD, alpha=0.06)
    ax.fill_between(ax.get_xlim(), -3, 0, color=EBB, alpha=0.06)
    ax.text(0.995, 0.92, "flood ↑ up-bay (NNE)", transform=ax.transAxes,
            ha="right", color=FLOOD, fontsize=8, fontweight="bold")
    ax.text(0.995, 0.06, "ebb ↓ down-bay (SSW)", transform=ax.transAxes,
            ha="right", color=EBB, fontsize=8, fontweight="bold")
    _shade_window(ax, data)
    ax.set_ylabel("Velocity (kn)")
    ax.set_title(f"Tidal current — harbor mouth vs. East Passage — {data['date']}",
                 loc="left", fontweight="bold")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: plot.py <brief.json>", file=sys.stderr)
        sys.exit(1)
    src = Path(sys.argv[1])
    data = json.loads(src.read_text())
    stem = src.with_suffix("")
    made = [
        plot_tide(data, f"{stem}_tide.png"),
        plot_wind(data, f"{stem}_wind.png"),
        plot_current(data, f"{stem}_current.png"),
    ]
    for m in made:
        if m:
            print(m)


if __name__ == "__main__":
    main()
