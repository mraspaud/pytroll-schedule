"""Tests for building the viewer page from a scheduling run."""

import json
from datetime import datetime, timedelta

import pytest

from trollsched.tests.test_viewer import NRK, FakeBoundary, FakePass, _fake_subsolar  # noqa: F401
from trollsched.viewer import geo, records, station
from trollsched.viewer.records import ScheduledEntry

T0 = datetime(2026, 10, 16, 9, 0, 0)


class FakeStation:
    """Station stand-in."""

    def __init__(self, antenna="meos"):
        """Set up a station near Norrköping with no usable area boundary."""
        self.id = "nrk"
        self.coords = NRK
        self.antenna = antenna
        self.area = None
        self.local_horizon = 0


def _trimmed(overpass, start, end):
    result = FakePass(overpass.satellite.name, start, end)
    result.original = overpass
    return result


def test_scheduled_entries_use_received_passes_only():
    """Only passes flagged as received become entries, on the station's antenna, in whole seconds."""
    received = FakePass("noaa20", T0 + timedelta(microseconds=149534), T0 + timedelta(minutes=12, microseconds=4963))
    received.rec = True
    skipped = FakePass("fy3d", T0 + timedelta(hours=1), T0 + timedelta(hours=1, minutes=12))
    skipped.rec = False
    assert station.scheduled_entries([received, skipped], "meos") == [
        ScheduledEntry("noaa20", "meos", T0, T0 + timedelta(minutes=12))]


def test_untrimmed_returns_originals_once():
    """Trimmed passes resolve to their original, and an original seen twice is kept once."""
    original = FakePass("fy3f", T0, T0 + timedelta(minutes=12))
    first = _trimmed(original, T0, T0 + timedelta(minutes=8))
    second = _trimmed(original, T0 + timedelta(minutes=2), T0 + timedelta(minutes=12))
    other = FakePass("noaa20", T0 + timedelta(hours=1), T0 + timedelta(hours=1, minutes=12))
    assert station.untrimmed([first, second, other]) == [original, other]


def test_extra_visible_passes_for_entries_the_scheduler_does_not_know(monkeypatch, tmp_path):
    """Entries without a visibility window get one computed from the TLEs.

    A satellite unknown to the scheduler keeps all its windows (its unscheduled passes matter too);
    a known one only gets the windows the scheduler discarded but another antenna uses.
    """
    computed = []
    windows = [FakePass("npp", T0, T0 + timedelta(minutes=12)),
               FakePass("npp", T0 + timedelta(hours=2), T0 + timedelta(hours=2, minutes=12)),
               FakePass("aqua", T0 + timedelta(hours=1), T0 + timedelta(hours=1, minutes=12))]
    monkeypatch.setattr(station, "load_tles", lambda path: "lookup")
    monkeypatch.setattr(station, "visible_passes",
                        lambda sats, start, end, coords, lookup, horizon: computed.append(sorted(sats)) or windows)
    tle = tmp_path / "tle.txt"
    tle.write_text("")
    full = [FakePass("noaa20", T0, T0 + timedelta(minutes=12)),
            FakePass("aqua", T0 + timedelta(hours=3), T0 + timedelta(hours=3, minutes=12))]
    entries = [ScheduledEntry("noaa20", "cgi", T0, T0 + timedelta(minutes=12)),
               ScheduledEntry("npp", "cgi", T0, T0 + timedelta(minutes=12)),
               ScheduledEntry("aqua", "cgi", T0 + timedelta(hours=1), T0 + timedelta(hours=1, minutes=12)),
               ScheduledEntry("NOAA-20", "cgi", T0, T0 + timedelta(minutes=12))]
    result = station.extra_visible_passes(full, entries, (T0, T0 + timedelta(days=1)), NRK, str(tle))
    assert computed == [["aqua", "npp"]]
    assert result == [windows[0], windows[1], windows[2]]


def test_extra_visible_passes_without_tle_file_warns(caplog):
    """Without a TLE file, avoid-only satellites are skipped with a warning."""
    entries = [ScheduledEntry("npp", "cgi", T0, T0 + timedelta(minutes=12))]
    assert station.extra_visible_passes([], entries, (T0, T0 + timedelta(days=1)), NRK, None) == []
    assert "npp" in caplog.text


def test_area_outline_from_boundary_contour():
    """An area with a boundary gives a rounded lon/lat ring; without one, None."""
    class Area:
        def boundary(self, frequency):
            return type("B", (), {"contour": lambda self: ([0.123, 10.456, 10], [50, 50, 60.789])})()

    assert station.area_outline(Area()) == [[0.12, 50.0], [10.46, 50.0], [10.0, 60.79]]
    assert station.area_outline(None) is None


