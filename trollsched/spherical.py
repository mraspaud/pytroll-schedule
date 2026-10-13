#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2013, 2014, 2015, 2018 Martin Raspaud

# Author(s):

#   Martin Raspaud <martin.raspaud@smhi.se>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Some generalized spherical functions.

base type is a numpy array of size (n, 2) (2 for lon and lats)

"""

import logging

import numpy as np
import pyresample.spherical
import shapely

logger = logging.getLogger(__name__)

EPSILON = 0.0000001


def modpi(val, mod=np.pi):
    """Put *val* between -*mod* and *mod*."""
    return (val + mod) % (2 * mod) - mod


class SphPolygon(pyresample.spherical.SphPolygon):
    """A spherical polygon with drawing capabilities."""

    def draw(self, mapper, options, **more_options):
        """Draw the polygon."""
        lons = np.rad2deg(self.lon.take(np.arange(len(self.lon) + 1),
                                        mode="wrap"))
        lats = np.rad2deg(self.lat.take(np.arange(len(self.lat) + 1),
                                        mode="wrap"))
        rx, ry = mapper(lons, lats)
        mapper.plot(rx, ry, options, **more_options)


def get_twilight_poly(utctime):
    """Return a polygon enclosing the sunlit part of the globe at *utctime*."""
    from pyorbital import astronomy
    ra, dec = astronomy.sun_ra_dec(utctime)
    lon = modpi(ra - astronomy.gmst(utctime))
    lat = dec

    vertices = np.zeros((4, 2))

    vertices[0, :] = modpi(lon - np.pi / 2), 0
    if lat <= 0:
        vertices[1, :] = lon, np.pi / 2 + lat
        vertices[3, :] = modpi(lon + np.pi), -(np.pi / 2 + lat)
    else:
        vertices[1, :] = modpi(lon + np.pi), np.pi / 2 - lat
        vertices[3, :] = lon, -(np.pi / 2 - lat)

    vertices[2, :] = modpi(lon + np.pi / 2), 0

    return SphPolygon(vertices)


def _to_cartesian(lonlats):
    lons, lats = lonlats[:, 0], lonlats[:, 1]
    return np.stack([np.cos(lats) * np.cos(lons), np.cos(lats) * np.sin(lons), np.sin(lats)], axis=1)


_COSINE_OF_LARGEST_PROJECTABLE_ANGLE = np.cos(np.deg2rad(80))
_SAME_POINT_IN_THE_PLANE = 1e-9


class _GnomonicPlane:
    """A plane tangent to the sphere, where great circles are straight lines."""

    def __init__(self, centre):
        self.centre = centre / np.linalg.norm(centre)
        east = np.cross([0, 0, 1.0], self.centre)
        self.east = east / np.linalg.norm(east)
        self.north = np.cross(self.centre, self.east)

    def can_project(self, *polygons):
        return all(np.all(_to_cartesian(polygon.vertices) @ self.centre > _COSINE_OF_LARGEST_PROJECTABLE_ANGLE)
                   for polygon in polygons)

    def project(self, polygon):
        points = _to_cartesian(polygon.vertices)
        distance_to_plane = points @ self.centre
        return shapely.Polygon(np.stack([points @ self.east, points @ self.north], axis=1) /
                               distance_to_plane[:, np.newaxis])

    def hemisphere_facing(self, direction, around):
        """Get the part of the plane around *around* that lies in the hemisphere facing *direction*."""
        a, b, c = direction @ self.east, direction @ self.north, direction @ self.centre
        reach = 2 * np.abs(around.bounds).max() + 1
        if a == b == 0:
            return shapely.box(-reach, -reach, reach, reach) if c > 0 else shapely.Polygon()
        towards_the_sun = np.array([a, b]) / np.hypot(a, b)
        along_the_terminator = np.array([-towards_the_sun[1], towards_the_sun[0]])
        on_the_terminator = -c * towards_the_sun / np.hypot(a, b)
        reach += np.linalg.norm(on_the_terminator)
        return shapely.Polygon([on_the_terminator - reach * along_the_terminator,
                                on_the_terminator + reach * along_the_terminator,
                                on_the_terminator + reach * (along_the_terminator + towards_the_sun),
                                on_the_terminator + reach * (towards_the_sun - along_the_terminator)])

    def unproject_or_none(self, flat_polygon):
        if flat_polygon.is_empty or flat_polygon.area == 0:
            return None
        return self.unproject(flat_polygon)

    def unproject(self, flat_polygon):
        flat_polygon = shapely.remove_repeated_points(flat_polygon, tolerance=_SAME_POINT_IN_THE_PLANE)
        outline = shapely.get_exterior_ring(shapely.orient_polygons(flat_polygon, exterior_cw=True))
        x, y = shapely.get_coordinates(outline)[:-1].T
        points = self.centre + x[:, np.newaxis] * self.east + y[:, np.newaxis] * self.north
        lons = np.arctan2(points[:, 1], points[:, 0])
        lats = np.arcsin(points[:, 2] / np.linalg.norm(points, axis=1))
        return pyresample.spherical.SphPolygon(np.stack([lons, lats], axis=1))


def intersect(polygon, other):
    """Get the part of the sphere covered by both *polygon* and *other*."""
    plane = _GnomonicPlane(_to_cartesian(np.concatenate([polygon.vertices, other.vertices])).sum(axis=0))
    if not plane.can_project(polygon, other):
        return polygon.intersection(other)
    common = plane.project(polygon).intersection(plane.project(other))
    if common.area > 0 and common.geom_type != "Polygon":
        return polygon.intersection(other)
    return plane.unproject_or_none(common)


def _split_day_and_night_with_pyresample(polygon, utctime):
    sunlit = get_twilight_poly(utctime)
    day = polygon.intersection(sunlit)
    sunlit.invert()
    night = polygon.intersection(sunlit)
    return day, night


def _direction_of_the_sun(utctime):
    from pyorbital import astronomy
    right_ascension, declination = astronomy.sun_ra_dec(utctime)
    subsolar_lonlat = np.array([[right_ascension - astronomy.gmst(utctime), declination]])
    return _to_cartesian(subsolar_lonlat)[0]


def split_day_and_night(polygon, utctime):
    """Split *polygon* in its sunlit and dark parts at *utctime*."""
    plane = _GnomonicPlane(_to_cartesian(polygon.vertices).sum(axis=0))
    if not plane.can_project(polygon):
        return _split_day_and_night_with_pyresample(polygon, utctime)
    flat = plane.project(polygon)
    sunlit = plane.hemisphere_facing(_direction_of_the_sun(utctime), around=flat)
    day, night = flat.intersection(sunlit), flat.difference(sunlit)
    if any(part.area > 0 and part.geom_type != "Polygon" for part in (day, night)):
        return _split_day_and_night_with_pyresample(polygon, utctime)
    return plane.unproject_or_none(day), plane.unproject_or_none(night)
