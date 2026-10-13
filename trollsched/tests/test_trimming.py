"""Test the trimming of overlapping passes."""
import datetime as dt

import pytest

from trollsched.satpass import create_pass
from trollsched.tests.polygons import AreaOfInterest
from trollsched.tests.test_satpass import AREA_DEF_EURON1
from trollsched.trimming import in_area_window, trim_associated_overlaps

EURON1 = AreaOfInterest(AREA_DEF_EURON1.boundary(8).contour_poly)
ONE_MINUTE = dt.timedelta(minutes=1)
OUTLINE_SAMPLING_NOISE = 1e-3


def test_in_area_window_of_a_pass_reaching_beyond_the_area_is_inside_the_pass(november_2025_tle_file):
    """Test that a pass starting and ending outside the area covers it during only part of the pass."""
    sga1 = create_pass("METOP-SGA1", "avhrr", dt.datetime(2025, 11, 21, 9, 23, 9), dt.datetime(2025, 11, 21, 9, 38, 35),
                       str(november_2025_tle_file))

    start, end = in_area_window(sga1, EURON1)

    assert sga1.risetime < start < end < sga1.falltime


def test_in_area_window_of_a_pass_over_the_area_all_along_is_the_whole_pass(november_2025_tle_file):
    """Test that a pass over the area from start to end covers it during the whole pass."""
    sga1 = create_pass("METOP-SGA1", "avhrr", dt.datetime(2025, 11, 21, 9, 29), dt.datetime(2025, 11, 21, 9, 31),
                       str(november_2025_tle_file))

    assert in_area_window(sga1, EURON1) == (sga1.risetime, sga1.falltime)


def test_coverage_loss_allowance_shortens_the_required_reception_window(november_2025_tle_file):
    """A configured loss permits dropping either end of an otherwise fully in-area pass."""
    sga1 = create_pass("METOP-SGA1", "avhrr", dt.datetime(2025, 11, 21, 9, 29), dt.datetime(2025, 11, 21, 9, 31),
                       str(november_2025_tle_file))
    sga1.satellite.max_coverage_loss = 25
    start, end = in_area_window(sga1, EURON1)
    assert sga1.risetime < start < end < sga1.falltime


def reception_times(passes):
    """Get the reception start and end times of *passes*."""
    return [(overpass.risetime, overpass.falltime) for overpass in passes]


def trimmable_pass(name, instrument, risetime, falltime, tle_file):
    """Create a pass of a satellite configured as trimmable."""
    overpass = create_pass(name, instrument, risetime, falltime, str(tle_file))
    overpass.satellite.trimmable = True
    return overpass


@pytest.fixture
def sga1_and_fy3f_overlapping_outside_the_area(november_2025_tle_file):
    """Make trimmable Metop-SGA1 and FY-3F passes overlapping by 5 minutes, outside euron1."""
    sga1 = trimmable_pass("METOP-SGA1", "avhrr", dt.datetime(2025, 11, 21, 9, 23, 9),
                          dt.datetime(2025, 11, 21, 9, 38, 35), november_2025_tle_file)
    fy3f = trimmable_pass("FENGYUN 3F", "mersi-3", dt.datetime(2025, 11, 21, 9, 33, 49),
                          dt.datetime(2025, 11, 21, 9, 49, 17), november_2025_tle_file)
    return [sga1, fy3f]


def test_trimmable_passes_overlapping_outside_the_area_are_both_kept_without_conflict(
        sga1_and_fy3f_overlapping_outside_the_area):
    """Test that trimmable passes overlapping only outside the area are trimmed so both can be received."""
    first, second = trim_associated_overlaps(sga1_and_fy3f_overlapping_outside_the_area, EURON1, ONE_MINUTE)

    assert first.falltime + ONE_MINUTE <= second.risetime


