#!/usr/bin/env python3
"""Render acquisition-schedule XML files as a self-contained HTML timeline.

Usage:
    schedule_viewer.py --tle tle.txt -o schedule.html request_meos.xml request_cgi.xml

Each XML file is one antenna.  The station position is estimated from the
passes unless given, visibility windows are recomputed from the TLEs so that
passes left out of the schedule and trimmed passes can be shown too.
"""

import argparse
import logging
import sys
from pathlib import Path

from trollsched.viewer import GEO_ALTITUDE_KM, build_page
from trollsched.viewer.geo import load_coastlines
from trollsched.viewer.records import build_records
from trollsched.viewer.sources import estimate_station, load_tles, read_schedule, visible_passes

logger = logging.getLogger("schedule_viewer")


def kv_pairs(values):
    """Turn ``["a=b", ...]`` into a dict."""
    out = {}
    for item in values or []:
        key, _, value = item.partition("=")
        out[key.strip()] = value.strip()
    return out


def parse_args(argv=None):
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("schedules", nargs="+", help="acquisition-schedule request XML files, one per antenna")
    parser.add_argument("-o", "--output", default="schedule.html")
    parser.add_argument("--tle", help="TLE file (needed for orbit numbers, coverage and unscheduled passes)")
    parser.add_argument("--lat", type=float, help="station latitude (default: estimated from the passes)")
    parser.add_argument("--lon", type=float, help="station longitude")
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
    return parser.parse_args(argv)


def main(argv=None):
    """Run the script."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    if not args.verbose:
        logging.getLogger("trollsched").setLevel(logging.WARNING)

    entries, starts, ends = [], [], []
    for path in args.schedules:
        properties, file_entries, span = read_schedule(path)
        logger.info("%s: antenna %s, %d passes", path, file_entries[0].antenna if file_entries else "?",
                    len(file_entries))
        entries.extend(file_entries)
        starts.append(span[0])
        ends.append(span[1])
    span = (min(starts), max(ends))

    if not args.tle:
        if args.lat is None or args.lon is None:
            logger.error("--lat and --lon are required when no TLE file is given")
            return 2
        logger.warning("No --tle given: no orbit numbers, coverage or unscheduled passes")
        records = [{"sat": e.satellite, "name": e.satellite.upper(), "ant": e.antenna, "station": "",
                    "s": e.start.timestamp(), "e": e.end.timestamp()} for e in entries]
        coords = (args.lon, args.lat, 0.0)
    else:
        tle_lookup = load_tles(args.tle, kv_pairs(args.alias))
        horizon = 0.0
        if args.lat is None or args.lon is None:
            guess = estimate_station(entries, tle_lookup)
            if guess is None:
                logger.error("Station position could not be estimated; give --lat and --lon")
                return 2
            args.lon, args.lat, horizon = guess
            logger.info("Station estimated at %.2f N, %.2f E, horizon %.1f deg (override with --lat/--lon)",
                        args.lat, args.lon, horizon)
        coords = (args.lon, args.lat, 0.0)
        satellites = {e.satellite for e in entries}
        full = visible_passes(satellites, span[0], span[1], coords, tle_lookup, horizon)
        if args.no_unscheduled:
            full = [p for p in full if any(e.satellite == p.satellite.name and e.overlaps(p.risetime, p.falltime)
                                           for e in entries)]
        station = properties.get("station", "")
        records = build_records(full, entries, coords, station=station)
        logger.info("%d scheduled passes, %d not scheduled, %d trimmed",
                    sum("un" not in r for r in records), sum("un" in r for r in records),
                    sum("fs" in r for r in records))

    page = build_page(records, span, coords, coastlines=load_coastlines(args.coastlines), title=args.title,
                      view_height=args.view_height, sources=[Path(p).name for p in args.schedules])
    Path(args.output).write_text(page, encoding="utf-8")
    logger.info("Wrote %s (%.0f kB)", args.output, len(page) / 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
