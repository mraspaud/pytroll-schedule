"""Geometry helpers for the schedule viewer: swath simplification, coastlines and sun positions."""

import logging
from datetime import timedelta

import numpy as np

logger = logging.getLogger(__name__)

# Natural Earth 110m countries via cartopy, used when no shapefile is given.
NATURAL_EARTH = dict(resolution="110m", category="cultural", name="admin_0_countries")


def xyz(lons, lats):
    """Convert degree lon/lat arrays to unit vectors, one per row."""
    lons = np.radians(np.asarray(lons, dtype=float))
    lats = np.radians(np.asarray(lats, dtype=float))
    return np.column_stack((np.cos(lats) * np.cos(lons),
                            np.cos(lats) * np.sin(lons),
                            np.sin(lats)))


def lonlat(vector):
    """Convert a vector to a rounded ``[lon, lat]`` pair in degrees."""
    vector = np.asarray(vector, dtype=float)
    vector = vector / np.linalg.norm(vector)
    return [round(float(np.degrees(np.arctan2(vector[1], vector[0]))), 2),
            round(float(np.degrees(np.arcsin(np.clip(vector[2], -1, 1)))), 2)]


def sample_segment(points, npoints):
    """Sample *npoints* evenly spaced by arc length along an open polyline of unit vectors.

    The first vertex is included and the last excluded, since the last one is
    the first vertex of the next segment.  Returns the samples and the segment length.
    """
    seg = np.arccos(np.clip(np.sum(points[:-1] * points[1:], axis=1), -1, 1))
    cum = np.concatenate(([0.0], np.cumsum(seg)))
    out = []
    for target in np.linspace(0, cum[-1], npoints, endpoint=False):
        index = min(int(np.searchsorted(cum, target, side="right") - 1), len(seg) - 1)
        fraction = (target - cum[index]) / seg[index] if seg[index] > 0 else 0.0
        out.append(lonlat(slerp(points[index], points[index + 1], fraction)))
    return out, float(cum[-1])


def slerp(a, b, fraction):
    """Interpolate along the great circle from unit vector *a* to *b*."""
    theta = np.arccos(np.clip(np.dot(a, b), -1, 1))
    if theta < 1e-9:
        return a
    return (np.sin((1 - fraction) * theta) * a + np.sin(fraction * theta) * b) / np.sin(theta)


def resample_boundary(boundary, npoints):
    """Reduce a swath boundary to about *npoints* vertices.

    The four swath corners (the ends of the first and last scan) are always
    kept; the remaining points are spread over the four sides in proportion to
    their length.  The sides only contribute interior points, because the
    decimated sides of a trollsched boundary do not always reach the end rows.
    """
    top = xyz(boundary.top_lons, boundary.top_lats)
    bottom = xyz(boundary.bottom_lons, boundary.bottom_lats)
    right = xyz(boundary.right_lons, boundary.right_lats)
    left = xyz(boundary.left_lons, boundary.left_lats)
    sides = [top,
             np.vstack((top[-1:], right[1:-1], bottom[:1])),
             bottom,
             np.vstack((bottom[-1:], left[1:-1], top[:1]))]
    lengths = [sample_segment(side, 1)[1] for side in sides]
    counts = [1 + n for n in _share(max(npoints - 4, 0), lengths)]
    out = []
    for side, count in zip(sides, counts):
        out.extend(sample_segment(side, count)[0])
    return out


def _share(total, weights):
    """Split *total* into integers proportional to *weights* (largest remainder method)."""
    weight_sum = sum(weights) or 1.0
    exact = [total * w / weight_sum for w in weights]
    counts = [int(e) for e in exact]
    for index in sorted(range(len(weights)), key=lambda i: exact[i] - counts[i], reverse=True)[:total - sum(counts)]:
        counts[index] += 1
    return counts


def densify_ring(ring, per_edge):
    """Insert *per_edge* - 1 great-circle points on every edge of a closed lon/lat ring."""
    points = xyz([p[0] for p in ring], [p[1] for p in ring])
    out = []
    for index in range(len(points)):
        a, b = points[index], points[(index + 1) % len(points)]
        for step in range(per_edge):
            out.append(lonlat(slerp(a, b, step / per_edge)))
    return out


