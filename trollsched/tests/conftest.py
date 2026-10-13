#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Adam.Dybbroe

# Author(s):

#   Adam.Dybbroe <a000680@c22526.ad.smhi.se>

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

"""Fixtures for unit testing."""


from datetime import datetime, timedelta

import pytest

from trollsched.satpass import create_pass

# Create a fake TLE file for testing.
TEST_TLEFILE1 = """NOAA-20
1 43013U 17073A   24260.23673431  .00000000  00000+0  20543-3 0 00012
2 43013  98.7102 196.6451 0000981  27.6583 181.3633 14.19588904353826
"""

FAKE_XML_SCHEDULE = """<acquisition-schedule><properties><project>Pytroll</project><type>request</type><station>nrk</station><file-start>2024-12-02-21:54:34</file-start><file-end>2024-12-02-23:54:34</file-end><requested-by>SMHI</requested-by><requested-on>2024-12-02-19:55:05</requested-on></properties><pass satellite="noaa18" start-time="2024-12-02-22:01:31" end-time="2024-12-02-22:16:17" /><pass satellite="npp" start-time="2024-12-02-22:38:18" end-time="2024-12-02-22:49:39" /><pass satellite="noaa20" start-time="2024-12-02-23:01:26" end-time="2024-12-02-23:14:17" /></acquisition-schedule>"""  # noqa

TEST_TLEFILE2 = """NOAA-20
1 43013U 17073A   24336.73680280  .00000000  00000+0  21070-3 0 00017
2 43013  98.7240 271.9468 0002361  91.7021 243.0836 14.19579317364671
NOAA 18
1 28654U 05018A   24336.77887833  .00000603  00000+0  34401-3 0  9991
2 28654  98.8621  52.2610 0013351 310.3593  49.6413 14.13439071  6932
SUOMI NPP
1 37849U 11061A   24336.86623462  .00000353  00000+0  18825-3 0  9992
2 37849  98.7391 272.4265 0002092 106.9131 253.2275 14.19509233678657
SENTINEL-3B
1 43437U 18039A   26130.81048956  .00000056  00000+0  41080-4 0  9992
2 43437  98.6260 198.8755 0001495  81.8840 278.2510 14.26738034418797
"""

@pytest.fixture
def fake_tle_file(tmp_path):
    """Write fake TLE file."""
    file_path = tmp_path / "sometles.txt"
    with open(file_path, "w") as fpt:
        fpt.write(TEST_TLEFILE1)

    return file_path

@pytest.fixture
def fake_long_tle_file(tmp_path):
    """Write fake TLE file."""
    file_path = tmp_path / "some_more_tles.txt"
    with open(file_path, "w") as fpt:
        fpt.write(TEST_TLEFILE2)

    return file_path

@pytest.fixture
def fake_noaa20_viirs_pass_instance(fake_tle_file):
    """Create a fake trollsched.,satpass instance for NOAA-20 VIIRS."""
    starttime = datetime(2024, 9, 17, 1, 25, 52)
    endtime = starttime + timedelta(minutes=15)
    return create_pass("NOAA-20", "viirs", starttime, endtime, str(fake_tle_file))

@pytest.fixture
def fake_xml_schedule_file(tmp_path):
    """Create a fake XML schedule file."""
    file_path = tmp_path / "20241202-195434-aquisition-schedule-request-nrk.xml"
    with open(file_path, "w") as fpt:
        fpt.write(FAKE_XML_SCHEDULE)

    return file_path


NOVEMBER_2025_TLES = """NOAA-21
1 54234U 22150A   25324.73837060  .00000000  00000+0  74562-4 0 00019
2 54234  98.7436 261.3254 0002715  82.9084 208.0969 14.19515328156977
FENGYUN 3F
1 57490U 23111A   25325.02782213  .00000090  00000+0  62835-4 0  9991
2 57490  98.7110  33.6690 0000896  74.2365 285.8911 14.19885292119329
METOP-SGA1
1 65159U 25172A   25324.45800682  .00000090  00000+0  61125-4 0  9999
2 65159  98.6957  22.6525 0001569  98.6969 261.4387 14.21581732 14136
AWS
1 60543U 24149CD  25324.47370566  .00001306  00000+0  14164-3 0  9990
2 60543  97.7048  35.6425 0003571  86.6949 273.4677 14.89823109 68227
"""


@pytest.fixture
def november_2025_tle_file(tmp_path):
    """Write real TLEs of NOAA-21, FY-3F, Metop-SGA1 and AWS from November 2025."""
    file_path = tmp_path / "november_2025.tle"
    file_path.write_text(NOVEMBER_2025_TLES)
    return file_path
