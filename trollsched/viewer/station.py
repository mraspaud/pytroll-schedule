"""Build the viewer page from inside the scheduler, where passes, station and area are already known."""

import logging
from datetime import timedelta
from pathlib import Path

import numpy as np

from trollsched.viewer import build_page, geo
from trollsched.viewer.records import ScheduledEntry, build_records, normalize, schedule_name
from trollsched.viewer.sources import load_tles, read_schedule, visible_passes

logger = logging.getLogger(__name__)


def scheduled_entries(reception_passes, antenna):
    """Turn the passes selected for reception into schedule entries for *antenna*."""
    return [ScheduledEntry(schedule_name(p), antenna, p.risetime, p.falltime, overpass=p)
            for p in reception_passes if getattr(p, "rec", False)]


def avoid_entries(avoid_files):
    """Read the avoid lists, each one being what another antenna will receive."""
    entries = []
    for path in avoid_files or []:
        _, file_entries, _ = read_schedule(path)
        entries.extend(file_entries)
    return entries


def untrimmed(passes):
    """Get the original (untrimmed) pass of every pass, without duplicates."""
    originals = {}
    for overpass in passes:
        original = getattr(overpass, "original", overpass)
        originals.setdefault(id(original), original)
    return list(originals.values())


def extra_visible_passes(full_passes, entries, span, coords, tle_file, horizon=0.0):
    """Compute the visibility windows of satellites that are only in the avoid lists."""
    known = {normalize(schedule_name(p)) for p in full_passes}
    missing = {e.satellite for e in entries if normalize(e.satellite) not in known}
    if not missing:
        return []
    if not tle_file or not Path(tle_file).exists():
        logger.warning("No TLE file; passes of %s (avoid lists only) cannot be computed", ", ".join(sorted(missing)))
        return []
    return visible_passes(missing, span[0], span[1], coords, load_tles(tle_file), horizon)


def area_outline(area):
    """Get the lon/lat ring of an area of interest, or None when it has no usable boundary."""
    try:
        boundary = area.boundary(8)
    except (AttributeError, TypeError):
        return None
    try:
        lons, lats = boundary.contour()
    except AttributeError:
        try:
            vertices = np.degrees(boundary.contour_poly.vertices)
        except AttributeError:
            return None
        lons, lats = vertices[:, 0], vertices[:, 1]
    return geo.ring_points(np.asarray(lons).ravel(), np.asarray(lats).ravel())


def station_page(station, allpasses, reception_passes, avoid_files, span, delay, tle_file=None,
                 coastlines_file=None, title=None, sources=()):
    """Build the viewer page for one station of a scheduling run.

    Args:
        station: the ``Station`` being scheduled (coords, antenna, area, local horizon).
        allpasses: every pass considered (possibly trimmed; their originals give the visibility windows).
        reception_passes: the passes with their ``rec`` flag set after scheduling.
        avoid_files: XML schedules of the other antennas.
        span: (start, end) of the schedule.
        delay: antenna switching delay.
        tle_file: TLE file, used for satellites that only appear in avoid lists.
        coastlines_file: shapefile for the map background, or None for Natural Earth via cartopy.
        title: page title.
        sources: input file names shown in the header.
    """
    antenna = getattr(station, "antenna", None) or station.id
    entries = scheduled_entries(reception_passes, antenna) + avoid_entries(avoid_files)
    full = untrimmed(allpasses)
    full += extra_visible_passes(full, entries, span, station.coords, tle_file, getattr(station, "local_horizon", 0))
    records = build_records(full, entries, station.coords, station=station.id, area=station.area,
                            delay=delay if isinstance(delay, timedelta) else timedelta(seconds=delay))
    logger.info("Viewer: %d scheduled passes, %d not scheduled, %d trimmed",
                sum("un" not in r for r in records), sum("un" in r for r in records),
                sum("fs" in r for r in records))
    return build_page(records, span, station.coords, coastlines=geo.load_coastlines(coastlines_file),
                      area_outline=area_outline(station.area), title=title, sources=sources)
