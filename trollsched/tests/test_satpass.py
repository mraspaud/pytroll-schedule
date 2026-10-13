#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2018 - 2024 Pytroll-schedule developers

# Author(s):

#   Adam.Dybbroe <adam.dybbroe@smhi.se>

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

"""Test the satellite pass and swath boundary classes."""

import hashlib
from datetime import datetime, timedelta

import numpy as np
import numpy.testing
import pytest
from pyorbital import geoloc, geoloc_instrument_definitions
from pyorbital.orbital import Orbital
from pyproj import Geod
from pyresample.geometry import AreaDefinition, create_area_def

from trollsched.boundary import InstrumentNotSupported, SwathBoundary
from trollsched.pass_scheduling_utils import Satellite
from trollsched.satpass import Pass, create_pass, get_next_passes

LONS1 = np.array([-122.29913729167814, -131.60058159571031, -155.961213760717,
                  143.3119727554512, 106.02965751347901, 93.36126835337495,
                  87.57849934781100, 84.29933364982566, 82.17950518319881,
                  80.68634385028724, 79.5690023835495, 78.69429485234980,
                  77.98502527974398, 77.39335155313441, 76.88800944806979,
                  76.44766342982001, 76.05721197259496, 75.70562085509124,
                  75.38459322897950, 75.08772010946592, 74.80991756643488,
                  74.54704020814617, 74.2956050853799, 74.05258461379435,
                  73.81524047742334, 73.58097695422956, 73.34719315875176,
                  73.11110832191844, 72.86951723408401, 72.6183881106984,
                  72.35208871319023, 72.06160625287379, 71.73109972748307,
                  58.24031892386924, 45.73164828451026, 34.983915286105841,
                  26.151791051098741, 19.01610700732932, 13.24681717703461,
                  8.535589849918395, -0.21478446026206655, -3.0137865812797742,
                  -5.068807376039615, -6.69014582833812, -8.031436531403884,
                  -9.17837787499672, -10.184053804068078, -11.08380616913978,
                  -11.902473400474307, -12.658288639570543, -13.365144298402306,
                  -14.033989519896842, -14.67373789768568, -15.291885411967804,
                  -15.894951357221601, -16.488809664426334, -17.07895346773434,
                  -17.670722332266877, -18.269514586624268, -18.881004493673814,
                  -19.511384728912944, -20.16765900161457, -20.858018907067198,
                  -21.592356127841647, -22.382991844580388, -23.245761959078699,
                  -24.201706093513693, -25.279831938055729, -26.521919725640878,
                  -27.991530824989383, -29.79270285696341, -32.11482495236408,
                  -35.36860848220794, -35.38196057929291, -35.96564490839391,
                  -37.14469461063711, -39.34032288993581, -43.49756191636224,
                  -52.140150361650242, -73.32968630167586], dtype="float64")

LATS1 = np.array([84.60636068853245, 86.98442395687161, 88.49456022447191,
                  88.89300011481139, 88.22779358510331, 87.40967936120957,
                  86.64325736161464, 85.94367983437350, 85.30255538867894,
                  84.70925173626937, 84.15425746586273, 83.62954333855285,
                  83.12834915433722, 82.64489266233674, 82.17410590471128,
                  81.71141289480769, 81.25254071570363, 80.79335178371028,
                  80.32968464330769, 79.85719038404096, 79.37115024401010,
                  78.86625629735791, 78.3363300710257, 77.77394121494508,
                  77.16986547297988, 76.51227895938166, 75.78550418056957,
                  74.96795603702333, 74.02856603911809, 72.92005968599192,
                  71.56494977194963, 69.82171851406746, 67.39639027951881,
                  67.05122703857464, 65.58296168740803, 63.17405563876378,
                  60.04860484612954, 56.40356307767654, 52.38706142545730,
                  48.10316762634827, 36.43286117419195, 37.294232177845529,
                  37.87377973884829, 38.300186952537686, 38.63276825199758,
                  38.9028916756336, 39.1290618698738, 39.32304570813714,
                  39.49275251704084, 39.64373393518190, 39.78002660805384,
                  39.90465451335454, 40.019943028832706, 40.12772323591502,
                  40.22946939083045, 40.326394199305582, 40.41951660774958,
                  40.50971118789266, 40.59774484777404, 40.68430451703702,
                  40.7700180558396, 40.855469567155758, 40.94120927061024,
                  41.02775680219415, 41.11559471997666, 41.20514508137085,
                  41.29671386380577, 41.39036993687247, 41.485681640616086,
                  41.58111782402230, 41.67256883542420, 41.749170728076649,
                  41.77850756272868, 54.62516164055283, 59.69624967680064,
                  64.7365169036661, 69.72588502309061, 74.61859634258133,
                  79.2863413071232, 83.25136143286568], dtype="float64")

