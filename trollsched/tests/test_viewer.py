"""Tests for the HTML schedule viewer."""

import json
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from defusedxml.common import EntitiesForbidden

from trollsched.viewer import build_page, geo, records, sources
from trollsched.viewer.records import ScheduledEntry, build_records

T0 = datetime(2026, 10, 16, 9, 0, 0)
NRK = (16.15, 58.58, 0.05)


class FakeBoundary:
    """A rectangular swath: top row at *lat0*, bottom row at *lat1*, between lon -10 and 10."""

    def __init__(self, lat0=40.0, lat1=70.0, along=5, across=4):
        """Set up the rows and (short) sides."""
        self.top_lons = np.linspace(-10, 10, across)
        self.top_lats = np.full(across, lat0)
        self.bottom_lons = np.linspace(10, -10, across)
        self.bottom_lats = np.full(across, lat1)
        # trollsched sides are decimated and may stop short of the last row
        self.right_lons = np.full(along, 10.0)
        self.right_lats = np.linspace(lat0, lat1 - 5, along)
        self.left_lons = np.full(along, -10.0)
        self.left_lats = np.linspace(lat1 - 5, lat0, along)


class FakeOrb:
    """Orbit stand-in with deterministic look angles."""

    def get_orbit_number(self, utctime):
        """Return a fixed orbit number."""
        return 12345

    def get_observer_look(self, utctime, lon, lat, alt):
        """Return azimuth 180 and an elevation that peaks mid-pass."""
        return 180.0, 42.0

    def get_lonlatalt(self, utctime):
        """Return a sub-satellite point moving north with time."""
        return 10.0, 40.0 + (utctime - T0).total_seconds() / 60, 800.0


class FakePass:
    """Minimal Pass look-alike."""

    def __init__(self, satellite, risetime, falltime, boundary=None, coverage=0.5):
        """Set up the pass with a fake orbit and swath."""
        self.satellite = SimpleNamespace(name=satellite, schedule_name=satellite)
        self.risetime, self.falltime = risetime, falltime
        self.uptime = risetime + (falltime - risetime) / 2
        self.orb = FakeOrb()
        self._boundary = boundary or FakeBoundary()
        self._coverage = coverage
        self.score = {}

    @property
    def boundary(self):
        """Return the fake swath (recreated after trimming, like the real one)."""
        if self._boundary is None:
            self._boundary = FakeBoundary()
        return self._boundary

    def pass_direction(self):
        """Mimic trollsched's direction from sub-satellite latitudes."""
        return "ascending"

    def area_coverage(self, area):
        """Return the configured coverage fraction."""
        return self._coverage


@pytest.fixture
def _fake_subsolar(monkeypatch):
    monkeypatch.setattr(geo, "subsolar_point", lambda utctime: [0.0, 0.0])


def test_resample_boundary_keeps_the_four_corners():
    """The ends of the first and last scan rows are always vertices, in order."""
    polygon = geo.resample_boundary(FakeBoundary(), 16)
    assert len(polygon) == 16
    assert polygon[0] == [-10.0, 40.0]
    assert [10.0, 40.0] in polygon
    assert [10.0, 70.0] in polygon
    assert [-10.0, 70.0] in polygon
    assert polygon.index([10.0, 40.0]) < polygon.index([10.0, 70.0]) < polygon.index([-10.0, 70.0])


def test_resample_boundary_ignores_short_sides():
    """Side points stopping short of the last row do not add a chamfer."""
    polygon = geo.resample_boundary(FakeBoundary(), 8)
    lats = [lat for _, lat in polygon]
    assert max(lats) == 70.0
    assert all(lon in (-10.0, 10.0) for lon, lat in polygon if 41.0 < lat < 69.0)


def test_sample_segment_spaces_points_by_arc_length():
    """Points along a meridian are evenly spaced in latitude."""
    points = geo.xyz([0, 0, 0], [0, 10, 60])
    samples, length = geo.sample_segment(points, 6)
    assert pytest.approx(length, abs=1e-6) == np.radians(60)
    assert [lat for _, lat in samples] == [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]


