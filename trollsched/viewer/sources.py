"""Inputs for the viewer that are not available from the scheduler itself.

Reading acquisition schedules, computing visibility windows from TLEs, and
estimating the station position when it is not known.
"""

import glob
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import defusedxml.ElementTree as ET
import numpy as np

from trollsched.viewer import geo
from trollsched.viewer.records import ScheduledEntry, normalize

logger = logging.getLogger(__name__)

TIME_FMT = "%Y-%m-%d-%H:%M:%S"

# Schedule name -> TLE name(s), when normalisation alone is not enough.
TLE_ALIASES = {
    "npp": ("SUOMI NPP", "NPP"),
    "aws-pfm": ("ARCTIC WEATHER SATELLITE", "AWS", "AWS-PFM"),
    "sga1": "METOP-SGA1",
    "sgb1": "METOP-SGB1",
    "fy3d": "FENGYUN 3D",
    "fy3e": "FENGYUN 3E",
    "fy3f": "FENGYUN 3F",
    "fy3g": "FENGYUN 3G",
    "fy3h": "FENGYUN 3H",
}

# Schedule name -> instrument used for the swath geometry.
INSTRUMENTS = {
    "noaa20": "viirs", "noaa21": "viirs", "noaa22": "viirs", "npp": "viirs",
    "aqua": "modis", "terra": "modis",
    "fy3d": "mersi-2", "fy3e": "mersi-ll", "fy3f": "mersi-3", "fy3h": "mersi-3",
    "metop-a": "avhrr", "metop-b": "avhrr", "metop-c": "avhrr",
    "sga1": "metimage", "aws-pfm": "avhrr",
}


def read_schedule(path, default_antenna=None):
    """Read an acquisition schedule XML file.

    Returns ``(properties, entries, (file_start, file_end))``.  When the file
    has no antenna name, *default_antenna* or the file's stem is used.
    """
    root = ET.parse(path).getroot()
    properties = {child.tag: child.text for child in root.find("properties")}
    antenna = properties.get("antenna") or default_antenna or Path(path).stem
    entries = [ScheduledEntry(node.get("satellite"), antenna,
                              datetime.strptime(node.get("start-time"), TIME_FMT),
                              datetime.strptime(node.get("end-time"), TIME_FMT))
               for node in root.findall("pass")]
    span = (datetime.strptime(properties["file-start"], TIME_FMT),
            datetime.strptime(properties["file-end"], TIME_FMT))
    return properties, entries, span


def schedule_history(pattern, antenna, avoid_files=()):
    """Find the schedule files of previous runs.

    *pattern* is a glob for this station's own request files, which belong
    to *antenna*.  The other antennas' runs are found next to each avoid
    file: files whose names differ from it only in digits (the run date and
    time).  Like the avoid file itself, they belong to the antenna named in
    their properties, or failing that to the avoid file's stem.

    Returns ``(path, default_antenna)`` pairs, sorted by path within each group.
    """
    history = [(path, antenna) for path in sorted(glob.glob(pattern))]
    for avoid in avoid_files or ():
        avoid = Path(avoid)
        siblings = re.sub(r"\d+", "*", glob.escape(avoid.name))
        history.extend((path, avoid.stem) for path in sorted(glob.glob(str(avoid.parent / siblings))))
    return history


def read_properties(path):
    """Read only the ``<properties>`` of an acquisition schedule, which come before the passes."""
    properties = {}
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag == "properties":
            properties = {child.tag: child.text for child in element}
            break
    return properties


def request_files(files, since=None, until=None):
    """Keep the request files among *files* that cover some of the time between *since* and *until*.

    Only the properties of each file are read, so a directory with months of
    schedules costs little.  Returns ``(path, default_antenna, file_start)`` triples.
    """
    kept = []
    for path, default_antenna in files:
        properties = read_properties(path)
        if properties.get("type", "request") != "request":
            continue
        file_start = datetime.strptime(properties["file-start"], TIME_FMT)
        file_end = datetime.strptime(properties["file-end"], TIME_FMT)
        if (since is not None and file_end <= since) or (until is not None and file_start >= until):
            continue
        kept.append((path, default_antenna, file_start))
    return kept


def history_start(files):
    """Get the earliest ``file-start`` of the request files among *files*, or None without any."""
    return min((file_start for _, _, file_start in request_files(files)), default=None)


