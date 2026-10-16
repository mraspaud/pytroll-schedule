"""Writers for different schedule formats."""
import os
from datetime import datetime


def generate_meos_file(output_file, allpasses, coords, start, report_mode=False):
    """Generate a meos file."""
    with open(output_file, "w") as out:
        out.write(" No. Date    Satellite  Orbit Max EL  AOS      Ovlp  LOS      Durtn  Az(AOS/MAX)\n")
        line_no = 1
        for overpass in sorted(allpasses, key=lambda x: x.risetime):
            if (overpass.rec or report_mode) and overpass.risetime > start:
                out.write(overpass.print_meos(coords, line_no) + "\n")
                line_no += 1
        out.close()
    return output_file


def generate_sch_file(output_file, overpasses, coords):
    """Generate a vcs/scisys/cgi schedule file."""
    with open(output_file, "w") as out:
        # create epochs
        out.write("#Orbital elements\n#\n#SCName           Epochtime\n#\n")
        satellites = set()

        for overpass in overpasses:
            epoch = "!{0:<16} {1}".format(overpass.satellite.name.upper(),
                                          overpass.orb.tle.epoch.strftime("%Y%m%d %H%M%S"))
            satellites |= set([epoch])
        sats = "\n".join(satellites) + "\n"
        out.write(sats)
        out.write("#\n#\n#Pass List\n#\n")

        out.write(
            "#SCName          RevNum Risetime        Falltime        Elev Dura ANL   Rec Dir Man Ovl OvlSCName        "
            "OvlRev OvlRisetime     OrigRisetime    OrigFalltime    OrigDuration\n#\n")

        for overpass in sorted(overpasses):
            out.write(overpass.print_vcs(coords) + "\n")


def generate_metno_xml_file(output_file, allpasses, coords, start, end, station_name, center_id, report_mode=False):
    """Generate a meto xml file."""
    from xml.etree import ElementTree as ET  # nosec B405 - XML generation only; no untrusted input is parsed.

    reqtime = datetime.utcnow()
    time_format = "%Y-%m-%dT%H:%M:%S"

    with open(output_file, "w") as out:
        out.write("<?xml version='1.0' encoding='utf-8'?>")

        root = ET.Element("acquisition-schedule")
        props = ET.SubElement(root, "properties")
        proj = ET.SubElement(props, "project")
        proj.text = "Pytroll"
        typep = ET.SubElement(props, "type")
        if report_mode:
            typep.text = "report"
        else:
            typep.text = "request"
        station = ET.SubElement(props, "station")
        station.text = station_name
        file_start = ET.SubElement(props, "file-start")
        file_start.text = start.strftime(time_format)
        file_end = ET.SubElement(props, "file-end")
        file_end.text = end.strftime(time_format)
        reqby = ET.SubElement(props, "requested-by")
        reqby.text = center_id
        reqon = ET.SubElement(props, "requested-on")
        reqon.text = reqtime.strftime(time_format)

        for overpass in sorted(allpasses, key=lambda x: x.risetime):
            if (overpass.rec or report_mode) and overpass.risetime > start:
                overpass.generate_metno_xml(coords, root)

        out.write(ET.tostring(root).decode("utf-8"))
        out.close()
    return output_file


def generate_xml_requests(sched, start, end, station_name, center_id, report_mode=False, antenna=None):
    """Create xml requests."""
    # defusedxml is not needed here as we only generate an xml file (ie no reading of potentially harmful data)
    from xml.etree import ElementTree as ET  # nosec B405 - XML generation only; no untrusted input is parsed.

    reqtime = datetime.utcnow()
    time_format = "%Y-%m-%d-%H:%M:%S"

    root = ET.Element("acquisition-schedule")
    props = ET.SubElement(root, "properties")
    proj = ET.SubElement(props, "project")
    proj.text = "Pytroll"
    typep = ET.SubElement(props, "type")
    if report_mode:
        typep.text = "report"
    else:
        typep.text = "request"
    antenna_element = ET.SubElement(props, "antenna")
    antenna_element.text = antenna
    station = ET.SubElement(props, "station")
    station.text = station_name
    file_start = ET.SubElement(props, "file-start")
    file_start.text = start.strftime(time_format)
    file_end = ET.SubElement(props, "file-end")
    file_end.text = end.strftime(time_format)
    reqby = ET.SubElement(props, "requested-by")
    reqby.text = center_id
    reqon = ET.SubElement(props, "requested-on")
    reqon.text = reqtime.strftime(time_format)

    for overpass in sorted(sched):
        if (overpass.rec or report_mode) and overpass.risetime > start:
            ovpass = ET.SubElement(root, "pass")
            sat_name = overpass.satellite.schedule_name or overpass.satellite.name
            ovpass.set("satellite", sat_name)
            ovpass.set("start-time", overpass.risetime.strftime(time_format))
            ovpass.set("end-time", overpass.falltime.strftime(time_format))
            if report_mode:
                if overpass.fig is not None:
                    ovpass.set("img", overpass.fig)
                ovpass.set("rec", str(overpass.rec))

    return root, reqtime


def generate_xml_file(sched, start, end, xml_file, station, center_id, report_mode=False, antenna=None):
    """Create an xml request file."""
    import defusedxml.ElementTree as ET
    tree, reqtime = generate_xml_requests(sched,
                                          start, end,
                                          station, center_id, report_mode, antenna)
    filename = xml_file
    tmp_filename = xml_file + reqtime.strftime("%Y-%m-%d-%H-%M-%S") + ".tmp"
    with open(tmp_filename, "w") as fp_:
        if report_mode:
            fp_.write("<?xml version='1.0' encoding='utf-8'?>"
                      "<?xml-stylesheet type='text/xsl' href='reqreader.xsl'?>")
        fp_.write(ET.tostring(tree).decode("utf-8"))
    os.rename(tmp_filename, filename)
    return filename
