"""Behavioral tests for published dump reports."""
import ftplib
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from trollsched.pass_scheduling_utils import Satellite
from trollsched.satpass import get_aqua_terra_dumpdata_from_ftp, get_terra_aqua_passes

REPORT_NAME = "wotis.test.2018332.120000.rpt"
REPORT_ROW = "SG1 2018:332:12:00:00 25.0 2018:332:12:10:00"


@pytest.fixture
def ftp_reports(tmp_path, monkeypatch):
    """Provide an FTP-boundary stub and an isolated report cache."""
    reports = {REPORT_NAME: ["header"] * 7 + [REPORT_ROW, REPORT_ROW, "", ""]}
    ftp = SimpleNamespace(
        login=lambda *args: None, prot_p=lambda: None, quit=lambda: None,
        dir=lambda path, append: [append(name) for name in reports],
        retrlines=lambda command, append: [append(line) for line in reports[command.split("/")[-1]]],
    )
    monkeypatch.setattr("trollsched.satpass.ftplib.FTP_TLS", lambda host: ftp)
    monkeypatch.setattr("trollsched.satpass.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr("trollsched.satpass.SwathBoundary", lambda *args, **kwargs: SimpleNamespace())
    return ftp, reports


def test_published_report_records_are_parsed_and_cached(ftp_reports, tmp_path):
    """Return one record per band pair, keeping timestamps and elevation text."""
    records = get_aqua_terra_dumpdata_from_ftp(Satellite("aqua", 0, 0), None)
    assert records == [{"station": "SG1", "aos": datetime(2018, 11, 28, 12),
                        "los": datetime(2018, 11, 28, 12, 10), "elev": "25.0"}]
    assert (tmp_path / REPORT_NAME).read_text().splitlines() == ftp_reports[1][REPORT_NAME]


def test_cached_report_is_used_instead_of_server_contents(ftp_reports, tmp_path):
    """A downloaded report remains authoritative on subsequent calls."""
    satellite = Satellite("aqua", 0, 0)
    expected = get_aqua_terra_dumpdata_from_ftp(satellite, None)
    ftp_reports[1][REPORT_NAME] = ["header"] * 7
    assert get_aqua_terra_dumpdata_from_ftp(satellite, None) == expected


@pytest.mark.parametrize("rows", [[], ["", REPORT_ROW], [REPORT_ROW, REPORT_ROW, "", "", REPORT_ROW]])
def test_report_headers_and_blank_terminators_limit_records(rows, ftp_reports):
    """Empty reports return no records and parsing stops at the first blank record."""
    ftp_reports[1][REPORT_NAME] = ["header"] * 7 + rows
    records = get_aqua_terra_dumpdata_from_ftp(Satellite("terra", 0, 0), "ftp://example/%s/")
    assert len(records) == (1 if rows and rows[0] else 0)


@pytest.mark.parametrize("stage", ["connect", "login", "listing", "download"])
def test_ftp_failures_preserve_logged_fallback_or_skip(stage, ftp_reports, monkeypatch, caplog):
    """Expected FTP failures are logged and yield no downloaded records."""
    ftp, _ = ftp_reports

    def fail(*args):
        raise ftplib.error_perm("denied") if stage in ("login", "download") else OSError("unreachable")

    if stage == "connect":
        monkeypatch.setattr("trollsched.satpass.ftplib.FTP_TLS", fail)
    else:
        monkeypatch.setattr(ftp, {"login": "login", "listing": "dir", "download": "retrlines"}[stage], fail)
    with caplog.at_level("INFO"):
        assert get_aqua_terra_dumpdata_from_ftp(Satellite("aqua", 0, 0), None) == []
    assert {"connect": "unreachable", "login": "cannot login anonymously",
            "listing": "Can't get any data", "download": "Permission error"}[stage] in caplog.text


def test_malformed_report_is_not_silently_ignored(ftp_reports):
    """Malformed published records propagate their parse error."""
    ftp_reports[1][REPORT_NAME] = ["header"] * 7 + ["invalid"]
    with pytest.raises(ValueError, match="not enough values to unpack"):
        get_aqua_terra_dumpdata_from_ftp(Satellite("aqua", 0, 0), None)


def pass_window(start, rise, fall):
    """Make a fixed orbital prediction in minutes from start."""
    return (start + timedelta(minutes=rise), start + timedelta(minutes=fall),
            start + timedelta(minutes=(rise + fall) / 2))


@pytest.mark.parametrize(("sv_elevation", "pf_elevation", "expected_rise"), [
    (30, 21, 11), (21, 20, 9), (20, 20, 11),
])
def test_inferred_dump_selection_preserves_threshold_and_ties(
        sv_elevation, pf_elevation, expected_rise, ftp_reports):
    """Poker Flat wins above twenty degrees or on ties; otherwise elevation wins."""
    start = datetime(2018, 11, 28, 12)
    ftp_reports[1][REPORT_NAME] = ["header"] * 7
    windows = {15.399: [pass_window(start, 3, 9)], -147.43: [pass_window(start, 5, 11)], -75.457222: []}
    orbit = SimpleNamespace(get_next_passes=lambda time, forward, lon, *args: windows[lon],
                            get_observer_look=lambda time, lon, *args: (0, sv_elevation if lon > 0 else pf_elevation),
                            get_orbit_number=lambda time: 1)
    passes = {}
    get_terra_aqua_passes(passes, start, 1, Satellite("aqua", 0, 0),
                         [pass_window(start, 0, 30)], orbit, True)
    assert [(p.risetime, p.falltime, p.instrument) for p in passes["aqua"]] == [
        (start + timedelta(minutes=expected_rise), start + timedelta(minutes=30), "modis"),
    ]


@pytest.mark.parametrize(("rise", "fall", "expected"), [(0, 10, (10, 30)), (20, 30, (0, 20)), (-5, 35, None)])
def test_published_dumps_trim_or_exclude_direct_broadcast_windows(rise, fall, expected, ftp_reports):
    """Early and late dumps trim the respective ends; a covering dump excludes reception."""
    start = datetime(2018, 11, 28, 12)
    window = pass_window(start, rise, fall)
    row = f"SG1 {window[0]:%Y:%j:%H:%M:%S} 25.0 {window[1]:%Y:%j:%H:%M:%S}"
    ftp_reports[1][REPORT_NAME] = ["header"] * 7 + [row, row]
    orbit = SimpleNamespace(get_next_passes=lambda *args: [])
    passes = {}
    get_terra_aqua_passes(passes, start, 1, Satellite("aqua", 0, 0),
                         [pass_window(start, 0, 30)], orbit, True)
    assert [(p.risetime, p.falltime) for p in passes["aqua"]] == (
        [] if expected is None else [pass_window(start, *expected)[:2]])


def test_reports_are_processed_chronologically_and_unrelated_files_are_ignored(ftp_reports):
    """Report filename dates determine the order of returned dump records."""
    _, reports = ftp_reports
    reports["wotis.test.2018333.120000.rpt"] = ["header"] * 7 + [REPORT_ROW.replace("332", "333")] * 2
    reports["unrelated.txt"] = ["invalid"]
    reports[REPORT_NAME] = reports.pop(REPORT_NAME)
    assert [record["aos"] for record in get_aqua_terra_dumpdata_from_ftp(Satellite("aqua", 0, 0), None)] == [
        datetime(2018, 11, 28, 12), datetime(2018, 11, 29, 12),
    ]


@pytest.mark.parametrize(("longitude", "expected_rise"), [(15.399, 9), (-147.43, 9), (-75.457222, 0)])
def test_unmatched_dump_stations_preserve_broadcast_policy(longitude, expected_rise, ftp_reports):
    """Unmatched Svalbard/Poker Flat passes restrict reception; Wallops alone does not."""
    start = datetime(2018, 11, 28, 12)
    ftp_reports[1][REPORT_NAME] = ["header"] * 7
    orbit = SimpleNamespace(
        get_next_passes=lambda time, forward, lon, *args: [pass_window(start, 3, 9)] if lon == longitude else [],
        get_orbit_number=lambda time: 1,
    )
    passes = {}
    get_terra_aqua_passes(passes, start, 1, Satellite("aqua", 0, 0),
                         [pass_window(start, 0, 30)], orbit, True)
    assert [(p.risetime, p.falltime) for p in passes["aqua"]] == [
        pass_window(start, expected_rise, 30)[:2],
    ]
