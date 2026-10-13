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
	``trimmable: true`` overlap in time, but only in the parts of the passes
	outside the area of interest, the passes are shortened so that both can be
	received: the overlap is shared equally, without cutting anything covering
	the area of interest, and with the scheduling delay in between. When the
	passes overlap over the area of interest, nothing is trimmed and the
	scheduler picks one of them as usual.