def test_swath_track_runs_from_first_to_last_scan():
    """The track starts on the top row, ends on the bottom row, and has a midpoint."""
    start, mid, end = geo.swath_track(FakeBoundary())
    assert start[0] == 0.0
    assert abs(start[1] - 40) < 0.5
    assert end[0] == 0.0
    assert abs(end[1] - 70) < 0.5
    assert 40 < mid[1] < 70


def test_subsolar_point_is_near_the_equator_at_equinox():
    """Around the equinox at 12 UTC the sun is overhead close to (0, 0)."""
    lon, lat = geo.subsolar_point(datetime(2026, 3, 20, 12, 0))
    assert abs(lon) < 3
    assert abs(lat) < 1


def test_sun_elevation_series_covers_the_span():
    """One sample per step, inclusive, with night and day present over a full day."""
    start, step, elevations = geo.sun_elevation_series(T0, T0 + timedelta(hours=24), *NRK[:2])
    assert start == T0
    assert step == 900
    assert len(elevations) == 97
    assert min(elevations) < 0 < max(elevations)


@pytest.mark.usefixtures("_fake_subsolar")
def test_build_records_matches_scheduled_entries_to_visibility():
    """A scheduled pass gets geometry from the visibility window it falls in."""
    overpass = FakePass("noaa20", T0, T0 + timedelta(minutes=12))
    entry = ScheduledEntry("noaa20", "cgi", T0, T0 + timedelta(minutes=12))
    (record,) = build_records([overpass], [entry], NRK, station="nrk")
    assert record["ant"] == "cgi"
    assert record["orbit"] == 12345
    assert record["dir"] == "ascending"
    assert record["max_el"] == 42
    assert len(record["cov"]) == records.COVERAGE_POINTS
    assert "un" not in record
    assert "fs" not in record


@pytest.mark.usefixtures("_fake_subsolar")
def test_build_records_flags_trimmed_passes_with_their_full_window():
    """A scheduled pass noticeably shorter than its visibility carries the full window and swath."""
    overpass = FakePass("fy3f", T0, T0 + timedelta(minutes=12))
    entry = ScheduledEntry("fy3f", "meos", T0 + timedelta(minutes=3), T0 + timedelta(minutes=12))
    (record,) = build_records([overpass], [entry], NRK)
    assert record["fs"] == records.timestamp(T0)
    assert record["fe"] == records.timestamp(T0 + timedelta(minutes=12))
    assert len(record["fcov"]) == records.COVERAGE_POINTS


@pytest.mark.usefixtures("_fake_subsolar")
def test_build_records_tolerates_small_differences():
    """A few seconds of difference is not a trim."""
    overpass = FakePass("fy3f", T0, T0 + timedelta(minutes=12))
    entry = ScheduledEntry("fy3f", "meos", T0 + timedelta(seconds=3), T0 + timedelta(minutes=12))
    (record,) = build_records([overpass], [entry], NRK)
    assert "fs" not in record


@pytest.mark.usefixtures("_fake_subsolar")
def test_build_records_lists_unscheduled_passes_and_what_they_lost_to():
    """A visible pass absent from every schedule is flagged, with the overlapping scheduled passes."""
    winner = FakePass("noaa20", T0, T0 + timedelta(minutes=12))
    loser = FakePass("fy3d", T0 + timedelta(minutes=5), T0 + timedelta(minutes=17))
    entry = ScheduledEntry("noaa20", "cgi", T0, T0 + timedelta(minutes=12))
    result = build_records([winner, loser], [entry], NRK, delay=timedelta(seconds=60))
    unscheduled = [r for r in result if r.get("un")]
    assert len(unscheduled) == 1
    assert unscheduled[0]["sat"] == "fy3d"
    assert unscheduled[0]["lost_to"] == [f"noaa20|cgi|{records.timestamp(T0):.0f}"]


@pytest.mark.usefixtures("_fake_subsolar")
def test_build_records_matches_names_across_conventions():
    """Schedule names and configured names only need to match once normalised."""
    overpass = FakePass("NOAA-20", T0, T0 + timedelta(minutes=12))
    entry = ScheduledEntry("noaa20", "cgi", T0, T0 + timedelta(minutes=12))
    (record,) = build_records([overpass], [entry], NRK)
    assert record["ant"] == "cgi"


