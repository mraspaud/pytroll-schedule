Usage
=====

Script to create a local satellite pass schedule
------------------------------------------------

To run the schedule script, it is now compulsory to provide a configuration file
(see the config section on how these are formed). Command line arguments
override what is provided in the configuration file.

Usage of the schedule script::

	usage: schedule [-h] [-c CONFIG] [-t TLE] [-l LOG] [-m [MAIL [MAIL ...]]] [-v]
	                [--lat LAT] [--lon LON] [--alt ALT] [-f FORWARD]
	                [-s START_TIME] [-d DELAY] [-a AVOID] [--no-aqua-terra-dump]
	                [--multiproc] [-o OUTPUT_DIR] [-u OUTPUT_URL] [-x] [-r]
	                [--scisys] [-p] [-g]

	optional arguments:
	  -h, --help            show this help message and exit
	  -c CONFIG, --config CONFIG
	                        configuration file to use
	  -t TLE, --tle TLE     tle file to use
	  -l LOG, --log LOG     File to log to (defaults to stdout)
	  -m [MAIL [MAIL ...]], --mail [MAIL [MAIL ...]]
	                        mail address(es) to send error messages to.
	  -v, --verbose         print debug messages too

	start-parameter:
	  (or set values in the configuration file)

	  --lat LAT             Latitude, degrees north
	  --lon LON             Longitude, degrees east
	  --alt ALT             Altitude, km
	  -f FORWARD, --forward FORWARD
	                        time ahead to compute the schedule
	  -s START_TIME, --start-time START_TIME
	                        start time of the schedule to compute
	  -d DELAY, --delay DELAY
	                        delay (in seconds) needed between two consecutive
	                        passes (60 seconds by default)

	special:
	  (additional parameter changing behaviour)

	  -a AVOID, --avoid AVOID
	                        xml request file with passes to avoid
	  --no-aqua-terra-dump  do not consider Aqua/Terra-dumps
	  --multiproc           use multiple parallel processes

	output:
	  (file pattern are taken from configuration file)

	  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
	                        where to put generated files
	  -u OUTPUT_URL, --output-url OUTPUT_URL
	                        URL where to put generated schedule file(s), otherwise
	                        use output-dir
	  -x, --xml             generate an xml request file (schedule)
	  -r, --report          generate an xml report file (schedule)
	  --scisys              generate a SCISYS schedule file
	  -p, --plot            generate plot images
	  -g, --graph           save graph info
	  --html                generate an interactive HTML page of the schedule
	                        (see :doc:`viewer`)


When using ``--avoid``, satellite identifiers in the XML are matched against
both the declared satellite names and their configured ``schedule_name``
aliases. For sequential runs on different antennas, use the same
``schedule_name`` for each shared satellite in both configurations.
Alias matches require overlapping reception windows; other passes of the
same satellite are not penalised merely because their names match.
Avoidance retains its existing scoring penalty rather than strictly
excluding matching passes.


.. warning::

   Coordinated scheduling writes local pickle artifacts, and ``--multiproc``
   loads the per-station ``allpasses.<station>.pkl`` results. The output
   directory must be trusted and must not be writable by untrusted users.
   Do not supply or reuse pickle artifacts from untrusted sources: loading
   a malicious pickle can execute arbitrary code.

.. warning::

   Legacy ``ftp://`` output URLs are retained for compatibility. FTP uploads
   send credentials and schedule contents without encryption; deployments
   using them must explicitly accept that risk. For sensitive transfers,
   write the output locally and use a separate encrypted transfer mechanism.


Script to create instrument swath outlines in shapefile format for all passes scheduled
---------------------------------------------------------------------------------------

Usage of the script to create swath outlines in shapefile format::

  usage: create_shapefiles_from_schedule [-h] [-l LOG_CONFIG] -s [LIST_OF_SATELLITES ...] -t TLE_FILEPATH -x XML_FILEPATH [-o OUTPUT_DIR] [-v]

  options:
    -h, --help            show this help message and exit
    -l LOG_CONFIG, --log-config LOG_CONFIG
                          Log config file to use instead of the standard logging.
    -s [LIST_OF_SATELLITES ...], --satellites [LIST_OF_SATELLITES ...]
                          Complete file path to the TLE file to use.
    -t TLE_FILEPATH, --tle_filename TLE_FILEPATH
                          Complete file path to the TLE file to use.
    -x XML_FILEPATH, --xml_filename XML_FILEPATH
                          Complete path to the XML satellite schedule file.
    -o OUTPUT_DIR, --output_dir OUTPUT_DIR
                          Path to the directory where the shapefiles will be stored.
    -v, --verbose         Verbosity (between 1 and 2 occurrences with more leading to more verbose logging). WARN=0, INFO=1, DEBUG=2. This is overridden by the log
                          config file if specified.
