# Copyright (c) 2013 - 2024 Pytroll community

# Author(s):

#   Martin Raspaud <martin.raspaud@smhi.se>
#   Alexander Maul <alexander.maul@dwd.de>

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

"""Module and script for pass scheduling."""
import argparse
import logging
import logging.handlers
import os
import pickle  # nosec B403 - Internal artifacts only; the output directory must be trusted.
from datetime import datetime, timedelta
from pprint import pformat
from urllib.parse import urlparse

import numpy as np
from pyresample import parse_area_file

from trollsched import MIN_PASS, utils
from trollsched.combine import get_combined_sched
from trollsched.graph import Graph
from trollsched.satpass import SimplePass, get_next_passes
from trollsched.spherical import intersect, split_day_and_night
from trollsched.trimming import restore_unused_trim, trim_associated_overlaps
from trollsched.writers import generate_meos_file, generate_metno_xml_file, generate_sch_file, generate_xml_file

logger = logging.getLogger(__name__)


class Station:
    """docstring for Station."""

    def __init__(self, station_id, name, longitude, latitude, altitude, area, satellites, area_file=None,
                 min_pass=MIN_PASS, local_horizon=0, antenna=None):
        """Initialize the station."""
        self.id = station_id
        self.name = name
        self.longitude = longitude
        self.latitude = latitude
        self.altitude = altitude
        self.area = area
        self.satellites = satellites

        if area_file is not None:
            try:
                self.area = parse_area_file(area_file, area)[0]
            except TypeError:
                pass
        self.min_pass = min_pass
        self.local_horizon = local_horizon
        self.antenna = antenna
    @property
    def coords(self):
        """Get the coordinates lon, lat, alt."""
        return self.longitude, self.latitude, self.altitude

    def single_station(self, sched, start_time, tle_file):
        """Calculate passes, graph, and schedule for one station."""
        logger.debug("station: %s coords: %s area: %s scores: %s",
                     self.id, self.coords, self.area.area_id, self.satellites)

        opts = sched.opts
        pattern_args = {
            "station": self.id,
            "output_dir": opts.output_dir,
            "date": start_time.strftime("%Y%m%d"),
            "time": start_time.strftime("%H%M%S")
        }
        if opts.xml:
            pattern_args["mode"] = "request"
        elif opts.report:
            pattern_args["mode"] = "report"

        allpasses = self.get_next_passes(opts, sched, start_time, tle_file)

        area_boundary = self.area.boundary(8)
        self.area.poly = area_boundary.contour_poly
        allpasses = trim_associated_overlaps(allpasses, self.area, timedelta(seconds=opts.delay),
                                             timedelta(minutes=self.min_pass))

        if opts.avoid is not None:
            avoid_list = get_passes_from_xml_file(opts.avoid)
        else:
            avoid_list = None

        logger.info("computing best schedule for area %s" % self.area.area_id)
        schedule, (graph, labels) = get_best_sched(allpasses,
                                                   self.area,
                                                   timedelta(seconds=opts.delay),
                                                   avoid_list)

        logger.debug(pformat(schedule))
        for opass in schedule:
            opass.rec = True
        reception_passes = restore_unused_trim(allpasses, timedelta(seconds=opts.delay))
        image_saver = _start_station_plots(sched, self, reception_passes, pattern_args)
        logger.info("generating file")

        _write_station_reception_products(sched, reception_passes, self.coords, start_time, pattern_args)

        if opts.plot:
            logger.info("Waiting for images to be saved...")
            image_saver.join()
            logger.info("Done!")

        _write_station_metno_reports(sched, reception_passes, [p for p in reception_passes if p.rec],
                                    self, start_time, pattern_args)

        _publish_xml(sched, reception_passes, start_time, pattern_args, self.id, self.antenna)

        _write_station_viewer(sched, self, allpasses, reception_passes, start_time, pattern_args, tle_file)

        _persist_station_results(sched, graph, labels, allpasses, pattern_args, self.id)

        return graph, allpasses

    def get_next_passes(self, opts, sched, start_time, tle_file):
        """Get the next passes."""
        logger.info("Computing next satellite passes")
        allpasses = get_next_passes(self.satellites, start_time,
                                    sched.forward,
                                    self.coords, tle_file,
                                    aqua_terra_dumps=(sched.dump_url or True
                                                      if opts.no_aqua_terra_dump
                                                      else None),
                                    min_pass=self.min_pass,
                                    local_horizon=self.local_horizon
                                    )
        logger.info("Computation of next overpasses done")
        logger.debug(str(sorted(allpasses, key=lambda x: x.risetime)))
        return allpasses



