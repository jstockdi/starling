#!/usr/bin/env python3
"""Build the Bristol Harbor race-brief journal (a static GitHub Pages site).

Scans every brief in ``briefs/`` and emits a self-contained static site under
``docs/`` — one page per race day plus a reverse-chronological index. GitHub
Pages serves it from ``main`` /docs; a ``.nojekyll`` marker keeps the raw HTML
untouched (no Jekyll build).

Each entry's prose comes from ``briefs/<date>.md`` when a hand-written brief
exists (YAML-ish front matter: ``title``, ``headline``); otherwise the page is
auto-summarised from the fetch JSON. The three PNGs (``_tide``/``_wind``/
``_current``) are copied into ``docs/img/`` and attached to the page.

Usage: python publish.py            # rebuild the whole journal
       python publish.py 2026-07-11 # rebuild one day + the index
"""
import datetime as dt
import html
import json
import shutil
import sys
from pathlib import Path

import markdown as md

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent          # repo root (.claude/skills/race-brief -> root)
BRIEFS = ROOT / "briefs"
DOCS = ROOT / "docs"
IMG = DOCS / "img"
LAYERS = ("tide", "wind", "current")

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?'
         'family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;'
         '1,9..144,400;1,9..144,500&'
         'family=Inter:wght@400;450;500;600;700&display=swap" rel="stylesheet">')

