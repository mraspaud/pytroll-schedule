#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2014 - 2025 Pytroll

# Author(s):

#   Martin Raspaud <martin.raspaud@smhi.se>
#   Adam Dybbroe <adam.dybbroe@smhi.se>

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

"""Test the schedule module."""
import datetime as dt
import os
import tempfile
from unittest.mock import patch

import pytest
import yaml

from trollsched.satpass import get_aqua_terra_dumps, get_metopa_passes, get_next_passes
from trollsched.schedule import (
    build_filename,
    conflicting_passes,
    coverage_weight,
    get_passes_from_xml_file,
    overlap_penalty_weight,
    run,
)


class TestTools:
    """Test the tools."""

    def test_conflicting_passes(self):
        """Test conflicting passes."""
        class MyPass(object):

            def __init__(self, rise, fall):
                self.risetime = rise
                self.falltime = fall

        ref_time = dt.datetime(2020, 1, 1, 18, 0)
        passes = [MyPass(ref_time, ref_time + dt.timedelta(minutes=10)),
                  MyPass(ref_time + dt.timedelta(minutes=10.01),
                         ref_time + dt.timedelta(minutes=20))]
        assert len(conflicting_passes(passes, dt.timedelta(seconds=0))) == 2
        assert len(conflicting_passes(passes, dt.timedelta(seconds=60))) == 1


class TestUtils:
    """Test class for utilities."""

    def test_fermi(self):
        """Test the fermi formula."""
        assert coverage_weight(0.25) == 0.875
        assert overlap_penalty_weight(0.25) == 0.5

    def test_build_filename(self):
        """Test building filename."""
        tempdir = tempfile.gettempdir()
        pattern_name = "dir_output"
        pattern_dict = {"file_xml": os.path.join("{dir_output}",
                                                 "{date}-{time}-aquisition-schedule-{mode}-{station}.xml"),
                        "file_sci": os.path.join("{dir_output}", "scisys-schedule-{station}.txt"),
                        "dir_plots": os.path.join("{dir_output}", "plots.{station}"), "dir_output": tempdir,
                        "file_graph": os.path.join("{dir_output}", "graph.{station}")}
        kwargs = {"date": "20190104", "output_dir": ".", "dir_output": tempdir, "time": "122023"}

        res = build_filename(pattern_name, pattern_dict, kwargs)
        assert res == tempdir

        pattern_name = "file_xml"
        kwargs = {"station": "nrk", "mode": "request", "time": "125334",
                  "date": "20190104", "dir_output": tempdir, "output_dir": "."}
        res = build_filename(pattern_name, pattern_dict, kwargs)
        assert res == os.path.join(tempdir, "20190104-125334-aquisition-schedule-request-nrk.xml")