class Scheduler:
    """docstring for Scheduler."""

    def __init__(self, stations, min_pass, forward, start, dump_url, patterns, center_id, plot_parameters, plot_title):
        """Initialize the scheduler."""
        self.stations = stations
        self.min_pass = min_pass
        self.forward = forward
        self.start = start
        self.dump_url = dump_url
        self.patterns = patterns
        self.center_id = center_id
        self.plot_parameters = plot_parameters
        self.plot_title = plot_title
        self.opts = None


def conflicting_passes(allpasses, delay=None):
    """Get the passes in groups of conflicting passes."""
    if delay is None:
        delay = timedelta(seconds=0)

    passes = sorted(allpasses, key=lambda x: x.risetime)

    overpass = passes[0]
    last_time = overpass.falltime
    group = [overpass]
    groups = []
    for overpass in passes[1:]:
        if overpass.risetime - delay < last_time:
            group.append(overpass)
            if last_time < overpass.falltime:
                last_time = overpass.falltime

        else:
            groups.append(group)
            group = [overpass]
            last_time = overpass.falltime

    groups.append(group)
    return groups


def get_non_conflicting_groups(passes, delay=None):
    """Get the different non-conflicting solutions in a group of conflicting passes."""
    # Uses graphs and maximal clique finding with the Bron-Kerbosch algorithm.
    if delay is None:
        delay = timedelta(seconds=0)

    order = len(passes)

    if order == 1:
        return [passes]

    graph = Graph(order)

    for i, overpass in enumerate(sorted(passes, key=lambda x: x.risetime)):
        for j in range(i + 1, order):
            if not overpass.overlaps(passes[j], delay):
                graph.add_edge(i, j)

    groups = []
    for res in graph.bron_kerbosch(set(), set(graph.vertices), set()):
        grp = []
        for vertex in res:
            grp.append(passes[vertex])
        groups.append(sorted(grp))

    return groups


def coverage_weight(hours_apart):
    """Weigh the coverage of two passes, from nearly 1 when simultaneous down to 0.5 when hours apart."""
    a = 0.25
    b = a / 4
    k = b * np.log(1 / 3.0) + a
    sh = k - 0.25
    return 0.5 / (np.exp(((hours_apart + sh) - a) / b) + 1) + 0.5


def overlap_penalty_weight(hours_apart):
    """Weigh the overlap of two passes, from nearly 1 when simultaneous down to 0 when hours apart."""
    a = 0.25
    b = a / 4
    return 1 / (np.exp((hours_apart - a) / b) + 1)


def _area_or_zero(polygon):
    if polygon is None:
        return 0
    return polygon.area()


def _weighted_share_of_area(polygon, overpass, area_of_interest):
    """Get the share of the area covered by *polygon*, weighted by the day and night scores of *overpass*."""
    area = area_of_interest.poly.area()
    day, night = split_day_and_night(polygon, overpass.uptime)
    return (_area_or_zero(night) * (overpass.satellite.score.night / area) +
            _area_or_zero(day) * (overpass.satellite.score.day / area))


def _coverage_and_score(overpass, area_of_interest):
    """Get the part of the area covered by *overpass*, and its day/night weighted share of the area."""
    coverage, score = overpass.score.get(area_of_interest, (None, None))
    if score is None:
        coverage = intersect(overpass.boundary.contour_poly, area_of_interest.poly)
        score = 0 if coverage is None else _weighted_share_of_area(coverage, overpass, area_of_interest)
        overpass.score[area_of_interest] = (coverage, score)
    return coverage, score