@pytest.mark.usefixtures("_fake_subsolar")
def test_station_page_combines_station_schedule_and_avoid_lists(tmp_path, monkeypatch):
    """The page holds the station's own passes, the avoid list's antenna, and the unscheduled rest."""
    monkeypatch.setattr(geo, "load_coastlines", lambda path=None, step=1: [])
    monkeypatch.setattr(geo, "sun_elevation_series", lambda *args, **kwargs: (T0, 900, [0.0]))
    avoid = tmp_path / "cgi.xml"
    avoid.write_text(
        "<acquisition-schedule><properties><antenna>cgi</antenna>"
        "<file-start>2026-10-16-09:00:00</file-start><file-end>2026-10-16-12:00:00</file-end></properties>"
        '<pass satellite="noaa21" start-time="2026-10-16-10:00:00" end-time="2026-10-16-10:12:00" />'
        "</acquisition-schedule>")
    own = FakePass("fy3d", T0, T0 + timedelta(minutes=12))
    own.rec = True
    other = FakePass("noaa21", T0 + timedelta(hours=1), T0 + timedelta(hours=1, minutes=12))
    other.rec = False
    left_out = FakePass("metop-b", T0 + timedelta(hours=2), T0 + timedelta(hours=2, minutes=12))
    left_out.rec = False
    passes = [own, other, left_out]
    page = station.station_page(FakeStation(), passes, passes, [str(avoid)], (T0, T0 + timedelta(hours=3)), 60)
    assert '"ant":"meos"' in page
    assert '"ant":"cgi"' in page
    assert '"sat":"metop-b"' in page
    assert '"un":1' in page


def test_station_page_shows_the_plan_in_force_before_the_run(tmp_path, monkeypatch):
    """Passes from earlier runs fill the past; those the current inputs repeat are not duplicated."""
    from trollsched.tests.test_viewer import _write_xml

    monkeypatch.setattr(geo, "load_coastlines", lambda path=None, step=1: [])
    monkeypatch.setattr(geo, "sun_elevation_series", lambda *args, **kwargs: (T0, 900, [0.0]))
    computed = []
    monkeypatch.setattr(station, "load_tles", lambda path: "lookup")
    monkeypatch.setattr(station, "visible_passes",
                        lambda sats, start, end, coords, lookup, horizon: computed.append((sorted(sats), start, end))
                        or [FakePass("noaa20", T0 - timedelta(hours=20), T0 - timedelta(hours=20, minutes=-12))])
    tle = tmp_path / "tle.txt"
    tle.write_text("")
    earlier = tmp_path / "20261015-090000-request-nrk-2met.xml"
    _write_xml(earlier, "2met", T0 - timedelta(hours=22), [("noaa20", T0 - timedelta(hours=20)),
                                                          ("npp", T0 - timedelta(hours=40))])
    avoid = tmp_path / "20261016-083000-request-nrk-cgi.xml"
    _write_xml(avoid, "cgi", T0 - timedelta(minutes=30), [("noaa21", T0 - timedelta(minutes=15)),
                                                         ("noaa21", T0 + timedelta(hours=1))])
    own = FakePass("fy3d", T0, T0 + timedelta(minutes=12))
    own.rec = True
    page = station.station_page(FakeStation("2met"), [own], [own], [str(avoid)], (T0, T0 + timedelta(hours=3)), 60,
                                tle_file=str(tle), history=str(tmp_path / "*-*-request-nrk-2met.xml"),
                                history_hours=24)
    blob = page[page.index("const DATA = ") + len("const DATA = "):]
    data = json.loads(blob[:blob.index(";\n")])
    starts = sorted((p["sat"], p["s"] - records.timestamp(T0)) for p in data["passes"])
    assert starts == [("fy3d", 0.0), ("noaa20", -20 * 3600.0), ("noaa21", -15 * 60.0), ("noaa21", 3600.0)]
    assert data["span"][0] == records.timestamp(T0 - timedelta(hours=24))
    assert computed[0] == (["fy3d", "noaa20", "noaa21"], T0 - timedelta(hours=24), T0)
    assert all("cov" in p for p in data["passes"] if p["sat"] == "noaa20")


def test_station_page_does_not_recompute_passes_the_scheduler_already_has(tmp_path, monkeypatch):
    """The scheduler's passes start before the schedule does; the past is only computed before them."""
    from trollsched.tests.test_viewer import _write_xml

    monkeypatch.setattr(geo, "load_coastlines", lambda path=None, step=1: [])
    monkeypatch.setattr(geo, "sun_elevation_series", lambda *args, **kwargs: (T0, 900, [0.0]))
    monkeypatch.setattr(station, "load_tles", lambda path: "lookup")
    # the TLE computation returns the same window the scheduler knows, plus an older one
    monkeypatch.setattr(station, "visible_passes",
                        lambda sats, start, end, coords, lookup, horizon: [
                            FakePass("fy3d", T0 - timedelta(hours=1), T0 - timedelta(minutes=48)),
                            FakePass("fy3d", T0 - timedelta(hours=20), T0 - timedelta(hours=19, minutes=48))])
    tle = tmp_path / "tle.txt"
    tle.write_text("")
    earlier = tmp_path / "20261015-090000-request-nrk-meos.xml"
    _write_xml(earlier, "meos", T0 - timedelta(hours=22), [("fy3d", T0 - timedelta(hours=1)),
                                                          ("fy3d", T0 - timedelta(hours=20))])
    # the scheduler started two hours before the schedule, so it already has the pass an hour ago
    known = FakePass("fy3d", T0 - timedelta(hours=1), T0 - timedelta(minutes=48))
    known.rec = False
    page = station.station_page(FakeStation("meos"), [known], [known], [], (T0, T0 + timedelta(hours=3)), 60,
                                tle_file=str(tle), history=str(tmp_path / "*-*-request-nrk-meos.xml"),
                                history_hours=24)
    blob = page[page.index("const DATA = ") + len("const DATA = "):]
    data = json.loads(blob[:blob.index(";\n")])
    assert sorted(p["s"] - records.timestamp(T0) for p in data["passes"]) == [-20 * 3600.0, -3600.0]
    assert all(p["ant"] == "meos" for p in data["passes"])