class TestAll:
    """The test class."""

    def setup_method(self):
        """Set up."""
        from pyorbital import orbital

        from trollsched.pass_scheduling_utils import Satellite

        self.utctime = dt.datetime(2018, 11, 28, 10, 0)
        self.satellites = ["noaa-20", ]
        self.tles = {"noaa-20": {}}
        self.tles["noaa-20"]["line1"] = "1 43013U 17073A   18331.00000000  .00000048  00000-0  22749-4 0  3056"
        self.tles["noaa-20"]["line2"] = "2 43013 098.7413 267.0121 0001419 108.5818 058.1314 14.19552981053016"

        self.aquas = ["aqua", ]
        self.terras = ["terra", ]
        self.terra = Satellite("terra", 0, 0)
        self.metopa = Satellite("metop-a", 0, 0)

        self.tles["aqua"] = {}
        self.tles["aqua"]["line1"] = "1 27424U 02022A   18332.21220389  .00000093  00000-0  30754-4 0  9994"
        self.tles["aqua"]["line2"] = "2 27424  98.2121 270.9368 0001045 343.9225 155.8703 14.57111538881313"
        self.tles["terra"] = {}
        self.tles["terra"]["line1"] = "1 25994U 99068A   18338.20920286  .00000076  00000-0  26867-4 0  9999"
        self.tles["terra"]["line2"] = "2 25994  98.2142  50.5750 0000577 102.5211 257.6060 14.57132862  8586"
        self.tles["metop-a"] = {}
        self.tles["metop-a"]["line1"] = "1 29499U 06044A   18338.30873671  .00000000  00000+0  31223-4 0 00013"
        self.tles["metop-a"]["line2"] = "2 29499  98.6045  31.7725 0001942  91.8780 346.4884 14.21536046629175"

        self.orb = orbital.Orbital("NOAA 20",
                                   line1=self.tles["noaa-20"]["line1"],
                                   line2=self.tles["noaa-20"]["line2"])
        self.aqua_orb = orbital.Orbital("AQUA",
                                        line1=self.tles["aqua"]["line1"],
                                        line2=self.tles["aqua"]["line2"])
        self.terra_orb = orbital.Orbital("TERRA",
                                         line1=self.tles["terra"]["line1"],
                                         line2=self.tles["terra"]["line2"])
        self.metopa_orb = orbital.Orbital("Metop-A",
                                          line1=self.tles["metop-a"]["line1"],
                                          line2=self.tles["metop-a"]["line2"])

        # These values were used to generate the get_next_passes list mock:
        # utctime = dt.datetime(2018, 12, 4, 9, 0)
        # forward = 6
        # coords = (16, 58, 0)
        self.metopa_passlist = [(dt.datetime(2018, 12, 4, 9, 10, 4, 574801),
                                 dt.datetime(2018, 12, 4, 9, 25, 29, 157194),
                                 dt.datetime(2018, 12, 4, 9, 17, 48, 530484)),
                                (dt.datetime(2018, 12, 4, 10, 50, 23, 899232),
                                 dt.datetime(2018, 12, 4, 11, 4, 2, 335184),
                                 dt.datetime(2018, 12, 4, 10, 57, 13, 691637)),
                                (dt.datetime(2018, 12, 4, 12, 30, 24, 97160),
                                 dt.datetime(2018, 12, 4, 12, 40, 42, 403698),
                                 dt.datetime(2018, 12, 4, 12, 35, 33, 317647)),
                                (dt.datetime(2018, 12, 4, 14, 9, 1, 937869),
                                 dt.datetime(2018, 12, 4, 14, 17, 20, 556654),
                                 dt.datetime(2018, 12, 4, 14, 13, 11, 247497))]

        self.dumpdata = [
            {"los": dt.datetime(2018, 11, 28, 10, 0, 30), "station": "USAK05",
             "aos": dt.datetime(2018, 11, 28, 9, 50, 24), "elev": "11.188"},
            {"los": dt.datetime(2018, 11, 28, 11, 39, 47), "station": "AS2",
             "aos": dt.datetime(2018, 11, 28, 11, 28, 51), "elev": "39.235"},
            {"los": dt.datetime(2018, 11, 28, 13, 19, 8), "station": "USAK05",
             "aos": dt.datetime(2018, 11, 28, 13, 6, 36), "elev": "58.249"},
            {"los": dt.datetime(2018, 11, 28, 14, 54, 25), "station": "AS2",
             "aos": dt.datetime(2018, 11, 28, 14, 44, 37), "elev": "22.403"},
            {"los": dt.datetime(2018, 11, 28, 16, 27, 22), "station": "SG1",
             "aos": dt.datetime(2018, 11, 28, 16, 16, 58), "elev": "9.521"}
        ]
        self.dumpdata_terra = [{"los": dt.datetime(2018, 11, 20, 23, 24, 41), "station": "SG2",
                                "aos": dt.datetime(2018, 11, 20, 23, 12, 32), "elev": "17.4526"},
                               {"los": dt.datetime(2018, 11, 22, 23, 19, 21), "station": "AS3",
                                "aos": dt.datetime(2018, 11, 22, 23, 8, 55), "elev": "28.9558"},
                               {"los": dt.datetime(2018, 11, 22, 23, 19, 21), "station": "AS3",
                                "aos": dt.datetime(2018, 11, 22, 23, 8, 55), "elev": "28.9558"},
                               {"los": dt.datetime(2018, 11, 26, 22, 47, 34), "station": "SG1",
                                "aos": dt.datetime(2018, 11, 26, 22, 34, 58), "elev": "21.5694"},
                               {"los": dt.datetime(2018, 11, 26, 22, 47, 34), "station": "SG1",
                                "aos": dt.datetime(2018, 11, 26, 22, 34, 58), "elev": "21.5694"},
                               {"los": dt.datetime(2018, 11, 26, 22, 47, 34), "station": "SG1",
                                "aos": dt.datetime(2018, 11, 26, 22, 34, 58), "elev": "21.5694"},
                               {"los": dt.datetime(2018, 11, 27, 23, 30, 44), "station": "SG2",
                                "aos": dt.datetime(2018, 11, 27, 23, 18, 39), "elev": "16.8795"},
                               {"los": dt.datetime(2018, 11, 27, 23, 30, 44), "station": "SG2",
                                "aos": dt.datetime(2018, 11, 27, 23, 18, 39), "elev": "16.8795"},
                               {"los": dt.datetime(2018, 11, 28, 22, 43, 53), "station": "USAK05",
                                "aos": dt.datetime(2018, 11, 28, 22, 31, 57), "elev": "40.9264"},
                               {"los": dt.datetime(2018, 11, 28, 22, 43, 53), "station": "USAK05",
                                "aos": dt.datetime(2018, 11, 28, 22, 31, 57), "elev": "40.9264"},
                               {"los": dt.datetime(2018, 11, 29, 23, 25, 11), "station": "USAK05",
                                "aos": dt.datetime(2018, 11, 29, 23, 14, 47), "elev": "26.9937"},
                               {"los": dt.datetime(2018, 11, 29, 23, 25, 11), "station": "USAK05",
                                "aos": dt.datetime(2018, 11, 29, 23, 14, 47), "elev": "26.9937"},
                               {"los": dt.datetime(2018, 11, 30, 22, 31, 3), "station": "AS2",
                                "aos": dt.datetime(2018, 11, 30, 22, 19, 48), "elev": "47.8599"},
                               {"los": dt.datetime(2018, 12, 1, 1, 29, 2), "station": "WG1",
                                "aos": dt.datetime(2018, 12, 1, 1, 21, 11), "elev": "8.0543"},
                               {"los": dt.datetime(2018, 11, 30, 22, 31, 3), "station": "AS2",
                                "aos": dt.datetime(2018, 11, 30, 22, 19, 48), "elev": "47.8599"},
                               {"los": dt.datetime(2018, 12, 1, 1, 29, 2), "station": "WG1",
                                "aos": dt.datetime(2018, 12, 1, 1, 21, 11), "elev": "8.0543"},
                               {"los": dt.datetime(2018, 12, 3, 1, 28, 14), "station": "SG2",
                                "aos": dt.datetime(2018, 12, 3, 1, 17, 53), "elev": "9.2428"},
                               {"los": dt.datetime(2018, 12, 3, 22, 53, 35), "station": "SG1",
                                "aos": dt.datetime(2018, 12, 3, 22, 41, 5), "elev": "20.8371"},
                               {"los": dt.datetime(2018, 12, 3, 22, 53, 35), "station": "SG1",
                                "aos": dt.datetime(2018, 12, 3, 22, 41, 5), "elev": "20.8371"},
                               {"los": dt.datetime(2018, 12, 4, 23, 43, 5), "station": "AS2",
                                "aos": dt.datetime(2018, 12, 4, 23, 33, 8), "elev": "23.546"}]

    @patch("os.path.exists")
    def test_get_next_passes_viirs(self, exists):
        """Test getting the next viirs passes."""
        import numpy as np

        exists.return_code = True

        # mymock:
        with patch("pyorbital.orbital.Orbital") as mymock:
            instance = mymock.return_value
            instance.get_next_passes = self.orb.get_next_passes

            allpasses = get_next_passes(self.satellites, self.utctime,
                                        4, (16, 58, 0), tle_file="nonexisting")

            assert len(allpasses) == 2

            rt1 = dt.datetime(2018, 11, 28, 10, 53, 42, 79483).timestamp()
            ft1 = dt.datetime(2018, 11, 28, 11, 9, 6, 916787).timestamp()
            rt2 = dt.datetime(2018, 11, 28, 12, 34, 44, 667963).timestamp()
            ft2 = dt.datetime(2018, 11, 28, 12, 49, 25, 134067).timestamp()

            rise_times = np.array([p.risetime.timestamp() for p in allpasses])
            fall_times = np.array([p.falltime.timestamp() for p in allpasses])

            assert min(abs(rise_times - rt1)) < 0.02
            assert min(abs(rise_times - rt2)) < 0.02
            assert min(abs(fall_times - ft1)) < 0.02
            assert min(abs(fall_times - ft2)) < 0.02

            assert all([p.instrument == "viirs" for p in allpasses])

    @patch("os.path.exists")
    @patch("trollsched.satpass.get_aqua_terra_dumpdata_from_ftp")
    def test_get_next_passes_with_aquadumps(self, dumps_from_ftp, exists):
        """Test getting the passes with dumps."""
        dumps_from_ftp.return_value = self.dumpdata
        exists.return_code = True

        # mymock:
        with patch("pyorbital.orbital.Orbital") as mymock:
            instance = mymock.return_value
            instance.get_next_passes = self.aqua_orb.get_next_passes

            allpasses = get_next_passes(self.aquas, self.utctime,
                                        6, (16, 58, 0), tle_file="nonexisting",
                                        aqua_terra_dumps=True)

            assert len(allpasses) == 3

            rt1 = dt.datetime(2018, 11, 28, 11, 12, 8, 728455)
            ft1 = dt.datetime(2018, 11, 28, 11, 26, 8, 250021)
            rt2 = dt.datetime(2018, 11, 28, 12, 50, 46, 574975)
            ft2 = dt.datetime(2018, 11, 28, 13, 3, 53, 262440)
            rt3 = dt.datetime(2018, 11, 28, 14, 33, 33, 973194)
            ft3 = dt.datetime(2018, 11, 28, 14, 40, 10, 761405)

            for mypass in allpasses:
                dtmin = dt.timedelta(seconds=10000000)
                for risetime in [rt1, rt2, rt3]:
                    dt_ = abs(mypass.risetime - risetime)
                    if dt_ < dtmin:
                        dtmin = dt_

                assert dtmin.seconds == pytest.approx(0)

                dtmin = dt.timedelta(seconds=10000000)
                for falltime in [ft1, ft2, ft3]:
                    dt_ = abs(mypass.falltime - falltime)
                    if dt_ < dtmin:
                        dtmin = dt_

                assert dtmin.seconds == pytest.approx(0)

                assert mypass.instrument == "modis"

    @patch("trollsched.satpass.get_aqua_terra_dumpdata_from_ftp")
    def test_get_aqua_terra_dumps(self, dumps_from_ftp):
        """Test getting the EOS dumps."""
        dumps_from_ftp.return_value = self.dumpdata_terra

        # mymock:
        with patch("pyorbital.orbital.Orbital") as mymock:
            instance = mymock.return_value
            instance.get_next_passes = self.terra_orb.get_next_passes

            dumps = get_aqua_terra_dumps(dt.datetime(2018, 12, 3, 0, 0),
                                         dt.datetime(2018, 12, 10, 0, 0),
                                         self.terra_orb,
                                         self.terra)

            assert len(dumps) == 4
            assert dumps[0].station == "SG2"
            assert dumps[0].max_elev == "9.2428"
            assert dumps[0].pass_direction() == "ascending"
            assert (dumps[0].risetime - dt.datetime(2018, 12, 3, 1, 17, 53)).seconds == 0
            assert (dumps[0].falltime - dt.datetime(2018, 12, 3, 1, 28, 14)).seconds == 0

            assert dumps[3].station == "AS2"
            assert dumps[3].max_elev == "23.546"
            assert dumps[3].pass_direction() == "descending"
            assert (dumps[3].risetime - dt.datetime(2018, 12, 4, 23, 33, 8)).seconds == 0
            assert (dumps[3].falltime - dt.datetime(2018, 12, 4, 23, 43, 5)).seconds == 0

    @patch("os.path.exists")
    def test_get_metopa_passes(self, exists):
        """Test getting metopa passes."""
        exists.return_code = True

        with patch("pyorbital.orbital.Orbital") as mymock:
            instance = mymock.return_value
            instance.get_next_passes = self.metopa_orb.get_next_passes

            metopa_passes = get_metopa_passes(self.metopa, self.metopa_passlist, self.metopa_orb)

            assert len(metopa_passes) == 2
            assert metopa_passes[0].pass_direction() == "descending"
            assert metopa_passes[0].seconds() == pytest.approx(487.512589, 1e-5)
            assert (metopa_passes[0].uptime - dt.datetime(2018, 12, 4, 9, 17, 48, 530484)).seconds == 0
            assert (metopa_passes[0].risetime - dt.datetime(2018, 12, 4, 9, 17, 21, 644605)).seconds == 0

    def test_write_xml(self, tmp_path):
        """Test that writing pass list following EUMETSAT xml format works as expected."""
        import defusedxml.ElementTree as ET

        from trollsched.writers import generate_xml_file

        with open(tmp_path / "tle.file", "wt") as f:
            f.write(self.satellites[0].upper() + "\n")
            f.write(self.tles[self.satellites[0]]["line1"] + "\n")
            f.write(self.tles[self.satellites[0]]["line2"] + "\n")
            f.close()

            allpasses = get_next_passes(self.satellites, self.utctime,
                                        4, (16, 58, 0), tle_file=str(tmp_path / "tle.file"))

            filename = str(tmp_path / "test.xml")
            written_test_file = generate_xml_file(allpasses,
                                                  self.utctime,
                                                  self.utctime + dt.timedelta(hours=5),
                                                  filename,
                                                  "id", "center_id")

            # Read back to test content
            tree = ET.parse(written_test_file)
            root = tree.getroot()
            assert root.find("properties/project").text == "Pytroll"
            assert root.find("properties/type").text == "request"
            assert root.find("properties/station").text == "id"
            assert root.find("properties/antenna").text is None
            assert root.find("properties/requested-by").text == "center_id"
            assert root.find("properties/file-start").text == "2018-11-28-10:00:00"
            assert root.find("properties/file-end").text == "2018-11-28-15:00:00"
            expected_aos = ["20181128105342", "20181128123444"]
            expected_los = ["20181128110906", "20181128124925"]
            for overpass, exp_aos, exp_los in zip(root.iter("pass"), expected_aos, expected_los):
                assert overpass.attrib["aos"] == exp_aos
                assert overpass.attrib["los"] == exp_los

    def test_write_metno_xml(self, tmp_path):
        """Test that writing pass list in metno xml format work as expected."""
        import defusedxml.ElementTree as ET

        from trollsched.writers import generate_metno_xml_file

        with open(tmp_path / "tle.file", "wt") as f:
            f.write(self.satellites[0].upper() + "\n")
            f.write(self.tles[self.satellites[0]]["line1"] + "\n")
            f.write(self.tles[self.satellites[0]]["line2"] + "\n")
            f.close()

            allpasses = get_next_passes(self.satellites, self.utctime,
                                        4, (16, 58, 0), tle_file=str(tmp_path / "tle.file"))
            coords = (10, 60, 0.1)
            written_test_file = generate_metno_xml_file(tmp_path / "test.xml", allpasses,
                                                        coords, self.utctime,
                                                        self.utctime + dt.timedelta(hours=5), "id", "center_id",
                                                        report_mode=True)
            # Read back to test content
            tree = ET.parse(written_test_file)
            root = tree.getroot()
            assert root.find("properties/project").text == "Pytroll"
            assert root.find("properties/type").text == "report"
            assert root.find("properties/station").text == "id"
            assert root.find("properties/requested-by").text == "center_id"
            assert root.find("properties/file-start").text == "2018-11-28T10:00:00"
            assert root.find("properties/file-end").text == "2018-11-28T15:00:00"
            expected_aos = ["20181128105342", "20181128123444"]
            expected_los = ["20181128110906", "20181128124925"]
            for overpass, exp_aos, exp_los in zip(root.iter("pass"), expected_aos, expected_los):
                assert overpass.attrib["aos"] == exp_aos
                assert overpass.attrib["los"] == exp_los


