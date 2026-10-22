"""Build the viewer page from inside the scheduler, where passes, station and area are already known."""

import logging
from datetime import timedelta
from pathlib import Path

import numpy as np

from trollsched.viewer import build_page, geo
from trollsched.viewer.records import ScheduledEntry, build_records, normalize, schedule_name
from trollsched.viewer.sources import load_tles, plan_in_force, read_schedule, schedule_history, visible_passes

logger = logging.getLogger(__name__)


def scheduled_entries(reception_passes, antenna):
    """Turn the passes selected for reception into schedule entries for *antenna*."""
    # whole seconds, like the XML writer, so that the same pass on another antenna matches exactly
    return [ScheduledEntry(schedule_name(p), antenna, p.risetime.replace(microsecond=0),
                           p.falltime.replace(microsecond=0), overpass=p)
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
    """Compute the visibility windows of scheduled passes the scheduler does not know.

    That covers satellites that only appear in the avoid lists, and passes the
    scheduler discarded itself (Aqua/Terra dump restrictions, for instance).
    """
    unmatched = [e for e in entries
                 if not any(normalize(schedule_name(p)) == normalize(e.satellite)
                            and e.overlaps(p.risetime, p.falltime) for p in full_passes)]
    if not unmatched:
        return []
    satellites = {e.satellite for e in unmatched}
    if not tle_file or not Path(tle_file).exists():
        logger.warning("No TLE file; passes of %s not known to the scheduler cannot be computed",
                       ", ".join(sorted(satellites)))
        return []
    computed = visible_passes(satellites, span[0], span[1], coords, load_tles(tle_file), horizon)
    known = {normalize(schedule_name(p)) for p in full_passes}
    # satellites the scheduler knows had their other windows discarded on purpose: keep only the scheduled ones
    return [p for p in computed
            if normalize(schedule_name(p)) not in known
            or any(normalize(e.satellite) == normalize(schedule_name(p)) and e.overlaps(p.risetime, p.falltime)
                   for e in unmatched)]


def past_entries(history, antenna, avoid_files, since, until, known):
    """Get the passes planned by earlier runs between *since* and *until*, except those in *known*."""
    if not history:
        return []
    files = schedule_history(history, antenna, avoid_files)
    entries = [e for e in plan_in_force(files, since, until) if e not in set(known)]
    logger.info("Viewer: %d passes from %d earlier schedules since %s", len(entries), len(files), since)
    return entries


def past_visible_passes(satellites, since, until, coords, tle_file, horizon=0.0):
    """Compute the visibility windows of *satellites* (schedule names) between *since* and *until*."""
    if not satellites or since >= until:
        return []
    if not tle_file or not Path(tle_file).exists():
        logger.warning("No TLE file; passes before the run are shown without coverage")
        return []
    return visible_passes(satellites, since, until, coords, load_tles(tle_file), horizon)


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
                 coastlines_file=None, title=None, sources=(), history=None, history_hours=0):
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
        history: glob of this station's request files from earlier runs, to fill the past of the page.
        history_hours: how far back the past goes, from the start of the schedule.
    """
    antenna = getattr(station, "antenna", None) or station.id
    horizon = getattr(station, "local_horizon", 0)
    entries = scheduled_entries(reception_passes, antenna) + avoid_entries(avoid_files)
    full = untrimmed(allpasses)
    run_start = span[0]
    since = run_start - timedelta(hours=history_hours)
    past = past_entries(history, antenna, avoid_files, since, run_start, entries)
    if past:
        span = (since, span[1])
        entries += past
        satellites = {schedule_name(p) for p in full} | {e.satellite for e in entries}
        full += past_visible_passes(satellites, since, run_start, station.coords, tle_file, horizon)
    full += extra_visible_passes(full, entries, span, station.coords, tle_file, horizon)
    records = build_records(full, entries, station.coords, station=station.id, area=station.area,
                            delay=delay if isinstance(delay, timedelta) else timedelta(seconds=delay))
    logger.info("Viewer: %d scheduled passes, %d not scheduled, %d trimmed",
                sum("un" not in r for r in records), sum("un" in r for r in records),
                sum("fs" in r for r in records))
    return build_page(records, span, station.coords, coastlines=geo.load_coastlines(coastlines_file),
                      area_outline=area_outline(station.area), title=title, sources=sources)