LONS2 = np.array([-174.41109502, 167.82626942, 148.22256543, 130.11394909,
                  115.7615786, 105.16848388, 97.41309453, 91.6172560,
                  87.15807492, 83.6252085, 80.75002341, 78.3536070,
                  76.31380877, 74.54500182, 72.98559664, 71.59019597,
                  70.32455088, 69.16223704, 68.08240912, 67.06824405,
                  66.10583161, 65.18335778, 64.29047833, 63.41780985,
                  62.55648167, 61.69769557, 60.83223100, 59.94980227,
                  59.03809754, 58.08113666, 57.05605009, 55.9256068,
                  54.62324926, 41.68940322, 41.45193022, 41.2459648,
                  41.05882951, 40.88350432, 40.71568203, 40.55233707,
                  40.3911088, 40.22998482, 40.06711243, 39.90066650,
                  39.72874144, 39.5492463, 39.35978842, 39.15752963,
                  38.93899594, 38.69981133, 38.43430995, 38.13494966,
                  37.79139086, 37.38898930, 36.90621096, 36.30994393,
                  35.54639579, 34.52183158, 33.05696589, 30.76100871,
                  26.59597760, 16.71267693, -23.63831133, -102.95424384,
                  -122.5905010, -129.09284487], dtype="float64")

LATS2 = np.array([83.23214787, 84.90705779, 85.61902922, 85.73275580, 85.50918317,
                  85.12456415, 84.67508083, 84.20663729, 83.73948028, 83.28164626,
                  82.83543371, 82.40043504, 81.9749612, 81.55671149, 81.14308032,
                  80.73128127, 80.31837559, 79.90124443, 79.47652254, 79.0404981,
                  78.58897484, 78.11708493, 77.61903219, 77.08773014, 76.5142769,
                  75.88716572, 75.19104884, 74.40470657, 73.49750543, 72.42273364,
                  71.10370827, 69.40022281, 67.02066125, 67.41117187, 69.8379414,
                  71.58248343, 72.93882219, 74.04850619, 74.98904312, 75.80772305,
                  76.53562759, 77.1943538, 77.79959100, 78.3631751, 78.89434340,
                  79.40054119, 79.88796420, 80.36194117, 80.8272166, 81.28817185,
                  81.74901082, 82.21392747, 82.68727202, 83.17372981, 83.67852909,
                  84.20769740, 84.76839054, 85.36931941, 86.02127623, 86.73759969,
                  87.5334324, 88.41473888, 89.22853704, 88.72242719, 87.09250572,
                  84.6670132], dtype="float64")

LONS3 = np.array([-8.66259458, -6.20985781, 15.99864336, 25.41280344, 33.80862236,
                  48.29034314, 49.55993268, 45.22113798, 43.95788628, 30.04270374,
                  22.33146323, 13.90625506, -5.59290787, -7.75625031], dtype="float64")

LATS3 = np.array([66.94713589, 67.07857959, 66.53182749, 65.27976581, 63.50416750,
                  58.34071842, 57.71422018, 55.15189581, 55.72733432, 60.41089170,
                  61.99702690, 63.11500276, 63.67176672, 63.56939063], dtype="float64")

AREA_DEF_EURON1 = AreaDefinition("euron1", "Northern Europe - 1km",
                                 "", {"proj": "stere", "ellps": "WGS84",
                                      "lat_0": 90.0, "lon_0": 0.0, "lat_ts": 60.0},
                                 3072, 3072, (-1000000.0, -4500000.0, 2072000.0, -1428000.0))


def get_n20_orbital():
    """Return the orbital instance for a given set of TLEs for NOAA-20.

    From 16 October 2018.
    """
    tle1 = "1 43013U 17073A   18288.00000000  .00000042  00000-0  20142-4 0  2763"
    tle2 = "2 43013 098.7338 224.5862 0000752 108.7915 035.0971 14.19549169046919"
    return Orbital("NOAA-20", line1=tle1, line2=tle2)


def get_n19_orbital():
    """Return the orbital instance for a given set of TLEs for NOAA-19.

    From 16 October 2018.
    """
    tle1 = "1 33591U 09005A   18288.64852564  .00000055  00000-0  55330-4 0  9992"
    tle2 = "2 33591  99.1559 269.1434 0013899 353.0306   7.0669 14.12312703499172"
    return Orbital("NOAA-19", line1=tle1, line2=tle2)


