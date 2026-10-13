Accounting for specific DR restrictions
=======================================

For some satellites and some instruments direct readout is not available
constantly. This is the case for instance for MODIS onboard the EOS Terra and
Aqua satellites.


Aqua and Terra dumps
--------------------

During the time when the EOS satellites make their global dump there is no
Direct Broadcast available for Direct Readout users. In order to disregard the
scheduling of local reception of data which will not be available due to these
restrictions, Pytroll-schedule takes the NASA Direct Readout Laboratory's
Terra and Aqua downlink scheduling reports into account when deriving the
local schedule.

Although DRL software development has moved to archive status, its current
ancillary data service continues to operate via FTP, as described on the
`DRL website <https://directreadout.sci.gsfc.nasa.gov/>`_.
Reports may contain only a header when no contacts are listed; an empty report
does not by itself establish that the service has been discontinued.

The FTP addresses are:
  - ftp://is.sci.gsfc.nasa.gov/ancillary/ephemeris/schedule/aqua/downlink/
  - ftp://is.sci.gsfc.nasa.gov/ancillary/ephemeris/schedule/terra/downlink/


.. Earth Observing System Polar Ground Network (EPGN)

   EPGN ground stations: Alaska Ground Station (AGS), Poker Flat, the Svalbard
   Satellite Station (SGS), the Kongsberg–Lockheed Martin ground station (SKS),
   and the SvalSat ground station (SG3) in Norway, as well as the SSC North
   Pole facility.

   SSC's North Pole Facility hosting the two antennas USAK04 & USAK05 (part of EPGN)


Metop
-----

Due to a broken A-side of the Metop-A HRPT downlink module only the B-side is
operable on the Metop-A spacecraft. The A-side failure was due to a
malfunctioning transistor that proved to be sensitive to cosmic radiation. The
same transistor is available on the B-side and therefore EUMETSAT has
implemented a restricted operation of the B-side HRPT downlink module. This
means no HRPT direct broadcast is available during parts of the Metop-A orbit
(e.g. over the North Pole and around the South Atlantic Anamoly).

For direct readout users EUMETSAT regularly (several times per day) publish an
HRPT on/off schedule in XML format at the following URL:

  - http://oiswww.eumetsat.org/uns/webapps/index.html?type=17


This will be read by Pytroll-schedule in order to disregard Metop-A where there will be
no Direct Readout available over the relavnt local reception station. NOT YET IMPLEMENTED!

.. FIXME!
