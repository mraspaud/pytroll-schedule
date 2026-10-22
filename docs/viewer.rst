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
* The past: the request files of earlier runs found in the output directory
  (the station's own, and those next to each avoid file for the other
  antennas) fill the page back as far as a run looks forward, with the plan
  as it was in force at each moment: runs overlap, so each file counts for
  the passes starting before the next file's start.

The page is one file with the data embedded, so it can be copied or served
from anywhere, and it works without network access.

What was received
-----------------

The page can also show what came out of each pass, from an index that the
processing side maintains next to it.  When ``products/index.js`` exists in
the page's directory, the page loads it and reloads it every two minutes
while open, so the products of a pass appear a few minutes after processing
without regenerating the page.  Nothing needs to be served: the index is a
script, which browsers load from a plain file as well, as long as it sits at
or below the page's directory (Firefox refuses ``..`` in the path).  Without
an index the page is unchanged.

The index registers the products with the page::

    viewer.add("products", [
      {"sat": "fy3h", "start": 1792660244, "end": 1792660942,
       "image": "thumbs/fy3h_20261022_091044.png",
       "link": "fy3h_20261022_091044_truecolor.png", "name": "true colour"},
      {"sat": "noaa20", "start": 1792663800, "end": 1792664400,
       "link": "noaa20_20261022_101000_truecolor.png", "name": "true colour"}
    ]);

Each product has the satellite name as used in the schedules (compared
ignoring case and punctuation, so ``NOAA-20`` matches ``noaa20``), the data
start and end as unix seconds, and any of: ``image``, a thumbnail in the
map's projection; ``link``, a product to open; ``name``, a label.  Paths are
relative to the index.  Products are matched to passes by satellite and time
overlap, so the data times may differ from the scheduled ones.

A pass with products shows the data times, with any late start or early end,
and links to the products; the first product with an image shows it on the
map, inside the planned swath outline.  A scheduled pass that ended without
any product is faded on the timeline and noted in the list.

Thumbnails are images in the page's map projection, with transparency
outside the swath.  :func:`trollsched.viewer.geo.thumbnail_area` gives the
pyresample area to resample onto, for the station and the map's viewpoint
height (geostationary by default)::

    from trollsched.viewer.geo import thumbnail_area
    area = thumbnail_area((16.15, 58.58, 0.05), size=800)
    scene.resample(area).save_dataset("overview", filename=..., fill_value=None)

The ``products`` argument of :func:`trollsched.viewer.build_page` moves the
index elsewhere (``{"url": "received/", "poll": 60}``) or disables the
lookup (``None``).  For a dashboard that people open by URL, give
``file_html`` a name without the run date and time, so that each run
overwrites the page, and keep the products directory next to it.

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