def test_trimming_passes_overlapping_outside_the_area_keeps_their_coverage_of_the_area(
        sga1_and_fy3f_overlapping_outside_the_area):
    """Test that trimming passes overlapping outside the area does not cut anything over the area."""
    sga1, fy3f = sga1_and_fy3f_overlapping_outside_the_area

    trimmed_passes = trim_associated_overlaps([sga1, fy3f], EURON1, ONE_MINUTE)

    for trimmed_pass, original in zip(trimmed_passes, [sga1, fy3f]):
        assert trimmed_pass.area_coverage(EURON1) >= original.area_coverage(EURON1) * (1 - OUTLINE_SAMPLING_NOISE)


def test_passes_overlapping_over_the_area_are_left_untouched(sga1_and_fy3f_overlapping_outside_the_area):
    """Test that passes too close in time over the area are left for the scheduler to choose from."""
    three_minutes = 3 * ONE_MINUTE

    untouched = trim_associated_overlaps(sga1_and_fy3f_overlapping_outside_the_area, EURON1, three_minutes)

    assert reception_times(untouched) == reception_times(sga1_and_fy3f_overlapping_outside_the_area)


def test_configured_coverage_loss_allows_conflicts_over_the_area_to_be_trimmed(
        sga1_and_fy3f_overlapping_outside_the_area):
    """Both passes can be received when the allowed coverage loss makes the delay feasible."""
    for overpass in sga1_and_fy3f_overlapping_outside_the_area:
        overpass.satellite.max_coverage_loss = 25
    first, second = trim_associated_overlaps(sga1_and_fy3f_overlapping_outside_the_area, EURON1, 3 * ONE_MINUTE)
    assert first.falltime + 3 * ONE_MINUTE <= second.risetime
    assert all(result.area_coverage(EURON1) >= original.area_coverage(EURON1) * 0.75 * (1 - OUTLINE_SAMPLING_NOISE)
               for result, original in zip((first, second), sga1_and_fy3f_overlapping_outside_the_area))


def test_coverage_loss_does_not_compound_when_both_ends_of_a_pass_are_trimmed(november_2025_tle_file):
    """The middle pass's allowance remains relative to its original coverage across the chain."""
    start = dt.datetime(2025, 11, 21, 9, 27)
    originals = [trimmable_pass("METOP-SGA1", "avhrr", start + offset * ONE_MINUTE,
                                start + (offset + 6) * ONE_MINUTE, november_2025_tle_file)
                 for offset in (-4, 0, 4)]
    for overpass, loss in zip(originals, (100, 25, 100)):
        overpass.satellite.max_coverage_loss = loss
    _, middle, _ = trim_associated_overlaps(originals, EURON1, 3 * ONE_MINUTE, shortest_pass=ONE_MINUTE)
    assert middle.area_coverage(EURON1) >= originals[1].area_coverage(EURON1) * 0.75 * (1 - OUTLINE_SAMPLING_NOISE)


@pytest.mark.parametrize("zero_loss_index", [0, 1])
def test_each_satellite_retains_its_own_coverage_allowance(
        zero_loss_index, sga1_and_fy3f_overlapping_outside_the_area):
    """A permissive satellite does not let its zero-loss neighbor give up area coverage."""
    originals = sga1_and_fy3f_overlapping_outside_the_area
    for index, overpass in enumerate(originals):
        overpass.satellite.max_coverage_loss = 0 if index == zero_loss_index else 100
    results = trim_associated_overlaps(originals, EURON1, 3 * ONE_MINUTE)
    assert results[0].falltime + 3 * ONE_MINUTE <= results[1].risetime
    assert results[zero_loss_index].area_coverage(EURON1) >= (
        originals[zero_loss_index].area_coverage(EURON1) * (1 - OUTLINE_SAMPLING_NOISE))


@pytest.mark.parametrize("unmarked_index", [0, 1])
def test_coverage_loss_does_not_enable_trimming_for_unmarked_satellites(
        unmarked_index, sga1_and_fy3f_overlapping_outside_the_area):
    """Both satellites must opt in even when their configured loss allowances are permissive."""
    originals = sga1_and_fy3f_overlapping_outside_the_area
    for overpass in originals:
        overpass.satellite.max_coverage_loss = 100
    originals[unmarked_index].satellite.trimmable = False
    results = trim_associated_overlaps(originals, EURON1, 3 * ONE_MINUTE)
    assert reception_times(results) == reception_times(originals)