def get_mb_orbital():
    """Return orbital for a given set of TLEs for MetOp-B.

    From 2021-02-04
    """
    tle1 = "1 38771U 12049A   21034.58230818 -.00000012  00000-0  14602-4 0 9998"
    tle2 = "2 38771  98.6992  96.5537 0002329  71.3979  35.1836 14.21496632434867"
    return Orbital("Metop-B", line1=tle1, line2=tle2)


def get_s3a_orbital():
    """From 2022-06-06."""
    tle1 = "1 41335U 16011A   22157.82164820  .00000041  00000-0  34834-4 0  9994"
    tle2 = "2 41335  98.6228 225.2825 0001265  95.7364 264.3961 14.26738817328255"
    return Orbital("Sentinel-3A", line1=tle1, line2=tle2)


SGA1_TLE = ("1 65159U 25172A   25324.45800682  .00000090  00000+0  61125-4 0  9999",
            "2 65159  98.6957  22.6525 0001569  98.6969 261.4387 14.21581732 14136")


def get_sga1_metimage_pass(duration):
    """Return a Metop-SGA1 METimage pass over Scandinavia, from 2025-11-20."""
    tstart = datetime(2025, 11, 20, 19, 42, 40)
    return Pass("Metop-SGA1", tstart, tstart + duration, instrument="metimage", tle1=SGA1_TLE[0], tle2=SGA1_TLE[1])


GROUND_SPEED_METRES_PER_SECOND = 6800


def metres_from_last_side_point_to_bottom_corner(boundary):
    """Return the distance from the last point of the boundary's right side to its bottom right corner."""
    _, _, metres = Geod(ellps="WGS84").inv(boundary.right_lons[-1], boundary.right_lats[-1],
                                           boundary.bottom_lons[0], boundary.bottom_lats[0])
    return metres


class TestPass:
    """Tests for the Pass object."""

    def setup_method(self):
        """Set up."""
        self.n20orb = get_n20_orbital()
        self.n19orb = get_n19_orbital()

    def test_pass_instrument_interface(self):
        """Test the intrument interface."""
        tstart = datetime(2018, 10, 16, 2, 48, 29)
        tend = datetime(2018, 10, 16, 3, 2, 38)

        instruments = set(("viirs", "avhrr", "modis", "mersi", "mersi-2"))
        for instrument in instruments:
            overp = Pass("NOAA-20", tstart, tend, orb=self.n20orb, instrument=instrument)
            assert overp.instrument == instrument

        instruments = set(("viirs", "avhrr", "modis"))
        overp = Pass("NOAA-20", tstart, tend, orb=self.n20orb, instrument=instruments)
        assert overp.instrument == "avhrr"

        instruments = set(("viirs", "modis"))
        overp = Pass("NOAA-20", tstart, tend, orb=self.n20orb, instrument=instruments)
        assert overp.instrument == "viirs"

        instruments = set(("amsu-a", "mhs"))
        with pytest.raises(TypeError):
            Pass("NOAA-20", tstart, tend, orb=self.n20orb, instrument=instruments)


