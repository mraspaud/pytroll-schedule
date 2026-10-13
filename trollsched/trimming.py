"""Trimming of overlapping passes, so that both can be received."""
import datetime as dt

from trollsched import MIN_PASS
from trollsched.satpass import Pass
from trollsched.spherical import intersect

TIME_RESOLUTION = dt.timedelta(seconds=1)
OUTLINE_SAMPLING_NOISE = 1e-4


def trimmed(overpass, risetime, falltime):
    """Get a copy of *overpass* received from *risetime* to *falltime* only."""
    return Pass(overpass.satellite, risetime, falltime, orb=overpass.orb, uptime=overpass.uptime,
                instrument=overpass.instrument, frequency=overpass.frequency,
                number_of_fovs=overpass.number_of_fovs)


def _coverage(overpass, area_of_interest):
    common = intersect(overpass.boundary.contour_poly, area_of_interest.poly)
    return 0 if common is None else common.area()


def in_area_window(overpass, area_of_interest):
    """Get the start and end times between which *overpass* covers *area_of_interest*."""
    full_coverage = _coverage(overpass, area_of_interest) * (1 - OUTLINE_SAMPLING_NOISE)

    def covers_all_from(risetime):
        return _coverage(trimmed(overpass, risetime, overpass.falltime), area_of_interest) >= full_coverage

    def covers_all_until(falltime):
        return _coverage(trimmed(overpass, overpass.risetime, falltime), area_of_interest) >= full_coverage

    return (_last_time_holding(covers_all_from, overpass.risetime, overpass.falltime),
            _last_time_holding(covers_all_until, overpass.falltime, overpass.risetime))


def _last_time_holding(condition, holds, fails):
    """Narrow down, from the time where *condition* *holds* towards the time it *fails*, where it stops holding."""
    while abs(fails - holds) > TIME_RESOLUTION:
        middle = holds + (fails - holds) / 2
        holds, fails = (middle, fails) if condition(middle) else (holds, middle)
    return holds


def trim_associated_overlaps(passes, area_of_interest, delay, shortest_pass=dt.timedelta(minutes=MIN_PASS)):
    """Trim overlapping passes outside *area_of_interest*, so they can all be received."""
    passes = sorted(passes, key=lambda overpass: overpass.risetime)
    for index in range(len(passes) - 1):
        passes[index], passes[index + 1] = _trim_pair(passes[index], passes[index + 1],
                                                      area_of_interest, delay, shortest_pass)
    return passes


def _are_associated(first, second, delay):
    return first.satellite.trimmable and second.satellite.trimmable and first.overlaps(second, delay)


def _trim_pair(first, second, area_of_interest, delay, shortest_pass):
    if not _are_associated(first, second, delay):
        return first, second
    _, first_end = in_area_window(first, area_of_interest)
    second_start, _ = in_area_window(second, area_of_interest)
    if first_end + delay > second_start:
        return first, second
    conflict_start = second.risetime - delay
    equal_share = conflict_start + (first.falltime - conflict_start) / 2
    cut = min(max(equal_share, first_end), second_start - delay)
    if cut - first.risetime < shortest_pass or second.falltime - (cut + delay) < shortest_pass:
        return first, second
    return trimmed(first, first.risetime, cut), trimmed(second, cut + delay, second.falltime)