@pytest.mark.usefixtures("_fake_subsolar")
def test_build_records_keeps_entries_without_visibility():
    """An entry no visibility window explains is still drawn, without geometry."""
    entry = ScheduledEntry("npp", "cgi", T0, T0 + timedelta(minutes=12))
    (record,) = build_records([], [entry], NRK)
    assert record["ant"] == "cgi"
    assert "cov" not in record


class FakeArea:
    """Area of interest stand-in: a lon/lat box with a spherical polygon."""

    def __init__(self, lon0, lon1, lat0, lat1):
        """Build the polygon from the box corners."""
        from pyresample.spherical import SphPolygon
        # clockwise in lon/lat, which is what pyresample needs for the area to be the inside
        self.poly = SphPolygon(np.radians(np.array([[lon0, lat0], [lon0, lat1], [lon1, lat1], [lon1, lat0]])))


def test_planar_fraction_of_contained_and_half_covered_area():
    """A swath around the whole area covers 100 %, one over its western half about 50 %."""
    area = FakeArea(0, 20, 50, 60)
    assert records.planar_fraction([[-5, 45], [25, 45], [25, 65], [-5, 65]], area) == pytest.approx(1.0, abs=0.01)
    assert records.planar_fraction([[-5, 45], [10, 45], [10, 65], [-5, 65]], area) == pytest.approx(0.5, abs=0.02)


@pytest.mark.usefixtures("_fake_subsolar")
def test_build_records_includes_area_coverage():
    """With an area of interest, the covered percentage is included, from the swath polygon."""
    area = FakeArea(-10, 10, 40, 70)
    overpass = FakePass("noaa20", T0, T0 + timedelta(minutes=12))
    entry = ScheduledEntry("noaa20", "cgi", T0, T0 + timedelta(minutes=12))
    (record,) = build_records([overpass], [entry], NRK, area=area)
    assert record["area_pct"] == pytest.approx(100.0, abs=1)


def test_area_fraction_prefers_the_scheduler_cache():
    """When the scheduler already intersected the pass with the area, that result is reused."""
    area = FakeArea(-10, 10, 40, 70)
    overpass = FakePass("noaa20", T0, T0 + timedelta(minutes=12))
    overpass.score[area] = (FakeArea(-10, 10, 40, 55).poly, 0.5)
    expected = (np.sin(np.radians(55)) - np.sin(np.radians(40))) / (np.sin(np.radians(70)) - np.sin(np.radians(40)))
    assert records.area_fraction(overpass, area) == pytest.approx(expected, abs=0.01)
    overpass.score[area] = (None, 0)
    assert records.area_fraction(overpass, area) == 0.0


def test_read_schedule_reads_antenna_and_span(tmp_path):
    """Entries carry the antenna from the file properties."""
    path = tmp_path / "sched.xml"
    path.write_text(
        "<acquisition-schedule><properties><antenna>cgi</antenna><station>nrk</station>"
        "<file-start>2026-10-16-09:00:00</file-start><file-end>2026-10-16-12:00:00</file-end></properties>"
        '<pass satellite="noaa20" start-time="2026-10-16-09:16:55" end-time="2026-10-16-09:30:20" />'
        "</acquisition-schedule>")
    properties, entries, span = sources.read_schedule(path)
    assert properties["station"] == "nrk"
    assert entries == [ScheduledEntry("noaa20", "cgi", datetime(2026, 10, 16, 9, 16, 55),
                                      datetime(2026, 10, 16, 9, 30, 20))]
    assert span == (datetime(2026, 10, 16, 9, 0), datetime(2026, 10, 16, 12, 0))


def test_read_schedule_falls_back_to_the_file_name_for_the_antenna(tmp_path):
    """Old schedules without an antenna name get one from the file name."""
    path = tmp_path / "old-request.xml"
    path.write_text(
        "<acquisition-schedule><properties>"
        "<file-start>2026-10-16-09:00:00</file-start><file-end>2026-10-16-12:00:00</file-end></properties>"
        '<pass satellite="noaa20" start-time="2026-10-16-09:16:55" end-time="2026-10-16-09:30:20" />'
        "</acquisition-schedule>")
    _, entries, _ = sources.read_schedule(path)
    assert entries[0].antenna == "old-request"
    _, entries, _ = sources.read_schedule(path, default_antenna="meos")
    assert entries[0].antenna == "meos"