euron1 = """euron1:
  description: Northern Europe - 1km
  projection:
    proj: stere
    ellps: WGS84
    lat_0: 90.0
    lon_0: 0.0
    lat_ts: 60.0
  shape:
    height: 3072
    width: 3072
  area_extent:
    lower_left_xy: [-1000000.0, -4500000.0]
    upper_right_xy: [2072000.0, -1428000.0]
"""


def run_schedule(tmp_path, tle, satellites, start_time, forward=12, coords=(16, 58, 0), extra_args=()):
    """Run the schedule command on *satellites* ({name: config}) and return the request xml file."""
    config_file = tmp_path / "config.yaml"
    tle_file = tmp_path / "test.tle"
    area_file = tmp_path / "areas.yaml"
    sched_file = tmp_path / "schedule.xml"

    area_file.write_text(euron1)
    tle_file.write_text(tle)

    longitude, latitude, altitude = coords
    config = dict(default=dict(station=["nrk"],
                               forward=forward,
                               start=0,
                               center_id="SMHI"),
                  stations=dict(nrk=dict(name="nrk",
                                         longitude=longitude,
                                         latitude=latitude,
                                         altitude=altitude,
                                         satellites=list(satellites),
                                         area="euron1",
                                         area_file=os.fspath(area_file))),
                  pattern=dict(dir_output=os.fspath(tmp_path),
                               file_xml=os.fspath(sched_file)),
                  satellites=satellites)
    config_file.write_text(yaml.dump(config))

    run(["-c", os.fspath(config_file), "-x", "-t", os.fspath(tle_file),
         "--start-time", start_time, *extra_args])
    return sched_file


