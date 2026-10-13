"""Behavioral unit tests for satellite pass prediction."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from trollsched.satpass import get_next_passes


@pytest.mark.parametrize(("name", "instrument"), [
    ("snpp", "viirs"), ("Metop-B", "avhrr"), ("NOAA-19", "avhrr"),
    ("AQUA", "modis"), ("terra", "modis"), ("FY-3C", "mersi"),
    ("fengyun 3d", "mersi-2"), ("FY-3H", "mersi-3"), ("other", "unknown"),
])
def test_prediction_preserves_instrument_and_minimum_duration(name, instrument, tmp_path, monkeypatch):
    """Choose the platform instrument and exclude passes at or below the duration limit."""
    start = datetime(2025, 6, 21, 11)
    windows = [(start, start + timedelta(minutes=minutes), start) for minutes in (3, 4, 5)]
    orbit = SimpleNamespace(get_next_passes=lambda *args, **kwargs: windows)
    monkeypatch.setattr("trollsched.satpass.orbital.Orbital", lambda *args, **kwargs: orbit)
    tle = tmp_path / "tle"
    tle.touch()
    passes = get_next_passes([name], start, 1, (16, 58, 0), str(tle), min_pass=4)
    assert [(p.instrument, p.risetime, p.falltime) for p in passes] == [
        (instrument, start, start + timedelta(minutes=5)),
    ]