class TestSwathBoundary:
    """Test the swath boundary object."""

    def setup_method(self):
        """Set up."""
        self.n20orb = get_n20_orbital()
        self.n19orb = get_n19_orbital()
        self.mborb = get_mb_orbital()
        self.s3aorb = get_s3a_orbital()
        self.euron1 = AREA_DEF_EURON1
        self.antarctica = create_area_def(
            "antarctic",
            {"ellps": "WGS84", "lat_0": "-90", "lat_ts": "-60",
             "lon_0": "0", "no_defs": "None", "proj": "stere",
             "type": "crs", "units": "m", "x_0": "0", "y_0": "0"},
            width=1000, height=1000,
            area_extent=(-4008875.4031, -4000855.294,
                         4000855.9937, 4008874.7048))
        self.arctica = create_area_def(
            "arctic",
            {"ellps": "WGS84", "lat_0": "90", "lat_ts": "60",
             "lon_0": "0", "no_defs": "None", "proj": "stere",
             "type": "crs", "units": "m", "x_0": "0", "y_0": "0"},
            width=1000, height=1000,
            area_extent=(-4008875.4031, -4000855.294,
                         4000855.9937, 4008874.7048))

    def test_swath_boundary(self):
        """Test generating a swath boundary."""
        tstart = datetime(2018, 10, 16, 2, 48, 29)
        tend = datetime(2018, 10, 16, 3, 2, 38)

        overp = Pass("NOAA-20", tstart, tend, orb=self.n20orb, instrument="viirs")
        overp_boundary = SwathBoundary(overp)

        cont = overp_boundary.contour()

        numpy.testing.assert_array_almost_equal(cont[0], LONS1)
        numpy.testing.assert_array_almost_equal(cont[1], LATS1)

        tstart = datetime(2018, 10, 16, 4, 29, 4)
        tend = datetime(2018, 10, 16, 4, 30, 29, 400000)

        overp = Pass("NOAA-20", tstart, tend, orb=self.n20orb, instrument="viirs")
        overp_boundary = SwathBoundary(overp, frequency=200)

        cont = overp_boundary.contour()

        numpy.testing.assert_allclose(cont[0], LONS2, rtol=0, atol=2e-6)
        numpy.testing.assert_array_almost_equal(cont[1], LATS2)

        # NOAA-19 AVHRR:
        tstart = datetime.strptime("20181016 04:00:00", "%Y%m%d %H:%M:%S")
        tend = datetime.strptime("20181016 04:01:00", "%Y%m%d %H:%M:%S")

        overp = Pass("NOAA-19", tstart, tend, orb=self.n19orb, instrument="avhrr")
        overp_boundary = SwathBoundary(overp, frequency=500)

        cont = overp_boundary.contour()

        numpy.testing.assert_array_almost_equal(cont[0], LONS3)
        numpy.testing.assert_array_almost_equal(cont[1], LATS3)

        overp = Pass("NOAA-19", tstart, tend, orb=self.n19orb, instrument="avhrr/3")
        overp_boundary = SwathBoundary(overp, frequency=500)

        cont = overp_boundary.contour()

        numpy.testing.assert_array_almost_equal(cont[0], LONS3)
        numpy.testing.assert_array_almost_equal(cont[1], LATS3)

        overp = Pass("NOAA-19", tstart, tend, orb=self.n19orb, instrument="avhrr-3")
        overp_boundary = SwathBoundary(overp, frequency=500)

        cont = overp_boundary.contour()

        numpy.testing.assert_array_almost_equal(cont[0], LONS3)
        numpy.testing.assert_array_almost_equal(cont[1], LATS3)

    def test_swath_coverage_does_not_cover_data_outside_area(self):
        """Test that swath covergate is 0 when the data is outside the area of interest."""
        # NOAA-19 AVHRR:
        tstart = datetime.strptime("20181016 03:54:13", "%Y%m%d %H:%M:%S")
        tend = datetime.strptime("20181016 03:55:13", "%Y%m%d %H:%M:%S")

        overp = Pass("NOAA-19", tstart, tend, orb=self.n19orb, instrument="avhrr")

        cov = overp.area_coverage(self.euron1)
        assert cov == 0

        overp = Pass("NOAA-19", tstart, tend, orb=self.n19orb, instrument="avhrr", frequency=80)

        cov = overp.area_coverage(self.euron1)
        assert cov == 0

    def test_swath_coverage_over_area(self):
        """Test that swath coverage matches when covering a part of the area of interest."""
        tstart = datetime.strptime("20181016 04:00:00", "%Y%m%d %H:%M:%S")
        tend = datetime.strptime("20181016 04:01:00", "%Y%m%d %H:%M:%S")

        overp = Pass("NOAA-19", tstart, tend, orb=self.n19orb, instrument="avhrr")

        cov = overp.area_coverage(self.euron1)
        assert cov == pytest.approx(0.103526, 1e-5)

        overp = Pass("NOAA-19", tstart, tend, orb=self.n19orb, instrument="avhrr", frequency=100)

        cov = overp.area_coverage(self.euron1)
        assert cov == pytest.approx(0.103526, 1e-5)

        overp = Pass("NOAA-19", tstart, tend, orb=self.n19orb, instrument="avhrr/3", frequency=133)

        cov = overp.area_coverage(self.euron1)
        assert cov == pytest.approx(0.103526, 1e-5)

        overp = Pass("NOAA-19", tstart, tend, orb=self.n19orb, instrument="avhrr", frequency=300)

        cov = overp.area_coverage(self.euron1)
        assert cov == pytest.approx(0.103526, 1e-5)

    def test_swath_coverage_metop(self):
        """Test ascat and avhrr coverages."""
        # ASCAT and AVHRR on Metop-B:
        tstart = datetime.strptime("2019-01-02T10:19:39", "%Y-%m-%dT%H:%M:%S")
        tend = tstart + timedelta(seconds=180)
        tle1 = "1 38771U 12049A   19002.35527803  .00000000  00000+0  21253-4 0 00017"
        tle2 = "2 38771  98.7284  63.8171 0002025  96.0390 346.4075 14.21477776326431"

        mypass = Pass("Metop-B", tstart, tend, instrument="ascat", tle1=tle1, tle2=tle2)
        cov = mypass.area_coverage(self.euron1)
        assert cov == pytest.approx(0.322815, 1e-5)

        mypass = Pass("Metop-B", tstart, tend, instrument="avhrr", tle1=tle1, tle2=tle2)
        cov = mypass.area_coverage(self.euron1)
        assert cov == pytest.approx(0.357325, 1e-5)

    def test_swath_coverage_slstr_not_supported(self):
        """Test Sentinel-3 SLSTR swath coverage - SLSTR is currently not supported!"""
        # Sentinel 3A slstr
        tstart = datetime(2022, 6, 6, 19, 58, 0)
        tend = tstart + timedelta(seconds=60)

        tle1 = "1 41335U 16011A   22156.83983125  .00000043  00000-0  35700-4 0  9996"
        tle2 = "2 41335  98.6228 224.3150 0001264  95.7697 264.3627 14.26738650328113"
        mypass = Pass("SENTINEL 3A", tstart, tend, instrument="slstr", tle1=tle1, tle2=tle2)

        with pytest.raises(InstrumentNotSupported) as exec_info:
            mypass.area_coverage(self.euron1)

        assert str(exec_info.value) == "SLSTR is a conical scanner, and currently not supported!"


    def test_swath_coverage_fy3(self):
        """Test FY3 coverages."""
        tstart = datetime.strptime("2019-01-05T01:01:45", "%Y-%m-%dT%H:%M:%S")
        tend = tstart + timedelta(seconds=60*15.5)

        tle1 = "1 43010U 17072A   18363.54078832 -.00000045  00000-0 -79715-6 0  9999"
        tle2 = "2 43010  98.6971 300.6571 0001567 143.5989 216.5282 14.19710974 58158"

        mypass = Pass("FENGYUN 3D", tstart, tend, instrument="mersi2", tle1=tle1, tle2=tle2, frequency=100)
        cov = mypass.area_coverage(self.euron1)
        assert cov == pytest.approx(0.786836, 1e-5)

        mypass = Pass("FENGYUN 3D", tstart, tend, instrument="mersi-2", tle1=tle1, tle2=tle2, frequency=100)
        cov = mypass.area_coverage(self.euron1)
        assert cov == pytest.approx(0.786836, 1e-5)

        tstart = datetime.strptime("2025-03-03T11:53:01", "%Y-%m-%dT%H:%M:%S")
        tend = tstart + timedelta(seconds=60*12.2)
        tle1 = "1 57490U 23111A   25061.77275788  .00000196  00000+0  11297-3 0  9996"
        tle2 = "2 57490  98.7372 134.1450 0001865  84.6719 275.4671 14.20001545 81964"
        mypass = Pass("FENGYUN 3F", tstart, tend, instrument="mersi-3", tle1=tle1, tle2=tle2, frequency=100)
        cov = mypass.area_coverage(self.euron1)
        assert cov == pytest.approx(0.70125, 1e-5)

    def test_arctic_is_not_antarctic(self):
        """Test that artic and antarctic are not mixed up."""
        tstart = datetime(2021, 2, 3, 16, 28, 3)
        tend = datetime(2021, 2, 3, 16, 31, 3)

        overp = Pass("Metop-B", tstart, tend, orb=self.mborb, instrument="avhrr")

        cov_south = overp.area_coverage(self.antarctica)
        cov_north = overp.area_coverage(self.arctica)

        assert cov_north == 0
        assert cov_south != 0

    def test_metimage_boundary_top_spans_the_whole_scan_line(self):
        """Test that the METimage boundary top runs from the first to the last pixel of a scan line."""
        mypass = get_sga1_metimage_pass(timedelta(seconds=60))

        edge_geometry = geoloc_instrument_definitions.metimage_edge_geom(1)
        edge_times = edge_geometry.times(mypass.risetime)
        edge_pixels = geoloc.compute_pixels(SGA1_TLE, edge_geometry, edge_times)
        edge_lons, edge_lats, _ = geoloc.get_lonlatalt(edge_pixels, edge_times)

        boundary = mypass.boundary
        np.testing.assert_allclose([boundary.top_lons[0], boundary.top_lons[-1]], edge_lons[:2])
        np.testing.assert_allclose([boundary.top_lats[0], boundary.top_lats[-1]], edge_lats[:2])

    def test_metimage_boundary_side_reaches_the_end_of_the_pass(self):
        """Test that the METimage boundary side follows the swath edge down to the last scan of the pass."""
        mypass = get_sga1_metimage_pass(timedelta(minutes=3))

        metimage_scan_seconds = geoloc_instrument_definitions.METIMAGE_SCAN.scan_rate
        assert (metres_from_last_side_point_to_bottom_corner(mypass.boundary) <
                2 * metimage_scan_seconds * GROUND_SPEED_METRES_PER_SECOND)

    def test_olci_boundary_side_reaches_the_end_of_the_pass(self, fake_long_tle_file):
        """Test that the OLCI boundary side follows the swath edge down to the end of the pass."""
        starttime = datetime(2026, 5, 11, 6, 15, 2)
        apass = create_pass("Sentinel-3B", "olci", starttime, starttime + timedelta(minutes=3), str(fake_long_tle_file))

        olci_side_step_seconds = 100 * 0.04399902224395014
        assert (metres_from_last_side_point_to_bottom_corner(apass.boundary) <
                2 * olci_side_step_seconds * GROUND_SPEED_METRES_PER_SECOND)

    def test_mwhs_2_boundary_is_the_mwhs2_boundary(self):
        """Test that spelling the instrument mwhs-2 gives the same boundary as mwhs2."""
        tstart = datetime(2019, 1, 5, 1, 1, 45)
        tend = tstart + timedelta(minutes=15)
        tle1 = "1 43010U 17072A   18363.54078832 -.00000045  00000-0 -79715-6 0  9999"
        tle2 = "2 43010  98.6971 300.6571 0001567 143.5989 216.5282 14.19710974 58158"

        contours = [Pass("FENGYUN 3D", tstart, tend, instrument=instrument, tle1=tle1, tle2=tle2).boundary.contour()
                    for instrument in ("mwhs-2", "mwhs2")]

        np.testing.assert_allclose(*contours)