def combine(p1, p2, area_of_interest):
    """Score scheduling *p2* right after *p1*: their coverage of the area, minus what they cover twice."""
    coverage1, score1 = _coverage_and_score(p1, area_of_interest)
    coverage2, score2 = _coverage_and_score(p2, area_of_interest)

    overlap = None if coverage1 is None or coverage2 is None else intersect(coverage1, coverage2)
    if overlap is None:
        overlap_score = 0
    else:
        overlap_score = (_weighted_share_of_area(overlap, p1, area_of_interest) +
                         _weighted_share_of_area(overlap, p2, area_of_interest)) / 2.0

    hours_apart = abs(p2.uptime - p1.uptime).seconds / 3600.
    return coverage_weight(hours_apart) * (score1 + score2) - overlap_penalty_weight(hours_apart) * overlap_score


def _first_passes(alternatives):
    return {alternative[0] for alternative in alternatives}


def _last_passes(alternatives):
    return {max(alternative, key=lambda overpass: overpass.falltime) for alternative in alternatives}


def _matches_avoid_entry(overpass, entry):
    return overpass == entry or (
        overpass.satellite.schedule_name == entry.satellite.name and overpass.overlaps(entry))


def get_best_sched(overpasses, area_of_interest, delay, avoid_list=None):
    """Get the best schedule based on *area_of_interest*."""
    avoid_list = avoid_list or []
    passes = sorted(overpasses, key=lambda x: x.risetime)
    avoided = {id(overpass) for overpass in passes
               if any(_matches_avoid_entry(overpass, entry) for entry in avoid_list)}
    alternatives_per_conflict = [get_non_conflicting_groups(conflict, delay)
                                 for conflict in conflicting_passes(passes, delay)]
    logger.debug("non conflicting %s", str(alternatives_per_conflict))

    start, end = 0, len(passes) + 1
    vertex = {id(overpass): index for index, overpass in enumerate(passes, start=1)}
    graph = Graph(n_vertices=len(passes) + 2)

    def add_arc(p1, p2):
        if id(p1) in avoided or id(p2) in avoided:
            weight = 0
        else:
            weight = combine(p1, p2, area_of_interest)
        logger.debug("Adding arc between %s and %s with weight %s", p1, p2, weight)
        graph.add_arc(vertex[id(p1)], vertex[id(p2)], weight)

    previous_ends = set()
    for alternatives in alternatives_per_conflict:
        firsts = _first_passes(alternatives)
        for previous_end in previous_ends:
            for first in firsts:
                add_arc(previous_end, first)
        for alternative in alternatives:
            for p1, p2 in zip(alternative[:-1], alternative[1:]):
                add_arc(p1, p2)
        previous_ends = _last_passes(alternatives)

    for last in previous_ends:
        graph.add_arc(vertex[id(last)], end)
    for first in _first_passes(alternatives_per_conflict[0]):
        graph.add_arc(start, vertex[id(first)])

    _, path = graph.dag_longest_path(start, end)
    return [passes[index - 1] for index in path[1:-1]], (graph, passes)


def save_passes(allpasses, poly, output_dir, plot_parameters=None, plot_title=None):
    """Save overpass plots to png and store in directory *output_dir*."""
    from trollsched.drawing import save_fig
    for overpass in allpasses:
        save_fig(overpass, poly=poly, directory=output_dir, plot_parameters=plot_parameters, plot_title=plot_title)
    logger.info("All plots saved!")


def get_passes_from_xml_file(filenames):
    """Read passes from aquisition xml files."""
    import defusedxml.ElementTree as ET
    pass_list = []
    for filename in filenames:
        tree = ET.parse(filename)
        root = tree.getroot()
        for overpass in root.iter("pass"):
            start_time = datetime.strptime(
                overpass.attrib["start-time"], "%Y-%m-%d-%H:%M:%S")
            end_time = datetime.strptime(
                overpass.attrib["end-time"], "%Y-%m-%d-%H:%M:%S")
            pass_list.append(SimplePass(
                overpass.attrib["satellite"], start_time, end_time))
    return pass_list


