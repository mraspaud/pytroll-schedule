"""Behavioral tests for scheduling and publication."""
import pickle
from copy import copy
from datetime import timedelta, timezone
from multiprocessing import get_all_start_methods, get_context
from types import SimpleNamespace

import defusedxml.ElementTree as ET
import pytest

from trollsched.schedule import Scheduler, Station, combined_stations, parse_args, run
from trollsched.tests.polygons import AreaOfInterest, clockwise_polygon


class StationArea(AreaOfInterest):
    """A serializable area stub with a fixed outline."""

    area_id = "test"

    def boundary(self, frequency):
        """Return the fixed area outline."""
        return SimpleNamespace(contour_poly=self.poly)


class InlineProcess:
    """Execute a process-boundary task synchronously in unit tests."""

    def __init__(self, target, args):
        """Store the task."""
        self.target, self.args = target, args

    def start(self):
        """Execute the task."""
        self.target(*self.args)

    def join(self):
        """The task has already completed."""


@pytest.fixture
def station_setup(tmp_path, fake_noaa20_viirs_pass_instance, monkeypatch):
    """Provide fixed orbital predictions and a local publishing destination."""
    overpass = fake_noaa20_viirs_pass_instance
    start = overpass.risetime - timedelta(minutes=1)
    windows = [(overpass.risetime + offset, overpass.falltime + offset, overpass.uptime + offset)
               for offset in (timedelta(), timedelta(minutes=100))]
    orbit = overpass.orb
    monkeypatch.setattr(orbit.tle, "epoch", start)
    monkeypatch.setattr(type(orbit), "get_next_passes", lambda *args, **kwargs: windows)
    monkeypatch.setattr(type(orbit), "__init__", lambda self, *args, **kwargs: self.__dict__.update(orbit.__dict__))
    outline = clockwise_polygon((-20, 80), (60, 80), (60, 30), (-20, 30))
    area = StationArea(outline)
    station = Station("one", "One", 16, 58, 0, area, [overpass.satellite])
    patterns = {key: str(tmp_path / filename) for key, filename in {
        "dir_output": ".", "dir_plots": "plots", "file_xml": "{station}-{mode}.xml",
        "file_sci": "{station}.sch", "file_meos": "{station}.meos",
        "file_metno_xml": "{station}.metno.xml", "file_metno_xml_all": "{station}-all.metno.xml",
        "file_graph": "{station}-{mode}.graph",
    }.items()}
    scheduler = Scheduler([station], 4, 4, 0, None, patterns, "TEST", {}, None)
    scheduler.opts = parse_args(["-c", "unused", "-x"])
    scheduler.opts.output_dir = str(tmp_path)
    scheduler.opts.comb = False
    return station, scheduler, start


@pytest.fixture
def coordinated_setup(station_setup):
    """Provide two stations using the same fixed orbital predictions."""
    station, scheduler, start = station_setup
    second = copy(station)
    second.id = "two"
    scheduler.stations.append(second)
    return scheduler, start


@pytest.mark.parametrize("flags", [("-x",), ("-r",), ("-x", "-r")])
def test_station_publishes_requests_and_optional_reports(flags, station_setup, tmp_path, monkeypatch):
    """Report mode still transfers a request and publishes a separate local report."""
    station, scheduler, start = station_setup
    scheduler.opts = parse_args(["-c", "unused", *flags])
    scheduler.opts.output_dir = str(tmp_path)
    scheduler.opts.comb = False
    transferred = []
    monkeypatch.setattr("trollsched.schedule.send_file", lambda url, file: transferred.append(file))
    _, passes = station.single_station(scheduler, start, str(tmp_path / "sometles.txt"))
    request = ET.parse(tmp_path / "one-request.xml").getroot()
    assert request.findtext("properties/type") == "request"
    assert len(request.findall("pass")) == len(passes) == 2
    assert all(overpass.rec for overpass in passes)
    assert transferred == [str(tmp_path / "one-request.xml")]
    assert (tmp_path / "one-report.xml").exists() == ("-r" in flags)


def test_station_antenna_is_published_in_request(station_setup, tmp_path, monkeypatch):
    """The antenna configured for a station ends up in its request file."""
    station, scheduler, start = station_setup
    station_with_antenna = Station(station.id, station.name, *station.coords, station.area, station.satellites,
                                   antenna="ANT-1")
    monkeypatch.setattr("trollsched.schedule.send_file", lambda url, file: None)
    station_with_antenna.single_station(scheduler, start, str(tmp_path / "sometles.txt"))
    assert ET.parse(tmp_path / "one-request.xml").getroot().findtext("properties/antenna") == "ANT-1"