class TestPassList:
    """Tests for the pass list."""

    def test_meos_pass_list(self):
        """Test generating a meos pass list."""
        orig = ("  1 20190105 FENGYUN 3D  5907 52.943  01:01:45 n/a   01:17:15 15:30  18.6 107.4 -- "
                "Undefined(Scheduling not done 1546650105 ) a3d0df0cd289244e2f39f613f229a5cc D")

        tstart = datetime.strptime("2019-01-05T01:01:45", "%Y-%m-%dT%H:%M:%S")
        tend = tstart + timedelta(seconds=60 * 15.5)

        tle1 = "1 43010U 17072A   18363.54078832 -.00000045  00000-0 -79715-6 0  9999"
        tle2 = "2 43010  98.6971 300.6571 0001567 143.5989 216.5282 14.19710974 58158"

        mypass = Pass("FENGYUN 3D", tstart, tend, instrument="mersi2", tle1=tle1, tle2=tle2)
        coords = (10.72, 59.942, 0.1)
        meos_format_str = mypass.print_meos(coords, line_no=1)
        assert meos_format_str == orig

        mypass = Pass("FENGYUN 3D", tstart, tend, instrument="mersi-2", tle1=tle1, tle2=tle2)
        coords = (10.72, 59.942, 0.1)
        meos_format_str = mypass.print_meos(coords, line_no=1)
        assert meos_format_str == orig

    def test_generate_metno_xml(self):
        """Test generating a metno xml."""
        import xml.etree.ElementTree as ET  # noqa because defusedxml has no Element, see defusedxml#48
        root = ET.Element("acquisition-schedule")

        orig = ('<acquisition-schedule><pass satellite="FENGYUN 3D" aos="20190105010145" los="20190105011715" '
                'orbit="5907" max-elevation="52.943" asimuth-at-max-elevation="107.385" asimuth-at-aos="18.555" '
                'pass-direction="D" satellite-lon-at-aos="76.204" satellite-lat-at-aos="80.739" '
                'tle-epoch="20181229125844.110848" /></acquisition-schedule>')

        tstart = datetime.strptime("2019-01-05T01:01:45", "%Y-%m-%dT%H:%M:%S")
        tend = tstart + timedelta(seconds=60 * 15.5)

        tle1 = "1 43010U 17072A   18363.54078832 -.00000045  00000-0 -79715-6 0  9999"
        tle2 = "2 43010  98.6971 300.6571 0001567 143.5989 216.5282 14.19710974 58158"

        mypass = Pass("FENGYUN 3D", tstart, tend, instrument="mersi2", tle1=tle1, tle2=tle2)

        coords = (10.72, 59.942, 0.1)
        mypass.generate_metno_xml(coords, root)

        # Dictionaries don't have guaranteed ordering in Python 3.7, so convert the strings to sets and compare them
        res = set(ET.tostring(root).decode("utf-8").split())
        assert res == set(orig.split())

    def tearDown(self):
        """Clean up."""
        pass


