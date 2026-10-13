#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Pytroll developers

# Author(s):

#   Adam Dybbroe <Firstname.Lastname at smhi.se>

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

"""Common utilities for satellite pass and schedule calculations."""


class SatScore:
    """Container for the score parameter deciding which satellite pass to take."""

    def __init__(self, day, night):
        """Initialize the score."""
        self.day = day
        self.night = night


class Satellite:
    """The Satellite class holding information on its score, name and designator."""

    def __init__(self, name, day, night,
                 schedule_name=None, international_designator=None, trimmable=False, max_coverage_loss=0):
        """Initialize the satellite."""
        if (isinstance(max_coverage_loss, bool) or not isinstance(max_coverage_loss, (int, float)) or
                not 0 <= max_coverage_loss <= 100):
            raise ValueError("max_coverage_loss must be a number between 0 and 100 percent")
        self.name = name
        self.trimmable = trimmable
        self.max_coverage_loss = max_coverage_loss
        self.international_designator = international_designator
        self.score = SatScore(day, night)
        self.schedule_name = schedule_name or name