# Mobile-first. Anthropic-style typography — Fraunces (warm display serif) for
# headings, Inter for body — over a deep-sea-blue / kelp-green / white palette.
# CSS is passed to PAGE.format() as a *value*, so its { } braces are safe.
CSS = """
:root{
  --ink:#132534;        /* near-black navy body text */
  --deep:#0f3a5a;       /* deep sea blue — display headings */
  --sea:#1a5c88;        /* mid sea blue — links, section heads */
  --tide:#2f86b4;       /* lighter tide blue — accents */
  --green:#12806a;      /* kelp / teal green — the second voice */
  --green-d:#0d5f4f;    /* deep green — hover / emphasis */
  --paper:#f5f9fb;      /* cool near-white ground */
  --card:#ffffff;
  --line:#dce7ee;       /* hairline */
  --line-2:#eef4f8;     /* faint fill / zebra */
  --mist:#5b7183;       /* muted slate — meta text */
  --wash:#e9f3f0;       /* green wash — callout */
  --band:linear-gradient(152deg,#0f3a5a 0%,#164f77 46%,#12806a 100%);
  --radius:16px;--radius-sm:10px;--maxw:42rem;
  --shadow:0 14px 34px -22px rgba(15,58,90,.55);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;
  font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:17px;line-height:1.68;color:var(--ink);background:var(--paper);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
h1,h2,h3{font-family:Fraunces,Georgia,"Times New Roman",serif;
  font-optical-sizing:auto;font-weight:500;line-height:1.12;
  letter-spacing:-.017em;text-wrap:balance}
p{margin:0 0 1rem}
a{color:var(--sea);text-underline-offset:2px;text-decoration-thickness:1px}
strong{font-weight:600}
.wrap{max-width:var(--maxw);margin:0 auto;padding:1.1rem 1.2rem 4rem}

/* eyebrow / kicker label — small caps, letter-spaced, in green */
.kicker{font-size:.72rem;font-weight:600;letter-spacing:.11em;text-transform:uppercase;
  color:var(--green);margin:0 0 .55rem}

/* index hero */
header.site{position:relative;overflow:hidden;background:var(--band);color:#fff;
  border-radius:var(--radius);padding:2rem 1.5rem 1.75rem;margin:.4rem 0 1.7rem;
  box-shadow:0 22px 44px -26px rgba(15,58,90,.75)}
header.site::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(120% 90% at 88% 8%,rgba(255,255,255,.16),transparent 55%)}
header.site>*{position:relative;z-index:1}
header.site .mark{width:44px;height:44px;display:block;margin-bottom:1rem}
header.site .kicker{color:rgba(255,255,255,.82);margin-bottom:.45rem}
header.site h1{margin:0;color:#fff;font-size:clamp(1.85rem,7.5vw,2.5rem);
  letter-spacing:-.02em}
header.site .site-sub{margin:.7rem 0 0;color:#e2eef4;font-size:1.02rem;
  line-height:1.55;max-width:32rem}

/* index cards */
.entry{position:relative;overflow:hidden;background:var(--card);
  border:1px solid var(--line);border-radius:var(--radius);
  padding:1.2rem 1.3rem 1.3rem 1.55rem;margin:0 0 1.1rem;box-shadow:var(--shadow);
  transition:transform .16s ease,box-shadow .16s ease}
.entry::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;
  background:var(--band)}
.entry:active{transform:scale(.994)}
@media(hover:hover){.entry:hover{transform:translateY(-2px);
  box-shadow:0 20px 40px -22px rgba(15,58,90,.5)}}
.entry h2{margin:0;font-size:1.4rem}
.entry h2 a{text-decoration:none;color:var(--deep)}
@media(hover:hover){.entry h2 a:hover{color:var(--sea)}}
.entry .meta{margin:.4rem 0 .1rem}
.meta{color:var(--mist);font-size:.85rem;line-height:1.5;margin:.35rem 0 0;
  display:flex;flex-wrap:wrap;gap:.2rem .6rem}
.entry .headline{font-family:Fraunces,Georgia,serif;font-weight:400;font-size:1.1rem;
  line-height:1.42;margin:.7rem 0 0;color:var(--ink)}
.thumbs{display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem;margin-top:1rem}
.thumbs img{width:100%;aspect-ratio:16/9;object-fit:cover;object-position:top;
  border-radius:var(--radius-sm);border:1px solid var(--line);background:#fff}

/* entry page */
.back{display:inline-flex;align-items:center;gap:.4rem;margin:.1rem 0 1.4rem;
  font-size:.9rem;color:var(--sea);text-decoration:none;font-weight:500}
@media(hover:hover){.back:hover{color:var(--green-d)}}
article>.kicker{margin-bottom:.45rem}
article h1{font-size:clamp(1.75rem,7vw,2.35rem);margin:0 0 .55rem;color:var(--deep)}
article>.meta{font-size:.88rem;margin:0 0 .2rem}
article h2{position:relative;font-size:1.36rem;margin:2.3rem 0 .65rem;color:var(--deep);
  padding-bottom:.4rem;border-bottom:2px solid var(--line)}
article h2::before{content:"";display:inline-block;width:.52rem;height:.52rem;
  background:var(--green);border-radius:2px;margin-right:.6rem;
  vertical-align:middle;transform:translateY(-.12em)}
article .headline{position:relative;font-family:Fraunces,Georgia,serif;
  font-style:italic;font-weight:400;font-size:1.24rem;line-height:1.5;
  margin:1rem 0 1.7rem;padding:1.1rem 1.25rem 1.1rem 1.4rem;background:var(--wash);
  border-left:4px solid var(--green);border-radius:12px;color:var(--deep)}
article .headline strong{font-weight:500}
article p,article li{max-width:38rem}
article ul,article ol{padding-left:1.3rem;margin:0 0 1rem}
article li{margin:.35rem 0}
article li::marker{color:var(--green)}
article strong{color:var(--deep)}
article a{color:var(--sea);font-weight:500}
article code{background:var(--line-2);padding:.12rem .38rem;border-radius:5px;
  font-size:.86em;color:var(--deep);font-weight:500}
article em{color:var(--mist)}

/* facts table (auto-summary) */
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;
  margin:1.3rem 0;box-shadow:var(--shadow);-webkit-overflow-scrolling:touch}
.tablewrap table{border-collapse:collapse;width:100%;font-size:.94rem;margin:0}
.tablewrap th,.tablewrap td{padding:.7rem .9rem;text-align:left;vertical-align:top;
  border-bottom:1px solid var(--line)}
.tablewrap tr:last-child th,.tablewrap tr:last-child td{border-bottom:0}
.tablewrap th{color:var(--deep);font-weight:600;white-space:normal;
  width:34%;min-width:8.5rem;background:var(--line-2)}
.tablewrap td{color:var(--ink)}
/* markdown tables (fallback) */
article table{border-collapse:collapse;width:100%;margin:1.2rem 0;font-size:.92rem;
  display:block;overflow-x:auto}
article table th,article table td{border:1px solid var(--line);padding:.55rem .75rem;
  text-align:left}
article table th{background:var(--line-2);color:var(--deep);font-weight:600}

/* chart figures */
.figs{margin-top:1.6rem}
.figs figure{margin:0 0 1.15rem;background:var(--card);border:1px solid var(--line);
  border-radius:var(--radius);padding:.65rem .65rem .35rem;box-shadow:var(--shadow)}
.figs img{width:100%;border-radius:var(--radius-sm);display:block}
.figs figcaption{display:flex;align-items:center;gap:.5rem;
  color:var(--mist);font-size:.82rem;padding:.55rem .35rem .35rem}
.figs figcaption .dot{width:.55rem;height:.55rem;border-radius:50%;flex:none;
  background:var(--sea)}
.figs .fig-tide .dot{background:var(--tide)}
.figs .fig-wind .dot{background:var(--green)}
.figs .fig-current .dot{background:var(--deep)}
.figs figcaption strong{color:var(--deep);font-weight:600}

footer{position:relative;margin-top:2.8rem;color:var(--mist);font-size:.78rem;
  line-height:1.7;border-top:1px solid var(--line);padding-top:1.25rem}
footer::before{content:"";position:absolute;top:-1px;left:0;width:3.5rem;height:2px;
  background:var(--band)}
footer strong{color:var(--sea);font-weight:600}
footer code{background:var(--line-2);padding:.08rem .3rem;border-radius:4px;
  font-size:.92em;color:var(--sea)}
@media(min-width:600px){.wrap{padding-top:1.7rem}}
"""