@pytest.mark.usefixtures("fake_tle_file")
def test_create_pass(fake_tle_file):
    """Test creating a pass given a start and an end-time, platform, instrument and TLE-filepath."""
    starttime = datetime(2024, 9, 17, 1, 25, 52)
    endtime = starttime + timedelta(minutes=15)
    apass = create_pass("NOAA-20", "viirs", starttime, endtime, str(fake_tle_file))

    assert isinstance(apass, Pass)
    assert apass.risetime == datetime(2024, 9, 17, 1, 25, 52)
    assert apass.falltime == datetime(2024, 9, 17, 1, 40, 52)
    contours = apass.boundary.contour()

    np.testing.assert_array_almost_equal(contours[0], np.array([
        -70.36110203, -67.46915579, -37.39227868, 15.41880497,
        45.92817594, 58.46516726, 64.80685871, 68.62697003,
        71.21054191, 73.10405925, 74.57665980, 75.77606177,
        76.79041835, 77.67608175, 78.47135109, 79.20387622,
        79.8949919, 80.56254046, 81.22305448, 81.89399601,
        82.59708788, 83.36554961, 84.26765770, 84.4380358 ,
        71.38871472, 59.86710822, 50.2648145 , 42.47616548,
        36.19170942, 31.08499466, 26.88204635, 23.37190116,
        17.5662740, 16.81235346, 13.3970594 , 11.09356678,
         9.34863875, 7.93459252,  6.73376559, 5.67666739,
         4.71816176, 3.82653013,  2.97777008, 2.15227582,
         1.33266018, 0.50209154, -0.3572437, -1.26588764,
        -2.24948770, -3.34251233, -4.59474432, -6.08390015,
        -7.94343858, -10.43565522, -14.20997737, -15.07433768,
       -14.49280142, -14.53229624, -14.87821968, -15.67970647,
        -17.21558546, -20.06333116, -25.60407459, -37.83432182], dtype="float64"))

    np.testing.assert_array_almost_equal(contours[1], np.array([
        84.33463272, 84.997171, 87.52048478, 87.92321762, 87.0894091 ,
        86.09655547, 85.17161338, 84.32873939, 83.55208977, 82.82353509,
        82.12679544, 81.4474257 , 80.77202024, 80.08726272, 79.37885879,
        78.63020789, 77.82052425, 76.92185536, 75.89384565, 74.67353765,
        73.15285615, 71.11924490, 68.04461095, 67.35541002, 66.32751035,
        64.27367333, 61.41247534, 57.95723011, 54.07641346, 49.89075232,
        45.48362495, 40.91233729, 30.85881467, 31.07880834, 32.00927129,
        32.57647447, 32.97429469, 33.2767975 , 33.51986008, 33.72341660,
        33.8996272 , 34.05645581, 34.19943649, 34.33262854, 34.45917240,
        34.58163601, 34.70224566, 34.82305067, 34.94604682, 35.073264  ,
        35.20679322, 35.34863920, 35.49998301, 35.65806179, 35.80023768,
        35.81635728, 46.51491320, 51.61438351, 56.69722997, 61.75596304,
        66.7771717 , 71.73310962, 76.55555829, 81.03181049], dtype="float64"))


