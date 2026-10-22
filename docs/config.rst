Configuration
=============

Two formats are recognized for the configuration files -- the plain
"group/key/value" format (parsed by module ConfigReader) and the now prefered
YAML-style.

.. note::
    .. deprecated::
        0.3.4
        The plain config format (.cfg) is deprecated, all config files should be
        changed to the YAML style.

Although here the YAML style is described, it also fits the plain config style.

The configuration file is divided in several section, each titled with a name
in square brackets. All sections are filled with key:value pairs.

Required sub-sections are those in sections ``default`` and ``pattern``, all
others are referenced by the station list in section ``default`` and the
satellites lists in the sub-sections per station.

Main section "default"
------------------------
::

	default:
	    center_id: DWD-OF
	    station:
	        - nrk
	        - ofb
	    forward: 12
	    start: 0.5
	    min_pass: 4
	    dump_url: "ftp://is.sci.gsfc.nasa.gov/ancillary/ephemeris/schedule/%s/downlink/"

``center_id``
    Name/ID for centre/org creating schedules.

``station``
    IDs of the stations to make a schedule for.

``forward``
	The timespan in hours the schedule should cover.

``start``
	Time offset between the time of computing and start of the schedule.

``min_pass``
	Minimum satellite pass duration (in minutes).

``dump_url``
	FTP URL, where to retrieve information about the data dump for AQUA and TERRA.

File- and directory pattern
---------------------------
Each of the keys in this section can be referenced from within other lines in
this section.

.. note::

   Be carefull not to create loops!

::

	pattern:
		dir_output: {output_dir}/{date}-{time}
		dir_plots: {dir_output}/plots.{station}
		file_xml: {dir_output}/aquisition-schedule-{mode}_{station}.xml
		file_sci: {dir_output}/scisys-schedule-{station}.txt
		file_graph: {dir_output}/graph.{station}

``time``, ``date``
	Time+date, when the computation started.

``station``
	Replaced with the station name. For co-operating stations "combined
	schedule" the string ".comb" is appended.

``mode``
	If a schedule file was created in `request` mode or in `report` mode.
	The first one is the format accepted by SciSYS software, while
	`report` mode is good for monitoring purposes.

``output_dir``
	This placeholder references the command-line argument ``-o OUTPUT_DIR``.

``dir_output``
	This key is used only within this section.

``dir_plots``
	Where the plots (globe grafic files) are saved.

``file_xml``
	Path and filename format for xml-schedule (request and report).

``file_sci``
	Path and filename for schedule file in SciSYS format.

``file_graph``
	Graph files with information about the computation.

``file_html``
	Path and filename of the interactive HTML schedule page written with
	``--html`` (default: ``{dir_output}/{date}-{time}-schedule-{station}.html``).
	See :doc:`viewer`.

``file_coastlines``
	Shapefile with coastlines or country outlines for the maps of the HTML
	page.  When unset, Natural Earth data is downloaded through cartopy, which
	needs internet access; see :doc:`viewer` for an offline setup.


Stations
--------
::

    stations:
        ofb:
            name:      "DWD Offenbach"
            longitude: 8.747073
            latitude:  50.103095
            altitude:  0.140
            area_file: /home/troll/etc/areas.def
            area:      euro4
            satellites:
                metop-a:
                    night: 0.1
                    day: 0.1
                metop-b:
                    night: 0.1
                    day: 0.1
                noaa 19:
                noaa 18:
                noaa 15:
                aqua:
                terra:
                suomi npp:

``name``
	Name of the station.

``longitude``
	Longitude in degrees east.

``latitude``
	Longitude in degrees north.

``altitude``
	Altitude above mean sea level, in km.

``area_file``, ``area``
	File with area definitions, and the area referenced therein.
	This area is taken into computation, only satellite passes which swaths
	are cross-sectioning this area are considered for scheduling.

``antenna``
	Optional. Name/ID of the antenna of this station, written to the
	``<antenna>`` element in the properties of the generated xml request and
	report files (also in the coordinated schedules). If omitted, the element
	is left empty.

``satellites``
	Satellites receivable from this station.
	The listed names may refer to the satellite sections.

	If the satellites are listed as a key/value dictionary, the day/night weight
	values (scores) can be set per satellite as in the section ``satellites``,
	described below. If no sub-keys are given, the scores from the section
	``satellites`` are used.

	Alternatively the satellites can be listed as a list, as shown in the
	following example for station "nrk". In this case all names refer to the
	section ``satellites``.

::

    stations:
        nrk:
            name: 	   Norrkoeping
            longitude: 16.148649
            latitude:  58.581844
            altitude:   0.052765
            area_file: /home/troll/etc/areas.def
            area:      euron1
            satellites:
                - metop-a
                - metop-b
                - noaa 19
                - noaa 18
                - noaa 15
                - aqua
                - terra
                - suomi npp

While the above example sub-section contained values for the station
Offenbach/Germany, this sub-section has values for Norkoepping/Sweden.

Satellites
----------
::

    satellites:
    	metop-a:
        	night:0.1
        	day:0.6
    	noaa 19:
        	night:0.05
        	day:0.3
    	terra:
        	night:0.2
        	day:0.8
    	suomi npp:
        	night:0.25
        	day:0.9

A few examples for satellite sections, assigning scores to each satellite.

``night``
	Weight value for satellite swath parts on the night-side of the terminator.

``day``
	Weight value for satellite swath parts on the day-side of the terminator.

``trimmable``
	Optional, ``false`` by default. When two passes of satellites both marked
	``trimmable: true`` overlap in time, they may be shortened so that both can
	be received. The overlap is shared equally where their coverage allowances
	permit, with the scheduling delay in between and the minimum pass duration
	preserved. By default, only reception outside the area of interest is
	removed. If the conflict cannot be resolved within these constraints,
	nothing is trimmed and the scheduler picks one pass as usual.
	Overlapping pairs are considered even when other candidate passes start
	between them; an intervening candidate does not prevent a feasible trim.

	After selection, unused trimmed time is restored where it does not
	conflict with another selected pass or the required scheduling delay.
	A pass therefore does not remain shortened solely to accommodate a
	trimming partner that was not selected. This applies to single-station
	and coordinated output, including reports and plots. It does not change
	which passes the scheduler selects.

``max_coverage_loss``
	Optional number from 0 to 100, expressed in percent, with a default of 0.
	When ``trimmable: true``, this sets the maximum fraction of each pass's
	original coverage of the area of interest that may be lost through
	trimming. For example, 5 retains at least 95 percent of the area that the
	untrimmed pass covered, not 95 percent of the entire area of interest or
	of the pass duration. The limit remains relative to the original pass
	even when both ends are trimmed in a chain of overlaps.

	A small numerical tolerance of 0.01 percent applies to the retained
	coverage threshold because of swath-boundary sampling. Setting the
	allowance does not enable trimming by itself; both satellites must still
	be marked ``trimmable: true``. A value of 100 allows all area coverage to
	be lost, but does not remove the minimum-duration or scheduling-delay
	constraints.

For example, allow each of these satellites to lose up to 5 percent of its
original coverage when resolving a conflict::

    satellites:
        metop-sga1:
            day: 0.7
            night: 0.5
            trimmable: true
            max_coverage_loss: 5
        fengyun 3f:
            day: 0.8
            night: 0.2
            trimmable: true
            max_coverage_loss: 5
