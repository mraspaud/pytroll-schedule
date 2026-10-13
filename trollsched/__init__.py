#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2014 - 2025 PyTroll Community

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

"""Package file."""


# shortest allowed pass in minutes
MIN_PASS = 4

# DRL still use the name JPSS-1 (etc) instead of NOAA-20 in the TLEs:
JPSS_TLE_NAMES = {"NOAA-20": "JPSS-1",
                  "NOAA-21": "JPSS-2",
                  "NOAA-22": "JPSS-3"}

NUMBER_OF_FOVS = {
    "avhrr": 2048,
    "mhs": 90,
    "amsua": 30,
    "mwhs2": 98,
    "atms": 96,
    "ascat": 42,
    "viirs": 6400,
    "mwhs-2": 98,
    "metimage": 3144,
}

SATELLITE_NAMES = {"npp": "Suomi NPP",
                   "noaa19": "NOAA 19",
                   "noaa18": "NOAA 18",
                   "noaa15": "NOAA 15",
                   "aqua": "Aqua",
                   "terra": "Terra",
                   "metopc": "Metop-C",
                   "metopb": "Metop-B",
                   "metopa": "Metop-A",
                   "noaa20": "NOAA-20",
                   "noaa21": "NOAA-21",
                   "noaa22": "NOAA-22",
                   "fengyun3d": "FY-3D",
                   "fengyun3c": "FY-3C",
                   "fengyun3e": "FY-3E",
                   "fengyun3f": "FY-3F"
                   }

INSTRUMENT = {"Suomi NPP": "viirs",
              "NOAA-20": "viirs",
              "NOAA-21": "viirs",
              "NOAA-22": "viirs",
              "Aqua": "modis",
              "Terra": "modis",
              "NOAA 19": "avhrr",
              "NOAA 18": "avhrr",
              "NOAA 15": "avhrr",
              "Metop-A": "avhrr",
              "Metop-B": "avhrr",
              "Metop-C": "avhrr",
              "FY-3D": "avhrr",
              "FY-3C": "avhrr"}

VIIRS_PLATFORM_NAMES = ["SUOMI NPP", "SNPP",
                        "NOAA-20", "NOAA 20", "NOAA-21", "NOAA 21"]

MERSI_PLATFORM_NAMES = ["FENGYUN 3C", "FENGYUN-3C", "FY-3C"]
MERSI2_PLATFORM_NAMES = ["FENGYUN 3D", "FENGYUN-3D", "FY-3D",
                         "FENGYUN 3E", "FENGYUN-3E", "FY-3E"]
MERSI3_PLATFORM_NAMES = ["FENGYUN 3F", "FENGYUN-3F", "FY-3F",
                         "FENGYUN 3H", "FENGYUN-3H", "FY-3H"]

SATELLITE_MEOS_TRANSLATION = {"NOAA 19": "NOAA_19",
                              "NOAA 18": "NOAA_18",
                              "NOAA 15": "NOAA_15",
                              "METOP-A": "M02",
                              "METOP-B": "M01",
                              "FENGYUN 3A": "FENGYUN-3A",
                              "FENGYUN 3B": "FENGYUN-3B",
                              "FENGYUN 3C": "FENGYUN-3C",
                              "SUOMI NPP": "NPP"}