def test_create_pass_olci(fake_long_tle_file):
    """Test creating a pass given a start and an end-time, platform, instrument and TLE-filepath."""
    starttime = datetime(2026, 5, 11, 6, 15, 2)
    endtime = starttime + timedelta(minutes=3)
    apass = create_pass("Sentinel-3B", "olci", starttime, endtime, str(fake_long_tle_file))

    assert isinstance(apass, Pass)

    # Reference footprint from the manifest XML (EPSG:4326 = lat, lon order).
    # Traversal: SW→SE (bottom W→E, 20 pts), SE→NE (east edge S→N, 4 pts),
    #            NE→NW (top E→W, 19 pts), NW→SW (west edge closing, 4 pts) = 47 total.
    lats_lons = ("20.9268 49.619 20.8209 50.2754 20.711 50.9318 20.6 51.5788 20.488 52.2326 20.3714 52.8832 20.2526 "
                 "53.5315 20.1306 54.1803 20.0067 54.8276 19.8803 55.4751 19.7528 56.12 19.6221 56.7649 19.4888 57.41 "
                 "19.3546 58.0515 19.217 58.6943 19.0778 59.3326 18.9354 59.9731 18.7911 60.6125 18.6451 61.2482 "
                 "18.4978 61.8846 21.138 62.579 23.7809 63.2999 26.4194 64.0508 29.0541 64.8351 29.2136 64.1438 "
                 "29.3696 63.4561 29.5219 62.7663 29.6707 62.0752 29.8156 61.3821 29.9574 60.6845 30.0942 59.9873 "
                 "30.2287 59.2858 30.3592 58.5841 30.4856 57.8771 30.6058 57.1887 30.7262 56.476 30.8425 55.7647 "
                 "30.9535 55.0573 31.0576 54.351 31.1624 53.6305 31.2619 52.9181 31.3557 52.2172 31.4508 51.4618 "
                 "28.8197 51.0137 26.1886 50.5571 23.555 50.0925 20.9268 49.619").split()
    lats = np.array(lats_lons[::2]).astype(np.float64)
    lons = np.array(lats_lons[1::2]).astype(np.float64)

    # Extract the 4 reference corners by their index in the polygon traversal.
    ref_sw_lat, ref_sw_lon = lats[0], lons[0]    # (20.9268, 49.619)
    ref_se_lat, ref_se_lon = lats[19], lons[19]  # (18.4978, 61.8846)
    ref_ne_lat, ref_ne_lon = lats[23], lons[23]  # (29.0541, 64.8351)
    ref_nw_lat, ref_nw_lon = lats[42], lons[42]  # (31.4508, 51.4618)

    # The boundary top/bottom edges are computed at the exact risetime/falltime,
    # so their endpoints give correct corners (within TLE vs precision-orbit accuracy).
    # top_lons[0]/top_lats[0]     = NW corner (wide west angle at risetime)
    # top_lons[-1]/top_lats[-1]   = NE corner (east angle at risetime)
    # bottom_lons[0]/bottom_lats[0]  = SE corner (east angle at falltime, reversed)
    # bottom_lons[-1]/bottom_lats[-1] = SW corner (west angle at falltime, reversed)
    b = apass.boundary
    np.testing.assert_almost_equal(b.top_lons[0], ref_nw_lon, decimal=0)
    np.testing.assert_almost_equal(b.top_lats[0], ref_nw_lat, decimal=0)
    np.testing.assert_almost_equal(b.top_lons[-1], ref_ne_lon, decimal=0)
    np.testing.assert_almost_equal(b.top_lats[-1], ref_ne_lat, decimal=0)
    np.testing.assert_almost_equal(b.bottom_lons[0], ref_se_lon, decimal=0)
    np.testing.assert_almost_equal(b.bottom_lats[0], ref_se_lat, decimal=0)
    np.testing.assert_almost_equal(b.bottom_lons[-1], ref_sw_lon, decimal=0)
    np.testing.assert_almost_equal(b.bottom_lats[-1], ref_sw_lat, decimal=0)


