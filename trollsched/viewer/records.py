"""Turn passes and acquisition schedules into the records the viewer page displays."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from trollsched.viewer import geo

logger = logging.getLogger(__name__)

COVERAGE_POINTS = 16
TRIM_TOLERANCE = timedelta(seconds=5)

DISPLAY_NAMES = {"npp": "NPP", "aws-pfm": "AWS-PFM"}


@dataclass(frozen=True)
class ScheduledEntry:
    """A pass as listed in an acquisition schedule: what one antenna will receive."""

    satellite: str
    antenna: str
    start: datetime
    end: datetime

    def overlaps(self, start, end):
        """Check whether this entry overlaps the (start, end) window."""
        return self.start < end and self.end > start


def normalize(name):
    """Normalise a satellite name for matching across naming conventions."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def schedule_name(overpass):
    """Get the name used in schedules for the satellite of *overpass*."""
    satellite = overpass.satellite
    return getattr(satellite, "schedule_name", None) or getattr(satellite, "name", satellite)


def display_name(name):
    """Get the name shown on the page."""
    return DISPLAY_NAMES.get(name, name.upper())


def timestamp(utctime):
    """Get the POSIX timestamp of a naive UTC datetime."""
    return utctime.replace(tzinfo=timezone.utc).timestamp()


def pass_geometry(overpass, coords, area=None, npoints=COVERAGE_POINTS):
    """Compute the orbit number, swath, direction and look angles of a pass."""
    orb = overpass.orb
    lon, lat, alt = coords
    result = {"orbit": int(orb.get_orbit_number(overpass.uptime)),
              "dir": overpass.pass_direction(),
              "aos_az": round(float(orb.get_observer_look(overpass.risetime, lon, lat, alt)[0])),
              "los_az": round(float(orb.get_observer_look(overpass.falltime, lon, lat, alt)[0])),
              "max_el": round(float(orb.get_observer_look(overpass.uptime, lon, lat, alt)[1])),
              "sun": geo.subsolar_point(overpass.uptime)}
    try:
        boundary = overpass.boundary
        result["cov"] = geo.resample_boundary(boundary, npoints)
        result["track"] = geo.swath_track(boundary)
    except Exception as err:  # noqa: BLE001 - a pass without swath is still worth listing
        logger.warning("No swath for %s %s: %s", schedule_name(overpass), overpass.risetime, err)
        return result
    if area is not None:
        try:
            result["area_pct"] = round(100 * overpass.area_coverage(area), 1)
        except Exception as err:  # noqa: BLE001
            logger.warning("No area coverage for %s %s: %s", schedule_name(overpass), overpass.risetime, err)
    return result


def _base_record(overpass, start, end, station):
    name = schedule_name(overpass)
    return {"sat": name, "name": display_name(name), "station": station,
            "s": timestamp(start), "e": timestamp(end)}


def build_records(full_passes, entries, coords, station="", area=None, delay=timedelta(0),
                  tolerance=TRIM_TOLERANCE, npoints=COVERAGE_POINTS):
    """Build the viewer records from the visible passes and what the schedules say will be received.

    Args:
        full_passes: untrimmed ``Pass`` objects, the visibility windows over the station.
        entries: ``ScheduledEntry`` objects from one or more acquisition schedules.
        coords: station (lon, lat, alt).
        station: station name for display.
        area: area of interest (with a ``poly``) for coverage percentages, or None.
        delay: antenna switching delay, used to tell which scheduled pass an unscheduled one lost to.
        tolerance: how much shorter than its visibility a scheduled pass may be before being called trimmed.
        npoints: vertices per swath polygon.

    Returns a list of dicts: one per scheduled entry (with the trimmed-away part when relevant),
    plus one per visible pass that no schedule lists, flagged ``un`` with the entries it lost to.
    """
    from trollsched.trimming import trimmed

    records = []
    matched = set()
    for overpass in sorted(full_passes, key=lambda p: p.risetime):
        name = normalize(schedule_name(overpass))
        hits = [e for e in entries
                if normalize(e.satellite) == name and e.overlaps(overpass.risetime, overpass.falltime)]
        full_geometry = None
        for entry in hits:
            matched.add(entry)
            record = _base_record(overpass, entry.start, entry.end, station)
            record["ant"] = entry.antenna
            received = trimmed(overpass, entry.start, entry.end)
            record.update(pass_geometry(received, coords, area, npoints))
            cut = max(entry.start - overpass.risetime, overpass.falltime - entry.end)
            if cut > tolerance:
                if full_geometry is None:
                    full_geometry = pass_geometry(overpass, coords, area, npoints)
                record["fs"], record["fe"] = timestamp(overpass.risetime), timestamp(overpass.falltime)
                if "cov" in full_geometry:
                    record["fcov"] = full_geometry["cov"]
                if "area_pct" in full_geometry:
                    record["full_area_pct"] = full_geometry["area_pct"]
            records.append(record)
        if not hits:
            record = _base_record(overpass, overpass.risetime, overpass.falltime, station)
            record["ant"] = ""
            record["un"] = 1
            record.update(pass_geometry(overpass, coords, area, npoints))
            record["lost_to"] = sorted({f"{e.satellite}|{e.antenna}|{timestamp(e.start):.0f}" for e in entries
                                        if e.overlaps(overpass.risetime - delay, overpass.falltime + delay)})
            records.append(record)

    for entry in entries:
        if entry in matched:
            continue
        logger.warning("Scheduled pass %s %s on %s has no matching visibility; drawn without geometry",
                       entry.satellite, entry.start, entry.antenna)
        records.append({"sat": entry.satellite, "name": display_name(entry.satellite), "station": station,
                        "ant": entry.antenna, "s": timestamp(entry.start), "e": timestamp(entry.end)})
    return records