def test_pyorbitals_platform_name(tmp_path):
    """Test that using pyorbital's platform name allows spurious names in the TLE data."""
    spurious_tle = ("NOAA 20 (JPSS-1)\n"
                    "1 43013U 17073A   24093.57357837  .00000145  00000+0  86604-4 0  9999\n"
                    "2 43013  98.7039  32.7741 0007542 324.8026  35.2652 14.21254587330172\n")
    satellites = {"noaa-20": dict(schedule_name="noaa20", international_designator="43013", night=0.4, day=0.9)}

    sched_file = run_schedule(tmp_path, spurious_tle, satellites, "2024-03-30T15:00")

    assert sched_file in tmp_path.iterdir()


avoid = """<?xml version="1.0"?>
<acquisition-schedule>
  <pass satellite="suomi npp" start-time="2024-05-08-03:57:01" end-time="2024-05-08-04:09:35"/>
</acquisition-schedule>
"""


def test_schedule_avoid(tmp_path):
    """Test that schedule can handle avoid list."""
    tle = ("SUOMI NPP\n"
           "1 37849U 11061A   24128.72979065  .00000000  00000+0  12832-3 0 00014\n"
           "2 37849  98.7205  67.3215 0001498  76.6175 303.3589 14.19560637649138\n"
           "NOAA 20\n"
           "1 37849U 11061A   24128.72979065  .00000000  00000+0  12832-3 0 00014\n"
           "2 37849  98.7205  67.3215 0001498  76.6175 303.3589 14.19560637649138\n")
    satellites = {"suomi npp": dict(schedule_name="suomi npp", international_designator="37849", night=0.4, day=0.9),
                  "noaa 20": dict(schedule_name="noaa 20", international_designator="99999", night=0.4, day=0.9)}
    avoid_file = tmp_path / "avoid.xml"
    avoid_file.write_text(avoid)

    sched_file = run_schedule(tmp_path, tle, satellites, "2024-05-08T00:00:00",
                              extra_args=["-v", "--avoid", os.fspath(avoid_file)])

    sched_file_passes = get_passes_from_xml_file([sched_file])
    for avoid_pass in get_passes_from_xml_file([avoid_file]):
        assert avoid_pass not in sched_file_passes