def test_station_persists_graph_passes_and_all_product_formats(station_setup, tmp_path, monkeypatch):
    """Preserve products, received flags, and report images in coordinated mode."""
    station, scheduler, start = station_setup
    scheduler.opts = parse_args(["-c", "unused", "-r", "-p", "--scisys", "--meos", "--metno-xml"])
    scheduler.opts.output_dir, scheduler.opts.comb = str(tmp_path), True
    monkeypatch.setattr("trollsched.drawing.save_fig", lambda overpass, **kwargs: setattr(overpass, "fig", "plot.png"))
    graph, passes = station.single_station(scheduler, start, str(tmp_path / "sometles.txt"))
    with (tmp_path / "allpasses.one.pkl").open("rb") as stream:
        restored = pickle.load(stream)
    assert [(str(p), p.rec) for p in restored] == [(str(p), True) for p in passes]
    assert (tmp_path / "one-report.graph.npz").exists()
    assert "digraph schedule" in (tmp_path / "one-report.graph.gv").read_text()
    assert graph.order == len(passes) + 2
    assert (tmp_path / "one.sch").read_text().startswith("#Orbital elements")
    assert (tmp_path / "one.meos").stat().st_size > 0
    for filename in ("one.metno.xml", "one-all.metno.xml", "one-report.xml"):
        root = ET.parse(tmp_path / filename).getroot()
        assert root.findtext("properties/type") == "report"
        assert len(root.findall("pass")) == 2
    assert all(p.attrib["img"] == "plot.png" for p in root.findall("pass"))


@pytest.mark.parametrize("flags", [("-x",), ("-r",), ("-x", "-r")])
def test_coordinated_station_products_preserve_modes_and_received_passes(
        flags, coordinated_setup, tmp_path, monkeypatch):
    """Coordinated products retain station names, request transfers, and selected flags."""
    scheduler, start = coordinated_setup
    predictions = {s.id: s.single_station(scheduler, start, str(tmp_path / "sometles.txt"))
                   for s in scheduler.stations}
    scheduler.opts = parse_args(["-c", "unused", *flags, "-g", "--scisys", "--meos", "--metno-xml"])
    scheduler.opts.output_dir = str(tmp_path)
    transferred = []
    monkeypatch.setattr("trollsched.schedule.send_file", lambda url, file: transferred.append(file))
    combined_stations(scheduler, start, {s: value[0] for s, value in predictions.items()},
                      {s: value[1] for s, value in predictions.items()})
    assert transferred == [str(tmp_path / f"{s}-comb-request.xml") for s in ("one", "two")]
    mode = "request" if "-x" in flags else "report"
    assert "\\n" in (tmp_path / f"comb-{mode}.graph.gv").read_text()
    for station_id, (_, passes) in predictions.items():
        root = ET.parse(tmp_path / f"{station_id}-comb-request.xml").getroot()
        assert root.findtext("properties/station") == station_id
        assert len(root.findall("pass")) == sum(p.rec for p in passes)
        assert (tmp_path / f"{station_id}-comb-report.xml").exists() == ("-r" in flags)
        assert (tmp_path / f"{station_id}-comb.meos").stat().st_size > 0
        assert ET.parse(tmp_path / f"{station_id}-comb.metno.xml").findtext("properties/type") == "request"


def test_coordinated_station_requests_carry_each_stations_antenna(coordinated_setup, tmp_path, monkeypatch):
    """Combined requests keep the antenna configured for their own station."""
    scheduler, start = coordinated_setup
    for station, antenna in zip(scheduler.stations, ("ANT-1", "ANT-2")):
        station.antenna = antenna
    predictions = {s.id: s.single_station(scheduler, start, str(tmp_path / "sometles.txt"))
                   for s in scheduler.stations}
    monkeypatch.setattr("trollsched.schedule.send_file", lambda url, file: None)
    combined_stations(scheduler, start, {s: value[0] for s, value in predictions.items()},
                      {s: value[1] for s, value in predictions.items()})
    for station_id, antenna in (("one", "ANT-1"), ("two", "ANT-2")):
        root = ET.parse(tmp_path / f"{station_id}-comb-request.xml").getroot()
        assert root.findtext("properties/antenna") == antenna


@pytest.mark.parametrize("execution_flags", [(), ("--multiproc",)])
def test_cli_station_execution_preserves_schedules_and_artifacts(
        execution_flags, coordinated_setup, tmp_path, monkeypatch):
    """Both execution paths publish the same coordinated pass windows and station artifacts."""
    scheduler, start = coordinated_setup
    scheduler.patterns["file_graph"] = str(tmp_path / "{station}.graph")
    monkeypatch.setattr("trollsched.schedule.utils.read_config", lambda filename: scheduler)
    monkeypatch.setattr("multiprocessing.Process", InlineProcess)
    run(["-c", "unused", "-x", "-t", str(tmp_path / "sometles.txt"), "-o", str(tmp_path),
         "--start-time", start.isoformat(), *execution_flags])
    with (tmp_path / "opts.pkl").open("rb") as stream:
        assert pickle.load(stream).comb
    for station_id in ("one", "two"):
        request = ET.parse(tmp_path / f"{station_id}-request.xml").getroot()
        assert [p.attrib["start-time"] for p in request.findall("pass")] == [
            "2024-09-17-01:25:52", "2024-09-17-03:05:52",
        ]
        assert (tmp_path / f"{station_id}.graph.npz").exists()
        assert (tmp_path / f"allpasses.{station_id}.pkl").exists()
        assert (tmp_path / f"{station_id}-comb-request.xml").exists()


