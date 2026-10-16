"""Test the trimming of overlapping passes."""
import datetime as dt

import defusedxml.ElementTree as ET
import pytest
from pyresample.geometry import AreaDefinition

from trollsched.pass_scheduling_utils import Satellite
from trollsched.satpass import create_pass
from trollsched.schedule import Scheduler, Station, combined_stations, parse_args
from trollsched.tests.polygons import AreaOfInterest
from trollsched.tests.test_satpass import AREA_DEF_EURON1
from trollsched.trimming import in_area_window, restore_unused_trim, trim_associated_overlaps, trimmed

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


def test_coverage_loss_allowance_relaxes_reception_time_limits(november_2025_tle_file):
    """A configured loss permits later rise and earlier fall limits for a fully in-area pass."""
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


def test_unused_trim_is_recovered_only_up_to_another_selected_pass(
        sga1_and_fy3f_overlapping_outside_the_area, november_2025_tle_file):
    """Recover the available reception time without overlapping a different selected pass."""
    sga1, fy3f = sga1_and_fy3f_overlapping_outside_the_area
    _, shortened = trim_associated_overlaps([sga1, fy3f], EURON1, ONE_MINUTE)
    blocker = create_pass("METOP-SGA1", "avhrr", sga1.risetime, shortened.risetime - 2 * ONE_MINUTE,
                          str(november_2025_tle_file))
    blocker.rec = shortened.rec = True

    _, restored = restore_unused_trim([blocker, shortened], ONE_MINUTE)

    assert restored.risetime == blocker.falltime + ONE_MINUTE


def test_selected_trimming_partners_keep_their_shared_cut(sga1_and_fy3f_overlapping_outside_the_area):
    """Keep the necessary trimming when both partners are received."""
    candidates = trim_associated_overlaps(sga1_and_fy3f_overlapping_outside_the_area, EURON1, ONE_MINUTE)
    for overpass in candidates:
        overpass.rec = True

    assert reception_times(restore_unused_trim(candidates, ONE_MINUTE)) == reception_times(candidates)


def test_recovering_both_sides_of_a_gap_preserves_delay_and_candidate_windows(
        sga1_and_fy3f_overlapping_outside_the_area):
    """Expanding two receptions must neither overlap nor mutate the graph's candidate passes."""
    sga1, fy3f = sga1_and_fy3f_overlapping_outside_the_area
    candidates = [trimmed(sga1, sga1.risetime, dt.datetime(2025, 11, 21, 9, 30)),
                  trimmed(fy3f, dt.datetime(2025, 11, 21, 9, 40), fy3f.falltime)]
    for overpass in candidates:
        overpass.rec = True
    candidate_windows = reception_times(candidates)

    first, second = restore_unused_trim(candidates, ONE_MINUTE)

    assert first.falltime + ONE_MINUTE <= second.risetime
    assert first.risetime == sga1.risetime
    assert second.falltime == fy3f.falltime
    assert reception_times(candidates) == candidate_windows


@pytest.fixture
def discarded_trimming_partner_setup(october_2026_tle_file, tmp_path, monkeypatch):
    """Provide a station where FY-3H wins over the SGA1 that FY-3F was trimmed for."""
    monkeypatch.setattr("trollsched.schedule.send_file", lambda url, file: None)
    satellites = [Satellite("METOP-SGA1", 0.7, 0.7, trimmable=True),
                  Satellite("FENGYUN 3F", 0.6, 0.3, trimmable=True, max_coverage_loss=5),
                  Satellite("FENGYUN 3H", 0.9, 0.9)]
    station = Station("nrk", "nrk", 16.148649, 58.581844, 0.052765, AREA_DEF_EURON1, satellites)
    patterns = {"dir_output": str(tmp_path), "file_xml": str(tmp_path / "{station}-{mode}.xml")}
    scheduler = Scheduler([station], 4, 2, 0, None, patterns, "TEST", {}, None)
    scheduler.opts = parse_args(["-c", "unused", "-x", "-d", "15"])
    scheduler.opts.output_dir = str(tmp_path)
    scheduler.opts.comb = False

    return station, scheduler, dt.datetime(2026, 10, 18, 10, 0), str(october_2026_tle_file)


@pytest.mark.parametrize("coordinated", [False, True])
def test_pass_is_not_trimmed_for_a_trimming_partner_that_is_not_scheduled(
        discarded_trimming_partner_setup, tmp_path, coordinated):
    """Keep the full FY-3F window when the SGA1 it was trimmed for is not received."""
    station, scheduler, start, tle_file = discarded_trimming_partner_setup
    graph, passes = station.single_station(scheduler, start, tle_file)
    if coordinated:
        combined_stations(scheduler, start, {"nrk": graph}, {"nrk": passes})

    filename = "nrk-comb-request.xml" if coordinated else "nrk-request.xml"
    scheduled = [(overpass.attrib["satellite"], overpass.attrib["start-time"])
                 for overpass in ET.parse(tmp_path / filename).getroot().findall("pass")]
    assert scheduled == [("FENGYUN 3H", "2026-10-18-10:24:33"), ("FENGYUN 3F", "2026-10-18-10:42:53")]


@pytest.mark.parametrize("coordinated", [False, True])
def test_report_plots_use_restored_reception_windows(
        discarded_trimming_partner_setup, tmp_path, monkeypatch, coordinated):
    """The report's image depicts the reception window actually published."""
    station, scheduler, start, tle_file = discarded_trimming_partner_setup
    scheduler.opts.report = scheduler.opts.plot = True
    scheduler.patterns["dir_plots"] = str(tmp_path / "plots")
    monkeypatch.setattr("trollsched.drawing.save_fig",
                        lambda overpass, **kwargs: setattr(overpass, "fig", overpass.risetime.isoformat()))

    graph, passes = station.single_station(scheduler, start, tle_file)
    if coordinated:
        station.area = AreaDefinition("euron1", "", "", station.area.proj_dict,
                                      station.area.width, station.area.height, station.area.area_extent)
        combined_stations(scheduler, start, {"nrk": graph}, {"nrk": passes})

    filename = "nrk-comb-report.xml" if coordinated else "nrk-report.xml"
    fy3f = ET.parse(tmp_path / filename).find("pass[@satellite='FENGYUN 3F']")
    assert fy3f.attrib["img"] == "2026-10-18T10:42:53.666865"