def test_read_schedule_rejects_xml_entities(tmp_path):
    """Entity declarations are rejected rather than expanded."""
    path = tmp_path / "schedule.xml"
    path.write_text(
        '<!DOCTYPE acquisition-schedule [<!ENTITY antenna "expanded">]>'
        "<acquisition-schedule><properties><antenna>&antenna;</antenna>"
        "<file-start>2026-10-18-10:00:00</file-start>"
        "<file-end>2026-10-18-12:00:00</file-end></properties></acquisition-schedule>")
    with pytest.raises(EntitiesForbidden):
        sources.read_schedule(path)


def test_load_tles_resolves_schedule_names(tmp_path):
    """Schedule names map to TLE names through aliases and normalisation."""
    path = tmp_path / "tle.txt"
    path.write_text(
        "NOAA-20\n"
        "1 43013U 17073A   26288.73628853  .00000000  00000+0  44233-4 0 00010\n"
        "2 43013  98.7872 227.1682 0000217  86.9600 235.4436 14.19531216461574\n"
        "SUOMI NPP\n"
        "1 37849U 11061A   26288.94129890  .00000084  00000+0  60842-4 0  9993\n"
        "2 37849  98.8060 229.0369 0001795  15.2096 344.9134 14.19538993775571\n"
        "AWS\n"
        "1 60543U 24149CD  26288.91547725  .00000671  00000+0  75562-4 0  9996\n"
        "2 60543  97.6683 355.8483 0003572  80.7669 279.3953 14.89798229117273\n")
    lookup = sources.load_tles(path, {"jpss1": "NOAA-20"})
    assert lookup("noaa20").line1.startswith("1 43013")
    assert lookup("npp").line1.startswith("1 37849")
    assert lookup("aws-pfm").line1.startswith("1 60543")
    assert lookup("jpss1").line1.startswith("1 43013")
    assert lookup("metop-b") is None


@pytest.mark.parametrize(("geometry_type", "depth"), [
    ("LineString", 0), ("Polygon", 1), ("MultiLineString", 1), ("MultiPolygon", 2),
])
def test_coastlines_preserve_geometry_sampling(geometry_type, depth, monkeypatch):
    """Sample supported geometry types, rounding points and dropping short rings."""
    ring = [[index + 0.12345, index + 0.98765] for index in range(5)]
    coordinates = ring
    for _ in range(depth):
        coordinates = [coordinates]
    shapes = [SimpleNamespace(__geo_interface__={"type": geometry_type, "coordinates": coordinates}),
              SimpleNamespace(__geo_interface__={"type": "LineString", "coordinates": ring[:2]})]
    monkeypatch.setitem(sys.modules, "shapefile",
                        SimpleNamespace(Reader=lambda path: SimpleNamespace(shapes=lambda: shapes)))
    assert geo.load_coastlines("unused.shp", 2) == [[[0.12, 0.99], [2.12, 2.99], [4.12, 4.99]]]


def test_build_page_embeds_data_and_assets():
    """The page is self-contained: data as JSON, CSS and JS inlined, no placeholders left."""
    record = {"sat": "noaa20", "name": "NOAA20", "ant": "cgi", "station": "nrk",
              "s": records.timestamp(T0), "e": records.timestamp(T0 + timedelta(minutes=10))}
    page = build_page([record], (T0, T0 + timedelta(hours=2)), NRK, coastlines=[[[0, 0], [1, 1], [2, 0]]],
                      title="Test page", sources=["a.xml"])
    for placeholder in ("__DATA__", "__CSS__", "__JS__", "__TITLE__"):
        assert placeholder not in page
    assert "<title>Test page</title>" in page
    blob = page[page.index("const DATA = ") + len("const DATA = "):]
    data = json.loads(blob[:blob.index(";\n")])
    assert data["passes"] == [record]
    assert data["map"]["lat"] == NRK[1]
    assert len(data["sun"]["elevation"]) == 9
    assert data["sources"] == ["a.xml"]
    assert "function draw" in page
