"""Polygon helpers for the tests."""
import numpy as np
from pyresample.spherical import SphPolygon


def clockwise_polygon(*lonlats):
    """Make a spherical polygon from clockwise (lon, lat) vertices in degrees."""
    return SphPolygon(np.deg2rad(np.array(lonlats, dtype=float)))


class AreaOfInterest:
    """An area of interest stub."""

    def __init__(self, polygon):
        """Set up the area."""
        self.poly = polygon