@pytest.mark.skipif("fork" not in get_all_start_methods(), reason="Fixed orbital stubs require fork")
def test_native_processes_match_sequential_products(coordinated_setup, tmp_path, monkeypatch):
    """Real child processes publish the same selected passes as sequential execution."""
    scheduler, start = coordinated_setup
    scheduler.patterns["file_graph"] = str(tmp_path / "{station}.graph")
    monkeypatch.setattr("trollsched.schedule.utils.read_config", lambda filename: scheduler)
    monkeypatch.setattr("multiprocessing.Process", get_context("fork").Process)
    args = ["-c", "unused", "-x", "-t", str(tmp_path / "sometles.txt"), "-o", str(tmp_path),
            "--start-time", start.isoformat()]
    run(args)
    filenames = [tmp_path / f"{s}-comb-request.xml" for s in ("one", "two")]
    expected = [[p.attrib for p in ET.parse(file).findall("pass")] for file in filenames]
    run([*args, "--multiproc"])
    assert [[p.attrib for p in ET.parse(file).findall("pass")] for file in filenames] == expected


@pytest.mark.parametrize(("flag", "filename"), [
    ("--scisys", "one.sch"), ("--meos", "one.meos"), ("--metno-xml", "one.metno.xml"),
])
def test_non_xml_station_products_do_not_publish_requests(flag, filename, station_setup, tmp_path, monkeypatch):
    """Other output formats remain independently usable without XML transfers."""
    station, scheduler, start = station_setup
    scheduler.opts = parse_args(["-c", "unused", flag])
    scheduler.opts.output_dir, scheduler.opts.comb = str(tmp_path), False
    transferred = []
    monkeypatch.setattr("trollsched.schedule.send_file", lambda url, file: transferred.append(file))
    station.single_station(scheduler, start, str(tmp_path / "sometles.txt"))
    assert transferred == []
    assert not (tmp_path / "one-request.xml").exists()
    assert (tmp_path / filename).stat().st_size > 0


def test_station_writes_html_viewer(station_setup, tmp_path, monkeypatch):
    """With --html, a self-contained page with the station's passes is written."""
    station, scheduler, start = station_setup
    scheduler.opts = parse_args(["-c", "unused", "--html"])
    scheduler.opts.output_dir = str(tmp_path)
    scheduler.opts.comb = False
    scheduler.patterns["file_html"] = str(tmp_path / "{station}.html")
    monkeypatch.setattr("trollsched.viewer.geo.load_coastlines", lambda path=None, step=1: [])
    station.single_station(scheduler, start, str(tmp_path / "sometles.txt"))
    page = (tmp_path / "one.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in page
    assert page.count('"ant":"one"') == 2
    assert '"orbit":' in page


def test_station_viewer_shows_passes_planned_by_earlier_runs(station_setup, tmp_path, monkeypatch):
    """Request files from earlier runs in the output directory fill the past of the page."""
    station, scheduler, start = station_setup
    scheduler.opts = parse_args(["-c", "unused", "--html"])
    scheduler.opts.output_dir = str(tmp_path)
    scheduler.opts.comb = False
    scheduler.patterns["file_html"] = str(tmp_path / "{station}.html")
    fmt = "%Y-%m-%d-%H:%M:%S"
    earlier = start - timedelta(hours=2)
    (tmp_path / "one-request.xml").write_text(
        f"<acquisition-schedule><properties><type>request</type><antenna>one</antenna>"
        f"<file-start>{start - timedelta(hours=3):{fmt}}</file-start>"
        f"<file-end>{start + timedelta(hours=1):{fmt}}</file-end></properties>"
        f'<pass satellite="noaa 19" start-time="{earlier:{fmt}}" end-time="{earlier + timedelta(minutes=10):{fmt}}" />'
        f'<pass satellite="noaa 19" start-time="{start + timedelta(minutes=30):{fmt}}" '
        f'end-time="{start + timedelta(minutes=40):{fmt}}" />'
        "</acquisition-schedule>")
    monkeypatch.setattr("trollsched.viewer.geo.load_coastlines", lambda path=None, step=1: [])
    station.single_station(scheduler, start, str(tmp_path / "sometles.txt"))
    page = (tmp_path / "one.html").read_text(encoding="utf-8")
    assert page.count('"ant":"one"') == 3
    assert f'"s":{earlier.replace(tzinfo=timezone.utc).timestamp()}' in page
    assert f'"s":{(start + timedelta(minutes=30)).replace(tzinfo=timezone.utc).timestamp()}' not in page
