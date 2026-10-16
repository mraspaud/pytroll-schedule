"""Tests for schedule viewer XML input."""
import sys
from importlib import import_module
from types import SimpleNamespace

import pytest
from defusedxml.common import EntitiesForbidden

schedule_viewer = import_module("scripts.schedule_viewer")


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

    assert schedule_viewer.load_coastlines("unused.shp", 2) == [[[0.12, 0.99], [2.12, 2.99], [4.12, 4.99]]]


def test_schedule_viewer_rejects_xml_entities(tmp_path):
    """Reject entity declarations rather than expanding schedule input."""
    schedule = tmp_path / "schedule.xml"
    schedule.write_text(
        '<!DOCTYPE acquisition-schedule [<!ENTITY antenna "expanded">]>'
        '<acquisition-schedule><properties><antenna>&antenna;</antenna>'
        '<file-start>2026-10-18-10:00:00</file-start>'
        '<file-end>2026-10-18-12:00:00</file-end></properties></acquisition-schedule>'
    )
    with pytest.raises(EntitiesForbidden):
        schedule_viewer.parse_schedule(schedule)