def swath_track(boundary):
    """Get the swath centre line as ``[[lon, lat], ...]`` from first scan to last scan."""
    top = xyz(boundary.top_lons, boundary.top_lats)
    bottom = xyz(boundary.bottom_lons, boundary.bottom_lats)
    start = top.mean(axis=0)
    end = bottom.mean(axis=0)
    return [lonlat(start), lonlat(start + end), lonlat(end)]


def ring_points(lons, lats, step=1):
    """Round and decimate a lon/lat ring into ``[[lon, lat], ...]``."""
    return [[round(float(lon), 2), round(float(lat), 2)] for lon, lat in zip(lons[::step], lats[::step])]


def load_coastlines(path=None, step=1):
    """Return a list of lon/lat rings from a shapefile (or Natural Earth via cartopy when *path* is None)."""
    if path is None:
        try:
            import cartopy.io.shapereader as shpreader
            path = shpreader.natural_earth(**NATURAL_EARTH)
        except Exception as err:  # noqa: BLE001 - a map without coastlines is better than no page
            logger.warning("No coastlines available (%s); map drawn without them", err)
            return []
    try:
        import shapefile
        geometries = [shape.__geo_interface__ for shape in shapefile.Reader(str(path)).shapes()]
    except ImportError:
        import cartopy.io.shapereader as shpreader
        from shapely.geometry import mapping
        geometries = [mapping(geometry) for geometry in shpreader.Reader(str(path)).geometries()]

    lines = []
    for geometry in geometries:
        for ring in geometry_rings(geometry):
            points = [[round(x, 2), round(y, 2)] for x, y in ring[::step]]
            if len(points) > 2:
                lines.append(points)
    return lines


def geometry_rings(geometry):
    """Yield the coordinate rings of a GeoJSON-like geometry."""
    geometry_type, coordinates = geometry["type"], geometry["coordinates"]
    if geometry_type == "LineString":
        yield coordinates
    elif geometry_type in ("Polygon", "MultiLineString"):
        yield from coordinates
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            yield from polygon


def subsolar_point(utctime):
    """Get the ``[lon, lat]`` of the point where the sun is at the zenith."""
    from pyorbital import astronomy
    ra, dec = astronomy.sun_ra_dec(utctime)
    lon = np.degrees(ra - astronomy.gmst(utctime))
    lon = (lon + 180) % 360 - 180
    return [round(float(lon), 2), round(float(np.degrees(dec)), 2)]


def sun_elevation_series(start, end, lon, lat, step=timedelta(minutes=15)):
    """Sample the sun elevation at a place from *start* to *end*, every *step*.

    Returns ``(first_time, step_seconds, elevations)`` for compact embedding.
    """
    from pyorbital import astronomy
    count = int((end - start) / step) + 1
    times = np.array([start + step * i for i in range(count)], dtype="datetime64[us]")
    elevations = 90 - astronomy.sun_zenith_angle(times, lon, lat)
    return start, int(step.total_seconds()), [round(float(e), 1) for e in elevations]


def horizon_radius(height_km, earth_radius_km=6371.0):
    """Get the radius of the visible disc from *height_km* above the Earth, in Earth radii.

    This is where the near-sided perspective projection puts the horizon; the
    page's map draws the disc with this radius.
    """
    ratio = (earth_radius_km + height_km) / earth_radius_km
    return ratio / (ratio + 1) * np.sqrt(1 - 1 / ratio ** 2)


def thumbnail_area(coords, height_km=35786.0, size=800, area_id="schedule_viewer"):
    """Get the area definition of the page's map, for thumbnails drawn on top of it.

    An image resampled onto this area (with transparency outside the swath)
    overlays the map exactly: a spherical near-sided perspective centred on
    the station at ``coords`` (lon, lat, ...), seen from *height_km*, covering
    the whole visible disc in a *size* × *size* image.
    """
    from pyresample import AreaDefinition

    earth_radius = 6371000.0
    half = horizon_radius(height_km, earth_radius / 1000) * earth_radius
    projection = {"proj": "nsper", "lon_0": coords[0], "lat_0": coords[1], "h": height_km * 1000,
                  "R": earth_radius, "units": "m", "no_defs": None, "type": "crs"}
    return AreaDefinition(area_id, "Schedule viewer map, for thumbnails", area_id, projection, size, size,
                          (-half, -half, half, half))