def build_filename(pattern_name, pattern_dict, kwargs):
    """Build absolute path from pattern dictionary."""
    for k in pattern_dict.keys():
        for v in pattern_dict.values():
            if "{" + k + "}" in v:
                kwargs[k] = pattern_dict[k].format(**kwargs)

    return pattern_dict[pattern_name].format(**kwargs)


def send_file(url, file):
    """Send a file through ftp."""
    pathname, filename = os.path.split(file)
    del pathname
    if url.scheme in ["file", "", b""]:
        pass
    elif url.scheme in ["ftp", b"ftp"]:
        import ftplib  # nosec B402 - Legacy plain-FTP support; deployments must accept its transport risks.
        session = ftplib.FTP(url.hostname, url.username, url.password)  # nosec B321 - Legacy plain-FTP compatibility.
        with open(file, "rb") as xfile:
            session.storbinary("STOR " + str(filename), xfile)
        session.quit()
    else:
        logger.error("Cannot save to %s, but file is there:",
                     (str(url.scheme), str(file)))


def _start_station_plots(scheduler, station, passes, pattern_args):
    if not scheduler.opts.plot:
        return None
    from threading import Thread
    directory = build_filename("dir_plots", scheduler.patterns, pattern_args)
    logger.info("Saving plots to %s", directory)
    image_saver = Thread(target=save_passes, args=(passes, station.area.boundary(8).contour_poly, directory,
                                                 scheduler.plot_parameters, scheduler.plot_title))
    image_saver.start()
    return image_saver


def _write_station_reception_products(scheduler, passes, coords, start_time, pattern_args):
    if scheduler.opts.scisys:
        generate_sch_file(build_filename("file_sci", scheduler.patterns, pattern_args), passes, coords)
    if scheduler.opts.meos:
        generate_meos_file(build_filename("file_meos", scheduler.patterns, pattern_args), passes,
                           coords, start_time + timedelta(hours=scheduler.start), True)


def _write_station_metno_reports(scheduler, passes, selected, station, start_time, pattern_args):
    if scheduler.opts.metno_xml:
        start = start_time + timedelta(hours=scheduler.start)
        end = start_time + timedelta(hours=scheduler.forward)
        for pattern, report_passes in (("file_metno_xml_all", passes), ("file_metno_xml", selected)):
            generate_metno_xml_file(build_filename(pattern, scheduler.patterns, pattern_args),
                                    report_passes, station.coords, start, end, station.id, scheduler.center_id,
                                    report_mode=True)


def _write_station_viewer(scheduler, station, allpasses, reception_passes, start_time, pattern_args, tle_file):
    if not scheduler.opts.html:
        return
    from trollsched.viewer.station import station_page

    patterns = dict(scheduler.patterns)
    patterns.setdefault("file_html", "{dir_output}/{date}-{time}-schedule-{station}.html")
    filename = build_filename("file_html", patterns, pattern_args)
    span = (start_time + timedelta(hours=scheduler.start), start_time + timedelta(hours=scheduler.forward))
    page = station_page(station, allpasses, reception_passes, scheduler.opts.avoid, span,
                        timedelta(seconds=scheduler.opts.delay), tle_file=tle_file,
                        coastlines_file=patterns.get("file_coastlines"),
                        title=f"{station.id} pass schedule {span[0]:%Y-%m-%d} → {span[1]:%Y-%m-%d}",
                        sources=[os.path.basename(f) for f in scheduler.opts.avoid or []])
    with open(filename, "w", encoding="utf-8") as stream:
        stream.write(page)
    logger.info("Generated %s", filename)


def _persist_station_results(scheduler, graph, labels, passes, pattern_args, station_id):
    if scheduler.opts.graph or scheduler.opts.comb:
        filename = build_filename("file_graph", scheduler.patterns, pattern_args)
        graph.save(filename)
        graph.export(labels=[str(label) for label in labels], filename=filename + ".gv")
    if scheduler.opts.comb:
        directory = build_filename("dir_output", scheduler.patterns, pattern_args)
        with open(os.path.join(directory, f"allpasses.{station_id}.pkl"), "wb") as stream:
            pickle.dump(passes, stream)