def plan_in_force(files, since, until):
    """Get the passes planned between *since* and *until*, as the antennas saw them.

    Schedules overlap: every run covers days, and a new one replaces the
    previous one from its own start.  So, for each antenna, a file counts
    for the passes starting between its ``file-start`` and the next file's.
    *files* are ``(path, default_antenna)`` pairs; report files are skipped.
    """
    by_antenna = {}
    for path, default_antenna, _ in request_files(files, since, until):
        properties, entries, (file_start, _) = read_schedule(path, default_antenna=default_antenna)
        by_antenna.setdefault(entries[0].antenna if entries else properties.get("antenna") or default_antenna,
                              []).append((file_start, entries))
    plan = []
    for runs in by_antenna.values():
        runs.sort(key=lambda run: run[0])
        for (file_start, entries), following in zip(runs, runs[1:] + [(until, [])]):
            end = min(following[0], until)
            plan.extend(e for e in entries if max(file_start, since) <= e.start < end)
    return sorted(plan, key=lambda e: (e.start, e.antenna))


def load_tles(path, aliases=None):
    """Read every TLE in *path*; return a lookup function from schedule name to ``Tle``."""
    from pyorbital.tlefile import Tle
    aliases = dict(TLE_ALIASES, **(aliases or {}))
    lines = [ln.rstrip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    tles = {}
    for i in range(0, len(lines) - 2, 3):
        tles[normalize(lines[i])] = Tle(lines[i], line1=lines[i + 1], line2=lines[i + 2])

    def lookup(satellite):
        names = aliases.get(satellite, ())
        candidates = [names] if isinstance(names, str) else list(names)
        for candidate in candidates + [satellite]:
            if normalize(candidate) in tles:
                return tles[normalize(candidate)]
        return None
    return lookup


def visible_passes(satellites, start, end, coords, tle_lookup, horizon=0.0, instruments=None):
    """Compute the visibility windows of *satellites* over the station between *start* and *end*.

    *satellites* are schedule names; *tle_lookup* comes from :func:`load_tles`.
    Returns ``Pass`` objects (untrimmed), skipping satellites without a TLE.
    """
    from pyorbital.orbital import Orbital

    from trollsched.satpass import Pass

    instruments = dict(INSTRUMENTS, **(instruments or {}))
    hours = int((end - start).total_seconds() // 3600) + 2
    lon, lat, alt = coords
    passes = []
    for satellite in sorted(set(satellites)):
        tle = tle_lookup(satellite)
        if tle is None:
            logger.warning("No TLE found for %s; its passes cannot be shown", satellite)
            continue
        orb = Orbital(satellite, line1=tle.line1, line2=tle.line2)
        for rise, fall, uptime in orb.get_next_passes(start - timedelta(hours=1), hours, lon, lat, alt,
                                                       horizon=max(horizon, 0.0)):
            if fall < start or rise > end:
                continue
            passes.append(Pass(satellite, rise.replace(microsecond=0), fall.replace(microsecond=0),
                               orb=orb, uptime=uptime, instrument=instruments.get(satellite, "avhrr")))
    return passes


def estimate_station(entries, tle_lookup, max_passes=60):
    """Guess the station position from the schedule itself.

    AOS and LOS of every pass are moments where the satellite sits on the
    station's horizon, so the position (and the horizon elevation) is found by
    least squares on the elevation at those times.  The mean of the mid-pass
    sub-satellite points gives the starting guess.

    Returns ``(lon, lat, horizon)`` or None when nothing can be computed.
    """
    from pyorbital.orbital import Orbital
    usable = [(entry, tle_lookup(entry.satellite)) for entry in entries]
    usable = [(entry, tle) for entry, tle in usable if tle is not None]
    if not usable:
        return None
    step = max(1, len(usable) // max_passes)
    sample = usable[::step][:max_passes]
    orbs = [(Orbital(entry.satellite, line1=tle.line1, line2=tle.line2), entry) for entry, tle in sample]
    mids = [geo.xyz(*orb.get_lonlatalt(entry.start + (entry.end - entry.start) / 2)[:2])[0]
            for orb, entry in orbs]
    guess = geo.lonlat(np.mean(mids, axis=0))
    try:
        from scipy.optimize import least_squares
    except ImportError:
        logger.warning("scipy not available; station guessed from mid-pass sub-points only")
        return guess[0], guess[1], 0.0

    def residuals(x):
        lon, lat, horizon = x
        return [orb.get_observer_look(t, lon, lat, 0.0)[1] - horizon
                for orb, entry in orbs for t in (entry.start, entry.end)]

    fit = least_squares(residuals, (guess[0], guess[1], 0.0), loss="soft_l1", f_scale=1.0,
                        bounds=([-180, -89, -10], [180, 89, 30]))
    rms = float(np.sqrt(np.mean(np.square(fit.fun))))
    if rms > 3:
        logger.warning("Station fit is poor (rms %.1f deg); give the position explicitly", rms)
    return round(float(fit.x[0]), 3), round(float(fit.x[1]), 3), round(float(fit.x[2]), 2)
