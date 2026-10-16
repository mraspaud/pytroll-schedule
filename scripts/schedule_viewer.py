#!/usr/bin/env python3
"""Render trollsched acquisition-schedule request files as a self-contained HTML timeline.

Usage:
    schedule_viewer.py --tle tle.txt -o schedule.html request_meos.xml request_cgi.xml

One row per satellite, bars coloured by antenna, mouse-wheel zoom / drag pan,
hover for pass details, orbit number and swath coverage on a near-sided
perspective map centred on the station.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import defusedxml.ElementTree as ET
import numpy as np
from pyorbital.tlefile import Tle

from trollsched.satpass import Pass

logger = logging.getLogger("schedule_viewer")

TIME_FMT = "%Y-%m-%d-%H:%M:%S"

# Schedule name -> TLE name, when normalisation alone is not enough.
TLE_ALIASES = {
    "npp": "SUOMI NPP",
    "aws-pfm": "ARCTIC WEATHER SATELLITE",
    "sga1": "METOP-SGA1",
    "sgb1": "METOP-SGB1",
    "fy3d": "FENGYUN 3D",
    "fy3e": "FENGYUN 3E",
    "fy3f": "FENGYUN 3F",
    "fy3g": "FENGYUN 3G",
    "fy3h": "FENGYUN 3H",
}

# Schedule name -> instrument used by trollsched for the swath geometry.
INSTRUMENTS = {
    "noaa20": "viirs",
    "noaa21": "viirs",
    "noaa22": "viirs",
    "npp": "viirs",
    "aqua": "modis",
    "terra": "modis",
    "fy3d": "mersi-2",
    "fy3e": "mersi-ll",
    "fy3f": "mersi-3",
    "fy3h": "mersi-3",
    "metop-a": "avhrr",
    "metop-b": "avhrr",
    "metop-c": "avhrr",
    "sga1": "metimage",
    "aws-pfm": "avhrr",
}

COVERAGE_POINTS = 16      # vertices kept per swath polygon
COASTLINE_STEP = 1        # keep every n-th coastline vertex
GEO_ALTITUDE_KM = 35786.0
TRIM_TOLERANCE_S = 5      # a scheduled pass shorter than the visibility by more than this is "trimmed"

DISPLAY_NAMES = {
    "npp": "NPP",
    "aws-pfm": "AWS-PFM",
}


def _norm(name):
    return "".join(ch for ch in name.lower() if ch.isalnum())


def parse_schedule(path):
    """Parse one acquisition-schedule XML file."""
    root = ET.parse(path).getroot()
    props = {child.tag: child.text for child in root.find("properties")}
    passes = []
    for node in root.findall("pass"):
        passes.append({
            "satellite": node.get("satellite"),
            "antenna": props.get("antenna", "?"),
            "station": props.get("station", "?"),
            "start": datetime.strptime(node.get("start-time"), TIME_FMT),
            "end": datetime.strptime(node.get("end-time"), TIME_FMT),
        })
    span = (datetime.strptime(props["file-start"], TIME_FMT),
            datetime.strptime(props["file-end"], TIME_FMT))
    return props, passes, span


def load_tles(path, aliases):
    """Read every TLE in *path*, keyed by normalised name."""
    lines = [ln.rstrip() for ln in Path(path).read_text().splitlines() if ln.strip()]
    tles = {}
    for i in range(0, len(lines) - 2, 3):
        tles[_norm(lines[i])] = Tle(lines[i], line1=lines[i + 1], line2=lines[i + 2])

    def lookup(sat):
        for cand in (aliases.get(sat), TLE_ALIASES.get(sat), sat):
            if cand and _norm(cand) in tles:
                return tles[_norm(cand)]
        return None
    return lookup


def _xyz(lons, lats):
    lons = np.radians(np.asarray(lons, dtype=float))
    lats = np.radians(np.asarray(lats, dtype=float))
    return np.column_stack((np.cos(lats) * np.cos(lons),
                            np.cos(lats) * np.sin(lons),
                            np.sin(lats)))


def _lonlat(p):
    p = p / np.linalg.norm(p)
    return [round(float(np.degrees(np.arctan2(p[1], p[0]))), 2),
            round(float(np.degrees(np.arcsin(p[2]))), 2)]


def _sample_segment(xyz, npoints):
    """Sample *npoints* evenly spaced by arc length along an open polyline.

    Include the first vertex, excluding the last (the next segment's first vertex).
    """
    seg = np.arccos(np.clip(np.sum(xyz[:-1] * xyz[1:], axis=1), -1, 1))
    cum = np.concatenate(([0.0], np.cumsum(seg)))
    out = []
    for t in np.linspace(0, cum[-1], npoints, endpoint=False):
        i = min(int(np.searchsorted(cum, t, side="right") - 1), len(seg) - 1)
        f = (t - cum[i]) / seg[i] if seg[i] > 0 else 0.0
        out.append(_lonlat(xyz[i] + (xyz[i + 1] - xyz[i]) * f))
    return out, cum[-1]


def resample_boundary(boundary, npoints):
    """Reduce a swath boundary to about *npoints* vertices.

    The four swath corners (the ends of the first and last scan) are always kept; the remaining points are spread
    over the four sides in proportion to their length.
    """
    top = _xyz(boundary.top_lons, boundary.top_lats)
    bottom = _xyz(boundary.bottom_lons, boundary.bottom_lats)
    right = _xyz(boundary.right_lons, boundary.right_lats)
    left = _xyz(boundary.left_lons, boundary.left_lats)
    # The decimated sides in trollsched do not always reach the end rows, so the
    # corners are taken from the rows and the sides only contribute interior points.
    sides = [top,
             np.vstack((top[-1:], right[1:-1], bottom[:1])),
             bottom,
             np.vstack((bottom[-1:], left[1:-1], top[:1]))]
    lengths = [_sample_segment(side, 1)[1] for side in sides]
    total = sum(lengths) or 1.0
    extra = max(npoints - 4, 0)
    counts = [1 + int(round(extra * length / total)) for length in lengths]
    out = []
    for side, count in zip(sides, counts):
        out.extend(_sample_segment(side, count)[0])
    return out


def estimate_station(passes, tle_lookup, max_passes=60):
    """Guess the station position from the schedule itself.

    AOS and LOS of every pass are moments where the satellite sits on the
    station's horizon, so the position (and the horizon elevation) is found by
    least squares on the elevation at those times.  The mean of the mid-pass
    sub-satellite points gives the starting guess.
    """
    from pyorbital.orbital import Orbital
    usable = [(p, tle_lookup(p["satellite"])) for p in passes]
    usable = [(p, t) for p, t in usable if t is not None]
    if not usable:
        return None
    step = max(1, len(usable) // max_passes)
    sample = usable[::step][:max_passes]
    orbs = [(Orbital(p["satellite"], line1=t.line1, line2=t.line2), p) for p, t in sample]
    mids = [_xyz(*orb.get_lonlatalt(p["start"] + (p["end"] - p["start"]) / 2)[:2]) [0]
            for orb, p in orbs]
    guess = _lonlat(np.mean(mids, axis=0)) + [0.0]
    try:
        from scipy.optimize import least_squares
    except ImportError:
        logger.warning("scipy not available; station guessed from mid-pass sub-points only")
        return guess

    def residuals(x):
        lon, lat, horizon = x
        return [orb.get_observer_look(t, lon, lat, 0.0)[1] - horizon
                for orb, p in orbs for t in (p["start"], p["end"])]

    fit = least_squares(residuals, (guess[0], guess[1], 0.0), loss="soft_l1", f_scale=1.0,
                        bounds=([-180, -89, -10], [180, 89, 30]))
    rms = float(np.sqrt(np.mean(np.square(fit.fun))))
    if rms > 3:
        logger.warning("Station fit is poor (rms %.1f deg); give --lat/--lon explicitly", rms)
    return [round(float(fit.x[0]), 3), round(float(fit.x[1]), 3), round(float(fit.x[2]), 2)]


def unscheduled_passes(passes, span, tle_lookup, lon, lat, horizon):
    """All passes of the requested satellites over the station that are not in the schedule.

    As a side effect, scheduled passes that are shorter than the visibility
    window get a ``full`` (start, end) entry describing the untrimmed pass.
    """
    from pyorbital.orbital import Orbital
    by_sat = {}
    for p in passes:
        by_sat.setdefault(p["satellite"], []).append(p)
    station = passes[0]["station"] if passes else "?"
    hours = int((span[1] - span[0]).total_seconds() // 3600) + 2
    extra = []
    for sat, scheduled in sorted(by_sat.items()):
        tle = tle_lookup(sat)
        if tle is None:
            continue
        orb = Orbital(sat, line1=tle.line1, line2=tle.line2)
        for rise, fall, _ in orb.get_next_passes(span[0], hours, lon, lat, 0.0, horizon=max(horizon, 0.0)):
            if fall < span[0] or rise > span[1]:
                continue
            matches = [q for q in scheduled if q["start"] < fall and q["end"] > rise]
            if matches:
                for q in matches:
                    lost = (q["start"] - rise).total_seconds(), (fall - q["end"]).total_seconds()
                    if max(lost) > TRIM_TOLERANCE_S:
                        q["full"] = (rise.replace(microsecond=0), fall.replace(microsecond=0))
                continue
            extra.append({"satellite": sat, "antenna": "", "station": station,
                          "start": rise.replace(microsecond=0), "end": fall.replace(microsecond=0),
                          "unscheduled": True})
    return extra


def add_geometry(passes, tle_lookup, instruments, npoints):
    """Attach orbit number and coverage polygon to each pass (in place)."""
    missing, fallen_back = set(), set()
    for p in passes:
        sat = p["satellite"]
        tle = tle_lookup(sat)
        if tle is None:
            missing.add(sat)
            continue
        inst = instruments.get(sat, INSTRUMENTS.get(sat, "avhrr"))
        for attempt in (inst, "avhrr"):
            try:
                ov = Pass(sat, p["start"], p["end"], instrument=attempt,
                          tle1=tle.line1, tle2=tle.line2)
                p["orbit"] = int(ov.orb.get_orbit_number(ov.uptime))
                p["coverage"] = resample_boundary(ov.boundary, npoints)
                if "full" in p:
                    full = Pass(sat, p["full"][0], p["full"][1], instrument=attempt,
                                tle1=tle.line1, tle2=tle.line2)
                    p["full_coverage"] = resample_boundary(full.boundary, npoints)
                break
            except Exception as err:  # noqa: BLE001 - one bad pass must not kill the page
                if attempt != "avhrr" and attempt not in fallen_back:
                    logger.warning("Swath for %s as %s failed (%s); using avhrr geometry", sat, attempt, err)
                    fallen_back.add(attempt)
                elif attempt == "avhrr":
                    logger.warning("No geometry for %s %s: %s", sat, p["start"], err)
    for sat in sorted(missing):
        logger.warning("No TLE found for %s; passes drawn without orbit/coverage", sat)


def load_coastlines(path, step):
    """Return a list of lon/lat polylines from a shapefile (or Natural Earth via cartopy)."""
    if path is None:
        try:
            import cartopy.io.shapereader as shpreader
            path = shpreader.natural_earth(resolution="110m", category="cultural",
                                           name="admin_0_countries")
        except Exception as err:  # noqa: BLE001
            logger.warning("No coastlines available (%s); map drawn without them", err)
            return []
    try:
        import shapefile
        reader = shapefile.Reader(str(path))
        geoms = [s.__geo_interface__ for s in reader.shapes()]
    except ImportError:
        import cartopy.io.shapereader as shpreader
        from shapely.geometry import mapping
        geoms = [mapping(g) for g in shpreader.Reader(str(path)).geometries()]

    lines = []
    for geometry in geoms:
        for ring in _geometry_rings(geometry):
            points = [[round(x, 2), round(y, 2)] for x, y in ring[::step]]
            if len(points) > 2:
                lines.append(points)
    return lines


def _geometry_rings(geometry):
    geometry_type, coordinates = geometry["type"], geometry["coordinates"]
    if geometry_type == "LineString":
        yield coordinates
    elif geometry_type in ("Polygon", "MultiLineString"):
        yield from coordinates
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            yield from polygon


def to_json_passes(passes):
    """Convert passes to the timeline's JSON-compatible representation."""
    out = []
    for p in passes:
        d = {
            "sat": p["satellite"],
            "name": DISPLAY_NAMES.get(p["satellite"], p["satellite"].upper()),
            "ant": p["antenna"],
            "station": p["station"],
            "s": p["start"].replace(tzinfo=timezone.utc).timestamp(),
            "e": p["end"].replace(tzinfo=timezone.utc).timestamp(),
        }
        if "orbit" in p:
            d["orbit"] = p["orbit"]
        if "coverage" in p:
            d["cov"] = p["coverage"]
        if p.get("unscheduled"):
            d["un"] = 1
        if "full" in p:
            d["fs"] = p["full"][0].replace(tzinfo=timezone.utc).timestamp()
            d["fe"] = p["full"][1].replace(tzinfo=timezone.utc).timestamp()
            if "full_coverage" in p:
                d["fcov"] = p["full_coverage"]
        out.append(d)
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fff;--fg:#1b1b1b;--muted:#6b6b6b;--line:#e2e2e2;--row:#f3f3f3;--tip:#fff;--sea:#dbe7f3;--land:#f4f1e6;--border:#8a8a8a}
@media (prefers-color-scheme:dark){:root{
  --bg:#1c1c1e;--fg:#ececec;--muted:#a0a0a0;--line:#333;--row:#262628;
  --tip:#2a2a2c;--sea:#223044;--land:#3a3a3a;--border:#777}}
html,body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{display:flex;gap:16px;align-items:center;flex-wrap:wrap;padding:10px 16px;
  border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:3}
header h1{font-size:16px;font-weight:600;margin:0 8px 0 0}
.sw{display:inline-block;width:14px;height:10px;border-radius:2px;vertical-align:-1px;margin-right:5px}
.legend span{margin-right:12px;color:var(--muted);font-size:13px}
.ctl button{font:inherit;font-size:13px;padding:3px 10px;border:1px solid var(--line);
  background:var(--bg);color:var(--fg);border-radius:6px;cursor:pointer}
.ctl button:hover{background:var(--row)}
#filters{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--muted)}
#filters label{cursor:pointer;white-space:nowrap}
#wrap{position:relative}
svg{display:block;width:100%;user-select:none}
.bar{cursor:pointer}
.bar.dim rect{opacity:.25}
.bar:hover rect{stroke:var(--fg);stroke-width:1.5}
.bar text{pointer-events:none;font-size:11px;fill:#1b1b1b}
.bar rect{stroke:rgba(0,0,0,.25);stroke-width:.5}
.bar.un rect{stroke:rgba(128,128,128,.6);stroke-dasharray:3 2}
.bar.un text{fill:var(--muted)}
#tip{display:none;position:absolute;z-index:5;pointer-events:none;background:var(--tip);
  border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:12px;
  line-height:1.45;box-shadow:0 4px 14px rgba(0,0,0,.18);width:300px}
#tip b{font-size:13px}
#tip canvas{display:block;margin-top:8px;border-radius:50%}
#status{color:var(--muted);font-size:12px;margin-left:auto}
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="legend" id="legend"></div>
  <div class="ctl">
    <button id="today">Today</button>
    <button id="week">Whole week</button>
    <button id="now">Now</button>
  </div>
  <span id="status"></span>
</header>
<div id="filters" style="padding:6px 16px"></div>
<div id="wrap"><svg id="g" xmlns="http://www.w3.org/2000/svg"></svg><div id="tip"></div></div>
<script>
const DATA = __DATA__;
// ColorBrewer Set3
const ANT_COLORS = ["#8dd3c7","#ffffb3","#bebada","#fb8072","#80b1d3","#fdb462",
                    "#b3de69","#fccde5","#d9d9d9","#bc80bd","#ccebc5","#ffed6f"];
const antennas = [...new Set(DATA.passes.filter(p=>!p.un).map(p=>p.ant))].sort();
const antColor = Object.fromEntries(antennas.map((a,i)=>[a,ANT_COLORS[i%ANT_COLORS.length]]));

// merge identical passes requested on several antennas
const merged = new Map();
for (const p of DATA.passes) {
  const k = p.un ? "un|"+p.sat+"|"+p.s : p.sat+"|"+p.s+"|"+p.e;
  if (merged.has(k)) merged.get(k).ants.push(p.ant);
  else merged.set(k, Object.assign({ants:[p.ant]}, p));
}
// Unscheduled first, so they sit behind.
const passes = [...merged.values()].sort((a,b)=>(b.un||0)-(a.un||0) || a.s-b.s);
const sats = [...new Set(passes.map(p=>p.sat))].sort();
const satName = Object.fromEntries(passes.map(p=>[p.sat,p.name]));

// per-antenna overlap detection
for (const a of antennas) {
  const list = passes.filter(p=>!p.un && p.ants.includes(a)).sort((x,y)=>x.s-y.s);
  for (let i=1;i<list.length;i++) if (list[i].s < list[i-1].e) { list[i].conflict=list[i-1].conflict=true; }
}

const L=86, R=12, T=44, RH=26, PAD=6;
let W=1200, H=T+sats.length*RH+PAD;
let t0=DATA.span[0], t1=DATA.span[1];
const hidden = new Set();
const svg=document.getElementById("g"), tip=document.getElementById("tip"), wrap=document.getElementById("wrap");

function X(t){return L+(t-t0)/(t1-t0)*(W-L-R)}
function pad(n){return (n<10?"0":"")+n}
function hhmm(t){const d=new Date(t*1000);return pad(d.getUTCHours())+":"+pad(d.getUTCMinutes())}
function hhmmss(t){const d=new Date(t*1000);return hhmm(t)+":"+pad(d.getUTCSeconds())}
function ymd(t){const d=new Date(t*1000);return d.toISOString().slice(0,10)}
function dayLabel(t){
  const d=new Date(t*1000);return ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][d.getUTCDay()]+" "+ymd(t)}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}

function draw(){
  W = wrap.clientWidth || 1200;
  svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
  svg.setAttribute("height",H);
  let o=`<defs><clipPath id="cp"><rect x="${L}" y="0" width="${W-L-R}" height="${H}"/></clipPath>`;
  // striped fills for passes on several antennas
  const combos=new Set(passes.map(p=>p.ants.slice().sort().join("+")).filter(c=>c.includes("+")));
  for (const c of combos){
    const cols=c.split("+").map(a=>antColor[a]); const w=4*cols.length;
    o+=`<pattern id="pat-${c.replace(/[^a-z0-9]/gi,"_")}" width="${w}" height="${w}" `+
      `patternUnits="userSpaceOnUse" patternTransform="rotate(45)">`;
    cols.forEach((col,i)=>o+=`<rect x="${i*4}" width="4" height="${w}" fill="${col}"/>`);
    o+=`</pattern>`;
  }
  o+=`</defs>`;
  sats.forEach((s,i)=>{const y=T+i*RH;
    o+=`<rect x="0" y="${y}" width="${W}" height="${RH}" fill="${i%2?'var(--row)':'transparent'}"/>`;
    o+=`<text x="8" y="${y+17}" font-size="12" fill="var(--fg)" font-weight="500">${esc(satName[s])}</text>`;});
  o+=`<g clip-path="url(#cp)">`;
  const span=t1-t0;
  const pxPerSec=(W-L-R)/span;
  const step=[60,300,600,900,1800,3600,2*3600,3*3600,6*3600,12*3600].find(st=>st*pxPerSec>=64)||12*3600;
  // day boundaries + labels
  for (let d=Math.floor(t0/86400)*86400; d<=t1; d+=86400){
    const x=X(d);
    o+=`<line x1="${x}" y1="0" x2="${x}" y2="${H}" stroke="var(--border)" stroke-width="1"/>`;
    o+=`<text x="${Math.max(x,L)+4}" y="14" font-size="12" fill="var(--fg)" font-weight="600">${dayLabel(d)}</text>`;
  }
  for (let t=Math.ceil(t0/step)*step; t<=t1; t+=step){
    const x=X(t); if (t%86400===0) continue;
    o+=`<line x1="${x}" y1="${T-6}" x2="${x}" y2="${H}" stroke="var(--line)" stroke-width="1"/>`;
    o+=`<text x="${x+3}" y="${T-10}" font-size="11" fill="var(--muted)">${hhmm(t)}</text>`;
  }
  passes.forEach((p,i)=>{
    if (p.e<t0||p.s>t1) return;
    const y=T+sats.indexOf(p.sat)*RH+5, x=X(p.s), w=Math.max(2,X(p.e)-x);
    const key=p.ants.slice().sort().join("+");
    const fill=p.un?"var(--row)":p.ants.length>1?`url(#pat-${key.replace(/[^a-z0-9]/gi,"_")})`:antColor[p.ants[0]];
    const dim=(hidden.has(p.sat)?" dim":"")+(p.un?" un":"");
    const stroke=p.conflict?' stroke="#E24B4A" stroke-width="2"':'';
    o+=`<g class="bar${dim}" data-i="${i}">`;
    if (p.fs!==undefined){ const fx=X(p.fs), fw=Math.max(2,X(p.fe)-fx);
      o+=`<rect x="${fx}" y="${y+3}" width="${fw}" height="${RH-16}" rx="2" fill="var(--row)" `+
        `stroke="rgba(128,128,128,.6)" stroke-dasharray="3 2"/>`; }
    o+=`<rect x="${x}" y="${y}" width="${w}" height="${RH-10}" rx="3" fill="${fill}"${stroke}/>`;
    if (p.orbit!==undefined && w>44) o+=`<text x="${x+w/2}" y="${y+12}" text-anchor="middle">${p.orbit}</text>`;
    o+=`</g>`;
  });
  const now=Date.now()/1000;
  if (now>t0&&now<t1) o+=`<line x1="${X(now)}" y1="0" x2="${X(now)}" y2="${H}" stroke="#E24B4A" stroke-width="1.5"/>`;
  o+=`</g><line x1="${L}" y1="${T}" x2="${W}" y2="${T}" stroke="var(--border)" stroke-width="1"/>`;
  svg.innerHTML=o;
  const nUn=passes.filter(p=>p.un).length;
  document.getElementById("status").textContent=`${ymd(t0)} ${hhmm(t0)} → ${ymd(t1)} ${hhmm(t1)} UTC · `+
    `${passes.length-nUn} scheduled, ${nUn} not`;
}

// ---- legend and filters
const legend=document.getElementById("legend");
legend.innerHTML=antennas.map(a=>`<span><i class="sw" style="background:${antColor[a]}"></i>${esc(a)}</span>`).join("")+
  (antennas.length>1?`<span><i class="sw" style="background:repeating-linear-gradient(45deg,${
    antennas.map((a,i)=>`${antColor[a]} ${i*3}px ${(i+1)*3}px`).join(",")})"></i>several antennas</span>`:"")+
  `<span><i class="sw" style="border:2px solid #E24B4A;box-sizing:border-box"></i>overlap within one antenna</span>`+
  (passes.some(p=>p.un)?`<span><i class="sw" style="background:var(--row);border:1px dashed var(--muted);`+
    `box-sizing:border-box"></i>not scheduled</span>`:"");
const filters=document.getElementById("filters");
filters.innerHTML=`<label><input type="checkbox" id="all" checked> all</label>`+
  sats.map(s=>`<label><input type="checkbox" data-sat="${s}" checked> ${esc(satName[s])}</label>`).join("");
filters.addEventListener("change",e=>{
  if (e.target.id==="all"){ filters.querySelectorAll("[data-sat]").forEach(c=>{
    c.checked=e.target.checked; e.target.checked?hidden.delete(c.dataset.sat):hidden.add(c.dataset.sat);}); }
  else { e.target.checked?hidden.delete(e.target.dataset.sat):hidden.add(e.target.dataset.sat); }
  draw();
});

// ---- zoom / pan
svg.addEventListener("wheel",ev=>{ev.preventDefault();
  const r=svg.getBoundingClientRect(); const fx=(ev.clientX-r.left)/r.width*W;
  const tc=t0+(fx-L)/(W-L-R)*(t1-t0); const k=ev.deltaY>0?1.25:0.8;
  const ns=Math.min(DATA.span[1]-DATA.span[0]+2*3600, Math.max(1800,(t1-t0)*k));
  t0=tc-(tc-t0)*ns/(t1-t0); t1=t0+ns; draw();},{passive:false});
let dragX=null, moved=false;
svg.addEventListener("mousedown",ev=>{dragX=ev.clientX;moved=false});
window.addEventListener("mouseup",()=>{dragX=null});
svg.addEventListener("mousemove",ev=>{
  if (dragX!==null){ const r=svg.getBoundingClientRect(); const dt=(ev.clientX-dragX)/r.width*W/(W-L-R)*(t1-t0);
    if (Math.abs(ev.clientX-dragX)>2) moved=true;
    t0-=dt;t1-=dt;dragX=ev.clientX;draw(); tip.style.display="none"; return; }
  const g=ev.target.closest(".bar"); if(!g){tip.style.display="none";return;}
  showTip(passes[+g.dataset.i], ev);
});
svg.addEventListener("mouseleave",()=>{tip.style.display="none"});
svg.addEventListener("click",ev=>{ if (moved) return; const g=ev.target.closest(".bar"); if(!g) return;
  window.open(location.pathname+"?pass="+encodeURIComponent(passId(passes[+g.dataset.i])),"_blank"); });
document.getElementById("today").onclick=()=>{const d=Math.floor(Date.now()/86400000)*86400; t0=d; t1=d+86400; draw();};
document.getElementById("week").onclick=()=>{t0=DATA.span[0]; t1=DATA.span[1]; draw();};
document.getElementById("now").onclick=()=>{
  const n=Date.now()/1000, s=Math.min(t1-t0,6*3600); t0=n-s/3; t1=t0+s; draw();};
window.addEventListener("resize",draw);

// ---- near-sided perspective map
const MAP=DATA.map; let SZ=256;
const lat0=MAP.lat*Math.PI/180, lon0=MAP.lon*Math.PI/180, P=(6371+MAP.height_km)/6371;
const cosL=Math.cos(lat0), sinL=Math.sin(lat0);
const rmax = P/(P+1)*Math.sqrt(1-1/(P*P)); // disc radius at the horizon, in R units
let SCALE=(SZ/2-2)/rmax;
function setMapSize(n){ if(n!==SZ){ SZ=n; SCALE=(SZ/2-2)/rmax; base=null; } }
function proj(lon,lat){ // [x,y,visible]; hidden points are clamped onto the horizon rim
  const la=lat*Math.PI/180, lo=lon*Math.PI/180-lon0;
  const cosc = sinL*Math.sin(la)+cosL*Math.cos(la)*Math.cos(lo);
  let x=Math.cos(la)*Math.sin(lo), y=cosL*Math.sin(la)-sinL*Math.cos(la)*Math.cos(lo);
  const vis = cosc >= 1/P;
  if (vis){ const k=(P-1)/(P-cosc); x*=k; y*=k; }
  else { const n=Math.hypot(x,y)||1e-9; x*=rmax/n; y*=rmax/n; }
  return [SZ/2+x*SCALE, SZ/2-y*SCALE, vis];
}
function ringPath(c, ring, close){ // trace a ring, walking the rim between consecutive hidden points
  let any=false, prev=null;
  for (const [lon,lat] of ring){
    const q=proj(lon,lat); any=any||q[2];
    if (prev && !q[2] && !prev[2]){ // both on the rim: follow the rim the short way
      let a0=Math.atan2(prev[1]-SZ/2,prev[0]-SZ/2), a1=Math.atan2(q[1]-SZ/2,q[0]-SZ/2);
      let d=a1-a0; while(d>Math.PI)d-=2*Math.PI; while(d<-Math.PI)d+=2*Math.PI;
      const n=Math.ceil(Math.abs(d)/0.1);
      for(let i=1;i<n;i++){const a=a0+d*i/n; c.lineTo(SZ/2+rmax*SCALE*Math.cos(a),SZ/2+rmax*SCALE*Math.sin(a));}
    }
    prev?c.lineTo(q[0],q[1]):c.moveTo(q[0],q[1]); prev=q;
  }
  if (close) c.closePath();
  return any;
}
function toXYZ(lon,lat){const la=lat*Math.PI/180,lo=lon*Math.PI/180;
  return [Math.cos(la)*Math.cos(lo),Math.cos(la)*Math.sin(lo),Math.sin(la)]}
function fromXYZ(v){const n=Math.hypot(v[0],v[1],v[2]);
  return [Math.atan2(v[1],v[0])*180/Math.PI, Math.asin(v[2]/n)*180/Math.PI]}
function densify(ring, n){ // great-circle interpolation between consecutive vertices
  const out=[]; for(let i=0;i<ring.length;i++){const a=toXYZ(...ring[i]), b=toXYZ(...ring[(i+1)%ring.length]);
    for(let j=0;j<n;j++){const f=j/n;
      out.push(fromXYZ([a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f,a[2]+(b[2]-a[2])*f]));}} return out;
}
function cssVar(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim()}
var base=null;
function drawBase(){
  base=document.createElement("canvas"); base.width=base.height=SZ; const c=base.getContext("2d");
  c.fillStyle=cssVar("--sea"); c.beginPath(); c.arc(SZ/2,SZ/2,SZ/2-2,0,2*Math.PI); c.fill();
  c.fillStyle=cssVar("--land"); c.strokeStyle=cssVar("--border"); c.lineWidth=0.6;
  c.save(); c.beginPath(); c.arc(SZ/2,SZ/2,SZ/2-2,0,2*Math.PI); c.clip();
  for (const ring of MAP.lines){ c.beginPath(); if (ringPath(c, ring, true)){ c.fill(); c.stroke(); } }
  c.restore();
  // graticule
  c.strokeStyle="rgba(128,128,128,.35)"; c.lineWidth=0.5;
  for(let lat=-80;lat<=80;lat+=20){c.beginPath();let pen=false;
    for(let lon=-180;lon<=180;lon+=2){const q=proj(lon,lat);if(!q[2]){pen=false;continue;}
      pen?c.lineTo(q[0],q[1]):c.moveTo(q[0],q[1]);pen=true;}c.stroke();}
  for(let lon=-180;lon<180;lon+=30){c.beginPath();let pen=false;
    for(let lat=-90;lat<=90;lat+=2){const q=proj(lon,lat);if(!q[2]){pen=false;continue;}
      pen?c.lineTo(q[0],q[1]):c.moveTo(q[0],q[1]);pen=true;}c.stroke();}
  const st=proj(MAP.lon,MAP.lat); c.fillStyle="#E24B4A"; c.beginPath(); c.arc(st[0],st[1],3,0,2*Math.PI); c.fill();
}
function showTip(p, ev){
  setMapSize(256);
  tip.innerHTML=passInfoHtml(p)+(p.cov?`<canvas width="${SZ}" height="${SZ}"></canvas>`:
    `<div style="color:var(--muted)">no coverage (no TLE)</div>`)+
    `<div style="color:var(--muted);margin-top:6px">click to open in a new tab</div>`;
  if (p.cov) drawPassMap(tip.querySelector("canvas"), p);
  tip.style.display="block";
  const r=wrap.getBoundingClientRect(); const tw=tip.offsetWidth, th=tip.offsetHeight;
  let x=ev.clientX-r.left+14, y=ev.clientY-r.top+14;
  if (x+tw>r.width) x=ev.clientX-r.left-tw-14;
  if (ev.clientY+14+th>window.innerHeight) y=Math.max(-r.top+8, ev.clientY-r.top-th-14);
  tip.style.left=x+"px"; tip.style.top=y+"px";
}
function drawPassMap(canvas, p){
    if(!base) drawBase();
    const c=canvas.getContext("2d"); c.drawImage(base,0,0);
    const col=p.un?"#d9d9d9":antColor[p.ants[0]];
    c.save(); c.beginPath(); c.arc(SZ/2,SZ/2,SZ/2-2,0,2*Math.PI); c.clip();
    if (p.fcov){ c.strokeStyle="#777"; c.fillStyle="rgba(128,128,128,.35)"; c.lineWidth=1; c.setLineDash([3,2]);
      c.beginPath(); ringPath(c, densify(p.fcov,8), true); c.fill(); c.stroke(); c.setLineDash([]); }
    c.strokeStyle="#333";
    c.fillStyle=p.un||p.ants.length<2?col+"66":stripePattern(c, p.ants.map(a=>antColor[a]+"66")); c.lineWidth=1.5;
    c.beginPath(); ringPath(c, densify(p.cov,8), true); c.fill(); c.stroke(); c.restore();
}
function stripePattern(c, cols){ // diagonal stripes, one per antenna, as a canvas fill
  const w=Math.max(4, Math.round(SZ/40)), n=cols.length, pc=document.createElement("canvas"); pc.width=w*n; pc.height=w;
  const g=pc.getContext("2d"); cols.forEach((col,i)=>{ g.fillStyle=col; g.fillRect(i*w,0,w,w); });
  const pat=c.createPattern(pc,"repeat"); pat.setTransform(new DOMMatrix().rotate(45)); return pat;
}
function passId(p){return p.sat+"-"+Math.round(p.s)}
function passInfoHtml(p){
  const ants=p.un?"not scheduled":"on "+p.ants.join(" + "), dur=Math.round(p.e-p.s);
  return `<b>${esc(p.name)}</b> <span style="color:var(--muted)">${esc(ants)}${
    p.orbit!==undefined?` · orbit ${p.orbit}`:""}</span>`+
    `<div>${ymd(p.s)} &nbsp; AOS ${hhmmss(p.s)} → LOS ${hhmmss(p.e)} UTC</div>`+
    `<div>${Math.floor(dur/60)} min ${dur%60} s · station ${esc(p.station)}${
      p.conflict?' · <span style="color:#E24B4A">overlaps another pass</span>':""}</div>`+
    (p.fs!==undefined?`<div style="color:var(--muted)">trimmed: visible ${hhmmss(p.fs)} → ${hhmmss(p.fe)}, `+
      `${Math.max(0,Math.round(p.s-p.fs))} s cut at start, ${Math.max(0,Math.round(p.fe-p.e))} s at end</div>`:"");
}
// ---- single-pass page (schedule.html?pass=<sat>-<unix AOS>)
function showPassPage(id){
  const p=passes.find(q=>passId(q)===id);
  document.body.innerHTML="";
  const el=document.createElement("div");
  el.style.cssText="max-width:900px;margin:0 auto;padding:16px 24px;font-size:15px";
  if (!p){ el.innerHTML=`<p>No pass with id <code>${esc(id)}</code>.</p>`+
    `<p><a href="${location.pathname}">Back to the schedule</a></p>`; document.body.appendChild(el); return; }
  document.title=`${p.name} ${ymd(p.s)} ${hhmm(p.s)} UTC`;
  el.innerHTML=`<p><a href="${location.pathname}">← schedule</a></p>`+
    `<div style="font-size:16px">${passInfoHtml(p)}</div>`;
  const size=Math.min(760, window.innerWidth-48);
  if (p.cov){ const cv=document.createElement("canvas"); cv.width=cv.height=size;
    cv.style.cssText="display:block;margin:16px auto;border-radius:50%";
    el.appendChild(cv); setMapSize(size); drawPassMap(cv, p); }
  else el.insertAdjacentHTML("beforeend",`<p style="color:var(--muted)">No coverage available (no TLE).</p>`);
  document.body.appendChild(el);
}
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change",()=>{base=null});

const wanted=new URLSearchParams(location.search).get("pass");
if (wanted) showPassPage(wanted);
else {
  document.getElementById("today").click();
  if (!(Date.now()/1000>DATA.span[0] && Date.now()/1000<DATA.span[1])) document.getElementById("week").click();
}
</script>
</body>
</html>
"""


def build_html(passes, span, coastlines, args):
    """Embed schedule and map data in the self-contained timeline page."""
    data = {
        "passes": to_json_passes(passes),
        "span": [span[0].replace(tzinfo=timezone.utc).timestamp(),
                 span[1].replace(tzinfo=timezone.utc).timestamp()],
        "map": {"lat": args.lat, "lon": args.lon, "height_km": args.view_height,
                "lines": coastlines},
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    title = args.title or f"Pass schedule {span[0]:%Y-%m-%d} → {span[1]:%Y-%m-%d}"
    html = TEMPLATE.replace("__TITLE__", title)
    html = html.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    return html


def kv_pairs(values):
    """Parse key=value arguments into a dictionary, stripping surrounding whitespace."""
    out = {}
    for item in values or []:
        k, _, v = item.partition("=")
        out[k.strip()] = v.strip()
    return out


def main(argv=None):
    """Run the script."""
    parser = arg_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    if not args.verbose:
        logging.getLogger("trollsched").setLevel(logging.WARNING)

    passes, starts, ends = [], [], []
    for path in args.schedules:
        props, plist, span = parse_schedule(path)
        logger.info("%s: antenna %s, %d passes", path, props.get("antenna"), len(plist))
        passes.extend(plist)
        starts.append(span[0])
        ends.append(span[1])
    span = (min(starts), max(ends))

    tle_lookup = load_tles(args.tle, kv_pairs(args.alias)) if args.tle else None
    if not tle_lookup:
        logger.warning("No --tle given: no orbit numbers or coverage maps")

    horizon = 0.0
    if args.lat is None or args.lon is None:
        guess = estimate_station(passes, tle_lookup) if tle_lookup else None
        if guess is None:
            parser.error("--lat and --lon are required when no TLE file is given")
        args.lon, args.lat, horizon = guess
        logger.info("Station estimated at %.2f N, %.2f E, horizon %.1f deg (override with --lat/--lon)",
                    args.lat, args.lon, horizon)

    if tle_lookup and not args.no_unscheduled:
        extra = unscheduled_passes(passes, span, tle_lookup, args.lon, args.lat, horizon)
        logger.info("%d passes over the station are not in the schedule, %d scheduled passes are trimmed",
                    len(extra), sum("full" in p for p in passes))
        passes.extend(extra)
    if tle_lookup:
        add_geometry(passes, tle_lookup, {}, COVERAGE_POINTS)

    coastlines = load_coastlines(args.coastlines, COASTLINE_STEP)
    html = build_html(passes, span, coastlines, args)
    Path(args.output).write_text(html, encoding="utf-8")
    logger.info("Wrote %s (%.0f kB)", args.output, len(html) / 1024)


def arg_parser():
    """Create the argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("schedules", nargs="+", help="acquisition-schedule request XML files")
    parser.add_argument("-o", "--output", default="schedule.html")
    parser.add_argument("--tle", help="TLE file (needed for orbit numbers and coverage)")
    parser.add_argument("--lat", type=float, help="station latitude for the map centre "
                        "(default: estimated from the passes and the TLEs)")
    parser.add_argument("--lon", type=float, help="station longitude for the map centre")
    parser.add_argument("--view-height", type=float, default=GEO_ALTITUDE_KM,
                        help="height of the near-sided perspective viewpoint, km (default: geostationary)")
    parser.add_argument("--coastlines", help="shapefile with coastlines/countries "
                        "(default: Natural Earth 110m via cartopy)")
    parser.add_argument("--no-unscheduled", action="store_true",
                        help="do not compute and show the passes left out of the schedule")
    parser.add_argument("--alias", action="append", metavar="SAT=TLENAME",
                        help="map a schedule satellite name to a TLE name")
    parser.add_argument("--title")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


if __name__ == "__main__":
    sys.exit(main())