def _publish_xml(scheduler, passes, start_time, pattern_args, station_id, antenna):
    opts = scheduler.opts
    if opts.xml or opts.report:
        pattern_args["mode"] = "request"
        xmlfile = _write_xml(scheduler, passes, start_time, pattern_args, station_id, antenna, report_mode=False)
        send_file(urlparse(opts.output_url or opts.output_dir), xmlfile)
    if opts.report:
        pattern_args["mode"] = "report"
        _write_xml(scheduler, passes, start_time, pattern_args, station_id, antenna, report_mode=True)


def _write_xml(scheduler, passes, start_time, pattern_args, station_id, antenna, report_mode):
    xmlfile = generate_xml_file(
        passes, start_time + timedelta(hours=scheduler.start),
        start_time + timedelta(hours=scheduler.forward),
        build_filename("file_xml", scheduler.patterns, pattern_args),
        station_id, scheduler.center_id, report_mode=report_mode, antenna=antenna,
    )
    logger.info("Generated %s", xmlfile)
    return xmlfile


def _combined_graph_labels(combinations, station_ids):
    labels = []
    for combination in combinations:
        station_labels = []
        for index, _ in enumerate(station_ids):
            overpass = combination[index][0]
            if overpass is None:
                station_labels.append("---")
            else:
                prefix = "+ " if overpass.rec else "  "
                station_labels.append(prefix + str(overpass))
        labels.append("\\n".join(station_labels))
    return labels


def _reset_received_flags(allpasses):
    passes = {}
    try:
        for station_id, station_passes in allpasses.items():
            passes[station_id] = list(station_passes)
            for overpass in passes[station_id]:
                overpass.rec = False
    except Exception:
        logger.exception("Failed to reset 'rec' for s:%s  ap:%s  passes[s]:%s  p:%s",
                         station_id, station_passes, passes[station_id], overpass)
        raise
    return passes


def _mark_coordinated_passes(schedule):
    for combination in schedule:
        for station_pass in combination:
            if station_pass[0] is not None:
                station_pass[0].rec = True


def _write_combined_station_products(scheduler, passes, station_id, start_time, pattern_args, station_coords,
                                     antenna):
    passes = restore_unused_trim(passes, timedelta(seconds=scheduler.opts.delay))
    if scheduler.opts.plot:
        station = next(station for station in scheduler.stations if station.id == station_id)
        _start_station_plots(scheduler, station, passes, pattern_args).join()
    if scheduler.opts.scisys or scheduler.opts.meos or scheduler.opts.metno_xml:
        coords = station_coords[station_id]
    if scheduler.opts.scisys:
        generate_sch_file(build_filename("file_sci", scheduler.patterns, pattern_args),
                          passes, coords)
    _publish_xml(scheduler, passes, start_time, pattern_args, station_id, antenna)
    if scheduler.opts.meos:
        meosfile = generate_meos_file(build_filename("file_meos", scheduler.patterns, pattern_args),
                                      passes, coords,
                                      start_time + timedelta(hours=scheduler.start), False)
        logger.info("Generated %s", meosfile)
    if scheduler.opts.metno_xml:
        metno_xmlfile = generate_metno_xml_file(build_filename("file_metno_xml", scheduler.patterns, pattern_args),
                                                passes, coords,
                                                start_time + timedelta(hours=scheduler.start),
                                                start_time + timedelta(hours=scheduler.forward),
                                                station_id, scheduler.center_id, False)
        logger.info("Generated %s", metno_xmlfile)


def _save_combined_graph(scheduler, graph, combinations, station_ids, pattern_args):
    if scheduler.opts.graph:
        pattern_args["station"] = "comb"
        filename = build_filename("file_graph", scheduler.patterns, pattern_args)
        graph.save(filename)
        graph.export(labels=_combined_graph_labels(combinations, station_ids), filename=filename + ".gv")


