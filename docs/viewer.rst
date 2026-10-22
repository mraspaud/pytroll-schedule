Schedule viewer
===============

The scheduler can write an interactive, self-contained HTML page of the
schedule next to its other products::

    schedule -c config.yaml -t tle.txt -x --html -a other-antenna-request.xml

The page shows one row per satellite over the scheduled period, with the
passes coloured by antenna.  Hovering a pass shows its details and swath on a
near-sided perspective map centred on the station; clicking opens a page for
that pass alone.  A pass list under the timeline mirrors the visible window.

What the page shows
-------------------

* Scheduled passes, one colour per antenna.  A pass received by several
  antennas is striped.  The shade of the colour follows the fraction of the
  area of interest the pass covers: darker means more coverage.
* The avoid lists given with ``--avoid`` are read as the schedules of the other
  antennas, with the antenna name taken from the ``<antenna>`` property of each
  file (the file name is used for files without one).  Satellites that only
  appear in avoid lists, and passes the scheduler discarded itself but another
  antenna receives, get their visibility windows computed from the TLE file.
* Passes visible from the station that no antenna receives, in faint grey,
  with the scheduled passes they lost to.
* Trimmed passes: the part of the visibility window that will not be
  received is drawn as a dashed grey stub, and on the map as a dashed outline.
* Passes overlapping on one antenna are outlined in red.
* The direction of the pass (an arrow along the sub-satellite track), the
  night side of the Earth, the area of interest, and a day/night band on the
  time axis for the station.
* Optional antenna lanes (a checkbox in the header) showing the occupancy of
  each antenna.

The page is one file with the data embedded, so it can be copied or served
from anywhere, and it works without network access.

Output file and map background
------------------------------

The file name follows the ``file_html`` pattern of the configuration file,
``{dir_output}/{date}-{time}-schedule-{station}.html`` by default.

The map background is read from a shapefile.  By default the Natural Earth
1:110m "Admin 0 - Countries" data set is fetched through cartopy, which needs
internet access the first time.  On machines without it, download
``https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_countries.zip``
elsewhere, unzip it (keep the ``.shp``, ``.shx``, ``.dbf`` and ``.prj`` files
together) and point the configuration at it::

    pattern:
        file_coastlines: /shared/naturalearth/ne_110m_admin_0_countries.shp

Any shapefile of polygons or lines in longitude/latitude works; the 1:110m
coastline data set gives outlines without land fill.  Reading it needs
either ``pyshp`` or ``cartopy``.  Without a usable shapefile the page is still
written, with a blank globe.

Standalone use
--------------

``scripts/schedule_viewer.py`` builds the same page from existing request
files, one per antenna, without running the scheduler::

    schedule_viewer.py --tle tle.txt --coastlines ne_110m_admin_0_countries.shp \
        -o schedule.html request-meos.xml request-cgi.xml

With a TLE file, the station position is estimated from the passes (every
AOS and LOS is a moment where the satellite sits on the horizon), the
visibility windows are recomputed so that unscheduled and trimmed passes can
be shown, and orbit numbers and swaths are included.  Give ``--lat`` and
``--lon`` to skip the estimate.  Without a TLE file only the scheduled
passes are drawn, and the position must be given.  There is no area of
interest in this mode, so passes are not shaded by coverage.