FENGYUN_3H_TLE = """FENGYUN 3H
1 65815U 25219A   26278.81334123  .00000027  00000+0  32934-4 0  9997
2 65815  98.6851 217.4624 0001566  86.9554 273.1802 14.19935530 53084
"""


def test_fengyun_3h_passes_are_mersi_3_passes(tmp_path):
    """Test that FY-3H passes are computed with the MERSI-3 instrument, as on FY-3F."""
    tle_file = tmp_path / "fy3h.tle"
    tle_file.write_text(FENGYUN_3H_TLE)

    passes = get_next_passes([Satellite("fengyun 3h", 0.8, 0.2)], datetime(2026, 10, 6), 12,
                             (16.148649, 58.581844, 0.052765), str(tle_file))

    assert {overpass.instrument for overpass in passes} == {"mersi-3"}


def test_meos_identifier_works_when_security_md5_is_disabled(fake_noaa20_viirs_pass_instance, monkeypatch):
    """MEOS output stays identical when MD5 is allowed only for non-security use."""
    overpass = fake_noaa20_viirs_pass_instance
    expected = overpass.print_meos((16, 58, 0), 1)
    original_md5 = hashlib.md5

    def non_security_md5(data, *, usedforsecurity=True):
        if usedforsecurity:
            raise ValueError("MD5 disabled for security use")
        return original_md5(data, usedforsecurity=False)

    monkeypatch.setattr(hashlib, "md5", non_security_md5)
    assert overpass.print_meos((16, 58, 0), 1) == expected