def combined_stations(scheduler, start_time, graph, allpasses):
    """Generate coordinated schedules and products for two or more stations."""
    logger.info("Generating coordinated schedules ...")

    pattern_args = {
        "output_dir": scheduler.opts.output_dir,
        "date": start_time.strftime("%Y%m%d"),
        "time": start_time.strftime("%H%M%S")
    }
    if scheduler.opts.xml:
        pattern_args["mode"] = "request"
    elif scheduler.opts.report:
        pattern_args["mode"] = "report"

    passes = _reset_received_flags(allpasses)

    station_ids, schedule, (combined_graph, combinations) = get_combined_sched(graph, passes)

    _mark_coordinated_passes(schedule)

    logger.info("generating files")

    _save_combined_graph(scheduler, combined_graph, combinations, station_ids, pattern_args)

    station_coords = {}
    station_antennas = {}
    for station in scheduler.stations:
        station_coords.setdefault(station.id, station.coords)
        station_antennas.setdefault(station.id, station.antenna)
    for station_id in passes:
        pattern_args["station"] = station_id + "-comb"
        logger.info("Create schedule file(s) for %s", station_id)
        _write_combined_station_products(scheduler, passes[station_id], station_id, start_time,
                                         pattern_args, station_coords, station_antennas[station_id])

    logger.info("Finished coordinated schedules.")


def _load_station_results(scheduler, station_id, directory, pattern_args):
    pattern_args["station"] = station_id
    graph = Graph()
    graph.load(build_filename("file_graph", scheduler.patterns, pattern_args) + ".npz")
    with open(os.path.join(directory, f"allpasses.{station_id}.pkl"), "rb") as stream:
        passes = pickle.load(stream)  # nosec B301 - Load only own artifacts from a trusted output directory.
    return graph, passes


def _run_station_processes(scheduler, start_time, tle_file, directory, pattern_args):
    from multiprocessing import Process
    processes, station_ids = {}, []
    graphs, passes = {}, {}
    for station in scheduler.stations:
        station_ids.append(station.id)
        processes[station.id] = Process(target=station.single_station, args=(scheduler, start_time, tle_file))
        processes[station.id].start()
    for station_id in station_ids:
        processes[station_id].join()
        graphs[station_id], passes[station_id] = _load_station_results(
            scheduler, station_id, directory, pattern_args)
    return graphs, passes


def _run_stations(scheduler, start_time, tle_file, directory, pattern_args):
    if scheduler.opts.multiproc and len(scheduler.stations) != 1:
        return _run_station_processes(scheduler, start_time, tle_file, directory, pattern_args)
    graphs, passes = {}, {}
    for station in scheduler.stations:
        graphs[station.id], passes[station.id] = station.single_station(scheduler, start_time, tle_file)
    return graphs, passes


def run(args=None):
    """The schedule command."""
    global logger

    opts = parse_args(args)

    if opts.config:
        scheduler = utils.read_config(opts.config)

    if opts.output_dir:
        scheduler.patterns["dir_output"] = opts.output_dir
    else:
        scheduler.patterns.setdefault("dir_output", os.path.curdir)

    setup_logging(opts)

    tle_file = opts.tle
    if opts.start_time:
        start_time = opts.start_time
    else:
        start_time = datetime.utcnow()

    logger.debug("start: %s forward: %s" % (scheduler.start, scheduler.forward))

    pattern_args = {
        "output_dir": opts.output_dir,
        "date": start_time.strftime("%Y%m%d"),
        "time": start_time.strftime("%H%M%S")
    }
    dir_output = build_filename("dir_output", scheduler.patterns, pattern_args)
    if not os.path.exists(dir_output):
        logger.debug("Create output dir " + dir_output)
        os.makedirs(dir_output)

    if len(scheduler.stations) > 1:
        opts.comb = True
        with open(os.path.join(dir_output, "opts.pkl"), "wb") as stream:
            pickle.dump(opts, stream)
    else:
        opts.comb = False

    scheduler.opts = opts

    graph, allpasses = _run_stations(scheduler, start_time, tle_file, dir_output, pattern_args)

    if opts.comb:
        combined_stations(scheduler, start_time, graph, allpasses)