def test_passes_overlapping_a_pass_not_marked_trimmable_are_left_untouched(sga1_and_fy3f_overlapping_outside_the_area):
    """Test that only passes of satellites both marked as trimmable are trimmed."""
    sga1, fy3f = sga1_and_fy3f_overlapping_outside_the_area
    fy3f.satellite.trimmable = False

    untouched = trim_associated_overlaps([sga1, fy3f], EURON1, ONE_MINUTE)

    assert reception_times(untouched) == reception_times([sga1, fy3f])


def test_passes_that_trimming_would_make_too_short_are_left_untouched(sga1_and_fy3f_overlapping_outside_the_area):
    """Test that passes are not trimmed below the shortest pass worth receiving."""
    untouched = trim_associated_overlaps(sga1_and_fy3f_overlapping_outside_the_area, EURON1, ONE_MINUTE,
                                         shortest_pass=13 * ONE_MINUTE)

    assert reception_times(untouched) == reception_times(sga1_and_fy3f_overlapping_outside_the_area)


def test_each_overlap_in_a_chain_of_overlapping_passes_is_trimmed_on_its_own(november_2025_tle_file):
    """Test that in a chain of overlaps, overlaps over the area are kept and those outside are trimmed."""
    aws = trimmable_pass("AWS", "avhrr", dt.datetime(2025, 11, 23, 20, 7, 36),
                         dt.datetime(2025, 11, 23, 20, 20, 20), november_2025_tle_file)
    sga1 = trimmable_pass("METOP-SGA1", "avhrr", dt.datetime(2025, 11, 23, 20, 13, 13),
                          dt.datetime(2025, 11, 23, 20, 28, 22), november_2025_tle_file)
    fy3f = trimmable_pass("FENGYUN 3F", "mersi-3", dt.datetime(2025, 11, 23, 20, 27, 49),
                          dt.datetime(2025, 11, 23, 20, 43, 17), november_2025_tle_file)

    trimmed_aws, trimmed_sga1, trimmed_fy3f = trim_associated_overlaps([aws, sga1, fy3f], EURON1, ONE_MINUTE)

    assert reception_times([trimmed_aws]) == reception_times([aws])
    assert trimmed_sga1.risetime == sga1.risetime
    assert trimmed_sga1.falltime + ONE_MINUTE <= trimmed_fy3f.risetime


def test_passes_not_overlapping_are_left_untouched(november_2025_tle_file):
    """Test that trimmable passes far enough apart are not trimmed."""
    sga1 = trimmable_pass("METOP-SGA1", "avhrr", dt.datetime(2025, 11, 21, 9, 23, 9),
                          dt.datetime(2025, 11, 21, 9, 38, 35), november_2025_tle_file)
    fy3f = trimmable_pass("FENGYUN 3F", "mersi-3", dt.datetime(2025, 11, 21, 11, 14, 13),
                          dt.datetime(2025, 11, 21, 11, 28, 52), november_2025_tle_file)

    untouched = trim_associated_overlaps([sga1, fy3f], EURON1, ONE_MINUTE)

    assert reception_times(untouched) == reception_times([sga1, fy3f])


def test_trimmed_passes_share_their_overlap_equally_when_outside_the_area(november_2025_tle_file):
    """Test that both passes give up the same reception time, when that cuts nothing over the area."""
    sga1 = trimmable_pass("METOP-SGA1", "avhrr", dt.datetime(2025, 11, 22, 9, 2, 19),
                          dt.datetime(2025, 11, 22, 9, 17, 46), november_2025_tle_file)
    fy3f = trimmable_pass("FENGYUN 3F", "mersi-3", dt.datetime(2025, 11, 22, 9, 14, 40),
                          dt.datetime(2025, 11, 22, 9, 29, 59), november_2025_tle_file)

    trimmed_sga1, trimmed_fy3f = trim_associated_overlaps([sga1, fy3f], EURON1, ONE_MINUTE)

    assert sga1.falltime - trimmed_sga1.falltime == trimmed_fy3f.risetime - fy3f.risetime
