"""Test the spherical geometry functions."""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pytest
from pyresample.spherical import SphPolygon

from trollsched.spherical import get_twilight_poly, intersect, split_day_and_night
from trollsched.tests.polygons import clockwise_polygon


def test_intersecting_overlapping_polygons_gives_their_common_part():
    """Test that the intersection of two overlapping polygons is their common part."""
    first = clockwise_polygon((0, 60), (20, 60), (20, 50), (0, 50))
    second = clockwise_polygon((10, 65), (30, 65), (30, 55), (10, 55))

    assert intersect(first, second).area() == pytest.approx(first.intersection(second).area(), rel=1e-9)


def test_polygons_sharing_only_an_edge_have_nothing_in_common():
    """Test that polygons sharing only an edge do not intersect."""
    east = clockwise_polygon((10, 60), (20, 60), (20, 50), (10, 50))
    west = clockwise_polygon((0, 60), (10, 60), (10, 50), (0, 50))

    assert intersect(east, west) is None


def test_identical_polygons_have_everything_in_common():
    """Test that a polygon intersected with an identical one is the polygon itself."""
    polygon = clockwise_polygon((0, 60), (20, 60), (20, 50), (0, 50))
    identical = clockwise_polygon((0, 60), (20, 60), (20, 50), (0, 50))

    assert intersect(polygon, identical).area() == pytest.approx(polygon.area(), rel=1e-9)


def test_polygons_on_opposite_sides_of_the_earth_have_nothing_in_common():
    """Test that polygons too far apart to share a gnomonic projection do not intersect."""
    europe = clockwise_polygon((0, 60), (20, 60), (20, 50), (0, 50))
    pacific = clockwise_polygon((170, -50), (-170, -50), (-170, -60), (170, -60))

    assert intersect(europe, pacific) is None


def test_intersections_in_several_pieces_are_left_to_pyresample():
    """Test that an intersection in two pieces, which one polygon cannot hold, is computed by pyresample."""
    u_shape = clockwise_polygon((0, 60), (4, 60), (4, 52), (16, 52), (16, 60), (20, 60), (20, 50), (0, 50))
    bar = clockwise_polygon((-5, 57), (25, 57), (25, 55), (-5, 55))

    assert intersect(u_shape, bar).area() == pytest.approx(u_shape.intersection(bar).area(), rel=1e-9)


def test_splitting_a_polygon_across_the_terminator_gives_its_day_and_night_parts():
    """Test that a polygon across the terminator is split in its sunlit and dark parts."""
    polygon = clockwise_polygon((0, 60), (10, 60), (10, 50), (0, 50))
    sunset = dt.datetime(2025, 3, 20, 17, 40)
    sunlit = get_twilight_poly(sunset)
    dark = get_twilight_poly(sunset)
    dark.invert()

    day, night = split_day_and_night(polygon, sunset)

    assert day.area() == pytest.approx(polygon.intersection(sunlit).area(), rel=1e-9)
    assert night.area() == pytest.approx(polygon.intersection(dark).area(), rel=1e-9)


def test_splitting_a_sunlit_polygon_leaves_no_night_part():
    """Test that a polygon in full daylight is all day."""
    polygon = clockwise_polygon((0, 60), (10, 60), (10, 50), (0, 50))

    day, night = split_day_and_night(polygon, dt.datetime(2025, 6, 21, 11, 0))

    assert (day.area(), night) == (pytest.approx(polygon.area(), rel=1e-9), None)


def test_splitting_a_dark_polygon_leaves_no_day_part():
    """Test that a polygon in full darkness is all night."""
    polygon = clockwise_polygon((0, 60), (10, 60), (10, 50), (0, 50))

    day, night = split_day_and_night(polygon, dt.datetime(2025, 12, 21, 23, 0))

    assert (day, night.area()) == (None, pytest.approx(polygon.area(), rel=1e-9))


def test_intersecting_coverages_with_nearly_coincident_edges_gives_a_valid_polygon():
    """Test that an intersection with nearly coincident vertices is no larger than what it intersects."""
    coverages = json.loads((Path(__file__).parent / "data" / "coverages_with_nearly_coincident_edges.json").read_text())
    fy3f = SphPolygon(np.array(coverages["fy3f"]))
    sga1 = SphPolygon(np.array(coverages["sga1"]))

    assert 0 < intersect(fy3f, sga1).area() <= min(fy3f.area(), sga1.area())