def setup_logging(opts):
    """Set up the logging."""
    global logger
    if opts.log:
        previous = os.path.exists(opts.log)
        handler = logging.handlers.RotatingFileHandler(opts.log, backupCount=7)
        if previous:
            handler.doRollover()
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s: %(asctime)s :"
                                           " %(name)s] %(message)s",
                                           "%Y-%m-%d %H:%M:%S"))
    if opts.verbose:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO
    handler.setLevel(loglevel)
    logging.getLogger("").setLevel(loglevel)
    logging.getLogger("").addHandler(handler)
    if opts.mail:
        mhandler = logging.handlers.SMTPHandler("localhost",
                                                "pytroll-schedule@pytroll.org",
                                                opts.mail,
                                                "Scheduler")
        mhandler.setLevel(logging.WARNING)
        logging.getLogger("").addHandler(mhandler)
    logger = logging.getLogger("trollsched")


def parse_args(args=None):
    """Parse arguments from the command line."""
    parser = argparse.ArgumentParser()
    # general arguments
    parser.add_argument("-c", "--config", required=True, default=None,
                        help="configuration file to use")
    parser.add_argument("-t", "--tle", default=None,
                        help="tle file to use")
    parser.add_argument("-l", "--log", default=None,
                        help="File to log to (defaults to stdout)")
    parser.add_argument("-m", "--mail", nargs="*", default=None,
                        help="mail address(es) to send error messages to.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print debug messages too")
    # argument group: coordinates and times
    group_postim = parser.add_argument_group(title="start-parameter",
                                             description="(or set values in the configuration file)")
    group_postim.add_argument("--lat", type=float,
                              help="Latitude, degrees north")
    group_postim.add_argument("--lon", type=float,
                              help="Longitude, degrees east")
    group_postim.add_argument("--alt", type=float,
                              help="Altitude, km")
    group_postim.add_argument("-f", "--forward", type=float,
                              help="time ahead to compute the schedule")
    group_postim.add_argument("-s", "--start-time", type=datetime.fromisoformat,
                              help="start time of the schedule to compute")
    group_postim.add_argument("-d", "--delay", default=60, type=float,
                              help="delay (in seconds) needed between two " +
                                   "consecutive passes (60 seconds by default)")
    # argument group: special behaviour
    group_spec = parser.add_argument_group(title="special",
                                           description="(additional parameter changing behaviour)")
    group_spec.add_argument("-a", "--avoid",
                            default=[],
                            nargs="*",
                            help="xml request file(s) with passes to avoid")
    group_spec.add_argument("--no-aqua-terra-dump", action="store_false",
                            help="do not consider Aqua/Terra-dumps")
    group_spec.add_argument("--multiproc", action="store_true",
                            help="use multiple parallel processes")
    # argument group: output-related
    group_outp = parser.add_argument_group(title="output",
                                           description="(file pattern are taken from configuration file)")
    group_outp.add_argument("-o", "--output-dir", default=None,
                            help="where to put generated files")
    group_outp.add_argument("-u", "--output-url", default=None,
                            help="URL where to put generated schedule file(s)" +
                                 ", otherwise use output-dir")
    group_outp.add_argument("-x", "--xml", action="store_true",
                            help="generate an xml request file (schedule)"
                            )
    group_outp.add_argument("-r", "--report", action="store_true",
                            help="generate an xml report file (schedule)")
    group_outp.add_argument("--scisys", action="store_true",
                            help="generate a SCISYS schedule file")
    group_outp.add_argument("-p", "--plot", action="store_true",
                            help="generate plot images")
    group_outp.add_argument("-g", "--graph", action="store_true",
                            help="save graph info")
    group_outp.add_argument("--meos", action="store_true",
                            help="generate a MEOS schedule file")
    group_outp.add_argument("--metno-xml", action="store_true",
                            help="generate a METNO xml pass data file")
    group_outp.add_argument("--html", action="store_true",
                            help="generate an interactive HTML page of the schedule (pattern 'file_html')")
    opts = parser.parse_args(args)

    if (not opts.config) and (not (opts.lon or opts.lat or opts.alt)):
        parser.error("Coordinates must be provided in the absence of "
                     "configuration file.")

    if not (opts.xml or opts.scisys or opts.report or opts.metno_xml or opts.meos or opts.html):
        parser.error("No output specified, use '--scisys', '-x/--xml', '-r/--report', '--meos', '--metno-xml' "
                     "or '--html'")

    return opts


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("Something wrong happened!")
        raise