def test_schedule_golden_master(tmp_path, november_2025_tle_file):
    """Test that a real 6-hour schedule over euron1 stays the same."""
    satellites = {"NOAA-21": dict(schedule_name="noaa21", night=0.4, day=0.9),
                  "fengyun 3f": dict(schedule_name="fy3f", night=0.2, day=0.8),
                  "metop-sga1": dict(schedule_name="sga1", night=0.7, day=0.5),
                  "aws": dict(schedule_name="aws-pfm", night=0.8, day=0.8)}

    sched_file = run_schedule(tmp_path, november_2025_tle_file.read_text(), satellites, "2025-11-21T04:00:00",
                              forward=6, coords=(16.148649, 58.581844, 0.052765))

    scheduled = [str(overpass) for overpass in get_passes_from_xml_file([sched_file])]
    assert scheduled == ["noaa21 2025-11-21T04:35:20 2025-11-21T04:46:16",
                         "sga1 2025-11-21T06:04:20 2025-11-21T06:11:26",
                         "noaa21 2025-11-21T06:14:09 2025-11-21T06:23:09",
                         "aws-pfm 2025-11-21T07:12:21 2025-11-21T07:17:16",
                         "sga1 2025-11-21T07:43:02 2025-11-21T07:57:11",
                         "aws-pfm 2025-11-21T08:46:16 2025-11-21T08:58:04",
                         "fy3f 2025-11-21T09:33:49 2025-11-21T09:49:17"]


def test_schedule_receives_both_trimmable_passes_overlapping_outside_the_area(tmp_path, november_2025_tle_file):
    """Test that trimmable passes overlapping outside the area are both scheduled, after trimming."""
    satellites = {"fengyun 3f": dict(schedule_name="fy3f", night=0.2, day=0.8, trimmable=True),
                  "metop-sga1": dict(schedule_name="sga1", night=0.7, day=0.5, trimmable=True)}

    sched_file = run_schedule(tmp_path, november_2025_tle_file.read_text(), satellites, "2025-11-21T07:30:00",
                              forward=1, coords=(16.148649, 58.581844, 0.052765))

    assert [overpass.satellite.name for overpass in get_passes_from_xml_file([sched_file])] == ["sga1", "fy3f"]