# Inline sailboat roundel for the index hero (self-contained, on-palette, white
# on the gradient band — no emoji font dependency, renders identically anywhere).
MARK = (
    '<svg class="mark" viewBox="0 0 40 40" fill="none" aria-hidden="true">'
    '<circle cx="20" cy="20" r="18.5" fill="rgba(255,255,255,.10)" '
    'stroke="rgba(255,255,255,.55)"/>'
    '<path d="M19.6 8 L19.6 26.5 L9 26.5 Z" fill="#fff" fill-opacity=".95"/>'
    '<path d="M21.6 12.5 L21.6 26.5 L30.5 26.5 Z" fill="#fff" fill-opacity=".55"/>'
    '<path d="M7.5 28 Q20 34.5 32.5 28" stroke="#fff" stroke-width="2" '
    'stroke-linecap="round"/></svg>'
)

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#1f5f8b">
<title>{title}</title>{fonts}<style>{css}</style></head>
<body><div class="wrap">{body}
<footer><strong>Bristol Harbor Race Briefs</strong> · data from NOAA CO-OPS, Open-Meteo, NWS &amp; NDBC · built by the <code>race-brief</code> skill</footer>
</div></body></html>"""


def esc(s):
    return html.escape(str(s))


def nice_date(date):
    d = dt.date.fromisoformat(date)
    return d.strftime("%A %-d %B %Y")


def parse_front_matter(text):
    """Split ``--- key: val ... ---`` front matter from the markdown body."""
    fm, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip('"').strip("'")
            body = text[end + 4:].lstrip("\n")
    return fm, body


def auto_summary(data):
    """Headline + facts table when no hand-written brief exists for a day."""
    fixes = [f for f in data["fixes"] if f.get("summary")]
    parts = []
    if fixes:
        avgs = [f["summary"]["avg_speed"] for f in fixes]
        gust = max(f["summary"]["max_gust"] for f in fixes)
        d0 = fixes[0]["summary"]["dir_start"]
        d1 = fixes[-1]["summary"]["dir_end"]
        wind = f"{min(avgs):.0f}–{max(avgs):.0f} kt (gust {gust:.0f}), from {d0:.0f}°→{d1:.0f}°"
        parts.append(("Wind", wind))
    hilo = data["tide"]["hilo"]
    if hilo:
        tide = "; ".join(f"{'HW' if e['type']=='H' else 'LW'} {float(e['v']):.1f} ft @ {e['t'][11:16]}" for e in hilo)
        parts.append(("Tide", tide))
    for cs in data["currents"]:
        wevents = cs.get("window", [])
        if wevents:
            cur = "; ".join(f"{e['Type']} {e.get('Velocity_Major', 0)} kt @ {e['Time'][11:16]}" for e in wevents)
            parts.append((f"Current — {cs['name']}", cur))
    headline = parts[0][1] if parts else "See charts below."
    rows = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in parts)
    tbl = f'<div class="tablewrap"><table>{rows}</table></div>'
    body_md = ("*Auto-summarised from the fetch data — no hand-written brief for this day.*\n\n")
    return headline, body_md, tbl


def entry_images(date):
    """Return (layer, filename) for each PNG that exists for this date."""
    found = []
    for layer in LAYERS:
        src = BRIEFS / f"{date}_{layer}.png"
        if src.exists():
            IMG.mkdir(parents=True, exist_ok=True)
            dest = IMG / src.name
            shutil.copyfile(src, dest)
            found.append((layer, f"img/{src.name}"))
    return found


def build_entry(json_path):
    date = json_path.stem
    data = json.loads(json_path.read_text())
    md_path = BRIEFS / f"{date}.md"
    if md_path.exists():
        fm, body_src = parse_front_matter(md_path.read_text())
        title = fm.get("title") or nice_date(date)
        headline = fm.get("headline", "")
        body_html = md.markdown(body_src, extensions=["tables", "fenced_code", "sane_lists"])
        extra_tbl = ""
    else:
        title = nice_date(date)
        headline, body_md, extra_tbl = auto_summary(data)
        body_html = md.markdown(body_md, extensions=["tables", "fenced_code", "sane_lists"])

    imgs = entry_images(date)
    figs = "".join(
        f'<figure class="fig-{layer}"><img src="{fn}" alt="{layer} chart for {date}">'
        f'<figcaption><span class="dot"></span><strong>{layer.title()}</strong> · {esc(date)}</figcaption></figure>'
        for layer, fn in imgs
    )
    harbor = data.get("harbor", "Bristol Harbor")
    win = data["window"]
    body = (
        f'<a class="back" href="index.html">← All briefs</a>'
        f'<article><p class="kicker">{esc(harbor)} · Rhode Island</p>'
        f"<h1>{esc(title)}</h1>"
        f'<p class="meta">Race window {esc(win["start"])}–{esc(win["end"])}</p>'
        + (f'<p class="headline">{esc(headline)}</p>' if headline else "")
        + body_html + extra_tbl
        + f'<div class="figs">{figs}</div></article>'
    )
    (DOCS / f"{date}.html").write_text(PAGE.format(title=esc(title), fonts=FONTS, css=CSS, body=body))
    return {"date": date, "title": title, "headline": headline,
            "window": f"{data['window']['start']}–{data['window']['end']}",
            "thumbs": imgs}


def build_index(entries):
    entries = sorted(entries, key=lambda e: e["date"], reverse=True)
    cards = []
    for e in entries:
        thumbs = "".join(f'<img src="{fn}" alt="{layer}">' for layer, fn in e["thumbs"])
        cards.append(
            f'<div class="entry">'
            f'<h2><a href="{e["date"]}.html">{esc(e["title"])}</a></h2>'
            f'<p class="meta">Race window {esc(e["window"])}</p>'
            + (f'<p class="headline">{esc(e["headline"])}</p>' if e["headline"] else "")
            + (f'<div class="thumbs">{thumbs}</div>' if thumbs else "")
            + "</div>"
        )
    body = (
        '<header class="site">' + MARK
        + '<p class="kicker">Bristol Harbor · Rhode Island</p>'
        '<h1>Race Briefs</h1>'
        '<p class="site-sub">Hyper-local wind, tide &amp; tidal-current briefs — from the '
        'inner harbor out around Hog Island &amp; Poppasquash Point into the East Passage.</p>'
        '</header>'
        + ("".join(cards) or "<p>No briefs yet.</p>")
    )
    (DOCS / "index.html").write_text(PAGE.format(title="Bristol Harbor Race Briefs", fonts=FONTS, css=CSS, body=body))


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").write_text("")
    jsons = sorted(BRIEFS.glob("*.json"))
    if not jsons:
        print("no briefs found in briefs/", file=sys.stderr)
        sys.exit(1)
    # Always rebuild every page so shared CSS/layout stays consistent; the
    # optional CLI arg just narrows what we *report* building.
    only = set(sys.argv[1:])
    entries = [build_entry(p) for p in jsons]
    build_index(entries)
    for e in entries:
        if not only or e["date"] in only:
            print(DOCS / f"{e['date']}.html")
    print(DOCS / "index.html")


if __name__ == "__main__":
    main()
