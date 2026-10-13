"""Test the scoring of pass combinations."""
import datetime as dt

import pytest

from trollsched.pass_scheduling_utils import Satellite
from trollsched.satpass import SimplePass
from trollsched.schedule import combine, coverage_weight, get_best_sched, overlap_penalty_weight
from trollsched.tests.polygons import AreaOfInterest, clockwise_polygon

NORTHERN_SUMMER_NOON = dt.datetime(2025, 6, 21, 11, 0)
NORTHERN_WINTER_MIDNIGHT = dt.datetime(2025, 12, 21, 23, 0)
SUNSET_OVER_THE_WEST_HALF = dt.datetime(2025, 3, 20, 17, 40)


class StubPass(SimplePass):
    """A pass stub with a fixed swath outline."""

    def __init__(self, name, outline, uptime, day=1.0, night=1.0):
        """Set up the pass."""
        super().__init__(Satellite(name, day, night), uptime - dt.timedelta(minutes=5),
                         uptime + dt.timedelta(minutes=5))
        self.uptime = uptime
        self.boundary = type("Boundary", (), {"contour_poly": outline})()


AREA = AreaOfInterest(clockwise_polygon((0, 60), (20, 60), (20, 50), (0, 50)))
WEST_HALF_SWATH = clockwise_polygon((-10, 70), (10, 70), (10, 40), (-10, 40))
EAST_HALF_SWATH = clockwise_polygon((10, 70), (30, 70), (30, 40), (10, 40))
WHOLE_AREA_SWATH = clockwise_polygon((-10, 70), (30, 70), (30, 40), (-10, 40))
FAR_AWAY_SWATH = clockwise_polygon((100, 70), (120, 70), (120, 40), (100, 40))
QUARTER_OF_AN_HOUR = dt.timedelta(hours=0.25)
INNER_SWATH = clockwise_polygon((1, 59), (19, 59), (19, 51), (1, 51))
INNER_WEST_SWATH = clockwise_polygon((2, 58), (8, 58), (8, 52), (2, 52))
INNER_EAST_SWATH = clockwise_polygon((12, 58), (18, 58), (18, 52), (12, 52))
ONE_MINUTE = dt.timedelta(minutes=1)


def test_daytime_passes_covering_disjoint_halves_add_up_half_their_day_scores():
    """Test that daytime passes over disjoint halves of the area add up half their day scores."""
    west = StubPass("west", WEST_HALF_SWATH, NORTHERN_SUMMER_NOON, day=0.6, night=0.1)
    east = StubPass("east", EAST_HALF_SWATH, NORTHERN_SUMMER_NOON + QUARTER_OF_AN_HOUR, day=0.8, night=0.1)

    assert combine(west, east, AREA) == pytest.approx(coverage_weight(0.25) * (0.6 / 2 + 0.8 / 2))


def test_daytime_passes_covering_the_same_area_are_penalised_by_their_mean_day_score():
    """Test that daytime passes over the same area lose their mean day score as overlap penalty."""
    first = StubPass("first", WHOLE_AREA_SWATH, NORTHERN_SUMMER_NOON, day=0.6, night=0.1)
    second = StubPass("second", WHOLE_AREA_SWATH, NORTHERN_SUMMER_NOON + QUARTER_OF_AN_HOUR, day=0.8, night=0.1)

    expected = coverage_weight(0.25) * (0.6 + 0.8) - overlap_penalty_weight(0.25) * (0.6 + 0.8) / 2
    assert combine(first, second, AREA) == pytest.approx(expected)


def test_nighttime_passes_covering_disjoint_halves_add_up_half_their_night_scores():
    """Test that nighttime passes over disjoint halves of the area add up half their night scores."""
    west = StubPass("west", WEST_HALF_SWATH, NORTHERN_WINTER_MIDNIGHT, day=0.6, night=0.1)
    east = StubPass("east", EAST_HALF_SWATH, NORTHERN_WINTER_MIDNIGHT + QUARTER_OF_AN_HOUR, day=0.8, night=0.3)

    assert combine(west, east, AREA) == pytest.approx(coverage_weight(0.25) * (0.1 / 2 + 0.3 / 2))


def test_passes_across_the_terminator_with_equal_day_and_night_scores_score_as_one():
    """Test that splitting a pass into day and night parts preserves its coverage."""
    west = StubPass("west", WEST_HALF_SWATH, SUNSET_OVER_THE_WEST_HALF, day=0.5, night=0.5)
    east = StubPass("east", EAST_HALF_SWATH, SUNSET_OVER_THE_WEST_HALF + QUARTER_OF_AN_HOUR, day=0.5, night=0.5)

    assert combine(west, east, AREA) == pytest.approx(coverage_weight(0.25) * (0.5 / 2 + 0.5 / 2))


def test_passes_covering_disjoint_halves_score_the_same_whichever_comes_first():
    """Test that the order of passes over disjoint halves of the area does not matter."""
    east = StubPass("east", EAST_HALF_SWATH, NORTHERN_SUMMER_NOON, day=0.8, night=0.1)
    west = StubPass("west", WEST_HALF_SWATH, NORTHERN_SUMMER_NOON + QUARTER_OF_AN_HOUR, day=0.6, night=0.1)

    assert combine(east, west, AREA) == pytest.approx(coverage_weight(0.25) * (0.8 / 2 + 0.6 / 2))


def test_a_pass_missing_the_area_adds_nothing_to_the_other_passes_score():
    """Test that combining with a pass outside the area keeps the other pass's score."""
    away = StubPass("away", FAR_AWAY_SWATH, NORTHERN_SUMMER_NOON, day=0.6, night=0.1)
    west = StubPass("west", WEST_HALF_SWATH, NORTHERN_SUMMER_NOON + QUARTER_OF_AN_HOUR, day=0.8, night=0.1)

    assert combine(away, west, AREA) == pytest.approx(coverage_weight(0.25) * 0.8 / 2)


def test_a_pass_missing_the_area_after_another_adds_nothing_to_its_score():
    """Test that combining with a later pass outside the area keeps the earlier pass's score."""
    west = StubPass("west", WEST_HALF_SWATH, NORTHERN_SUMMER_NOON, day=0.8, night=0.1)
    away = StubPass("away", FAR_AWAY_SWATH, NORTHERN_SUMMER_NOON + QUARTER_OF_AN_HOUR, day=0.6, night=0.1)

    assert combine(west, away, AREA) == pytest.approx(coverage_weight(0.25) * 0.8 / 2)


def test_a_pass_missing_the_area_can_be_combined_again():
    """Test that a pass outside the area can be combined with several passes."""
    away = StubPass("away", FAR_AWAY_SWATH, NORTHERN_SUMMER_NOON, day=0.6, night=0.1)
    west = StubPass("west", WEST_HALF_SWATH, NORTHERN_SUMMER_NOON + QUARTER_OF_AN_HOUR, day=0.8, night=0.1)
    east = StubPass("east", EAST_HALF_SWATH, NORTHERN_SUMMER_NOON + QUARTER_OF_AN_HOUR, day=0.4, night=0.1)
    combine(away, west, AREA)

    assert combine(away, east, AREA) == pytest.approx(coverage_weight(0.25) * 0.4 / 2)


def large_and_small_conflicting_passes_then_a_later_one(large_day_score=1.0):
    """Make a large and a small pass conflicting in time, and a later pass."""
    large = StubPass("large", INNER_SWATH, NORTHERN_SUMMER_NOON, day=large_day_score)
    small = StubPass("small", INNER_WEST_SWATH, NORTHERN_SUMMER_NOON + 5 * ONE_MINUTE)
    later = StubPass("later", INNER_EAST_SWATH, NORTHERN_SUMMER_NOON + 60 * ONE_MINUTE)
    return large, small, later


def test_best_schedule_takes_the_pass_covering_more_of_the_area_when_passes_conflict():
    """Test that of two conflicting passes, the one covering more of the area is scheduled."""
    large, small, later = large_and_small_conflicting_passes_then_a_later_one()

    schedule, _ = get_best_sched([small, later, large], AREA, ONE_MINUTE)

    assert sorted(schedule) == [large, later]


def test_best_schedule_leaves_out_passes_to_avoid():
    """Test that a pass to avoid is not scheduled, even when it covers more of the area."""
    earlier = StubPass("earlier", INNER_EAST_SWATH, NORTHERN_SUMMER_NOON - 60 * ONE_MINUTE)
    large, small, later = large_and_small_conflicting_passes_then_a_later_one()
    to_avoid = SimplePass("large", large.risetime, large.falltime)

    schedule, _ = get_best_sched([earlier, small, later, large], AREA, ONE_MINUTE, avoid_list=[to_avoid])

    assert sorted(schedule) == [earlier, small, later]


def test_best_schedule_takes_the_better_pass_in_the_very_first_conflict():
    """Test that the first conflict of the schedule is decided on coverage too."""
    large, small, later = large_and_small_conflicting_passes_then_a_later_one(large_day_score=0.01)

    schedule, _ = get_best_sched([small, later, large], AREA, ONE_MINUTE)

    assert sorted(schedule) == [small, later]


def test_best_schedule_can_take_both_ends_of_a_chain_of_conflicts():
    """Test that the passes at both ends of a chain of conflicts can both be scheduled."""
    earlier = StubPass("earlier", INNER_EAST_SWATH, NORTHERN_SUMMER_NOON - 60 * ONE_MINUTE)
    west = StubPass("west", INNER_WEST_SWATH, NORTHERN_SUMMER_NOON)
    middle = StubPass("middle", INNER_SWATH, NORTHERN_SUMMER_NOON + 8 * ONE_MINUTE, day=0.1)
    east = StubPass("east", INNER_EAST_SWATH, NORTHERN_SUMMER_NOON + 16 * ONE_MINUTE)

    schedule, _ = get_best_sched([earlier, west, middle, east], AREA, ONE_MINUTE)

    assert sorted(schedule) == [earlier, west, east]
