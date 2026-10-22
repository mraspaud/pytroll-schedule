"""Interactive HTML page showing acquisition schedules as a timeline with pass coverage maps.

The page is built from ``template.html``, ``viewer.css`` and ``viewer.js`` in
this package, with the data embedded as JSON so the result is one
self-contained file.
"""

import json
from datetime import datetime, timezone
from importlib import resources

from trollsched.viewer import geo
from trollsched.viewer.records import timestamp

GEO_ALTITUDE_KM = 35786.0


def _asset(name):
    return resources.files("trollsched.viewer").joinpath(name).read_text(encoding="utf-8")


PRODUCTS = "products/"


def products_config(products, poll=120):
    """Normalise the *products* argument of :func:`build_page`: a URL with a trailing slash and a poll interval."""
    if products is None or products is False:
        return None
    if products is True:
        products = PRODUCTS
    if isinstance(products, str):
        products = {"url": products}
    url = products.get("url", "products/")
    return {"url": url if url.endswith("/") else url + "/", "poll": int(products.get("poll", poll))}


def build_page(records, span, coords, coastlines=None, area_outline=None, title=None,
               view_height=GEO_ALTITUDE_KM, generated=None, sources=(), products=True):
    """Build the viewer page.

    Args:
        records: pass records from :func:`trollsched.viewer.records.build_records`.
        span: (start, end) naive UTC datetimes of the schedule.
        coords: station (lon, lat, alt); the map is centred on it.
        coastlines: lon/lat rings from :func:`trollsched.viewer.geo.load_coastlines`.
        area_outline: lon/lat ring of the area of interest, or None.
        title: page title.
        view_height: height of the near-sided perspective viewpoint in km.
        generated: generation time (defaults to now).
        sources: names of the input files, shown in the header.
        products: where the page finds what was received and processed: a directory relative to
            the page (``products/`` by default) or a dict ``{"url": ..., "poll": seconds}``; None to
            disable.  The page loads ``<url>index.js`` from there when it exists; see the viewer
            documentation for its format.
    """
    lon, lat = coords[0], coords[1]
    start, end = span
    first, step, elevations = geo.sun_elevation_series(start, end, lon, lat)
    data = {
        "passes": records,
        "span": [timestamp(start), timestamp(end)],
        "map": {"lat": lat, "lon": lon, "height_km": view_height, "lines": coastlines or [],
                "area": area_outline},
        "sun": {"start": timestamp(first), "step": step, "elevation": elevations},
        "generated": (generated or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC"),
        "sources": list(sources),
        "products": products_config(products),
    }
    title = title or f"Pass schedule {start:%Y-%m-%d} → {end:%Y-%m-%d}"
    page = _asset("template.html")
    page = page.replace("__TITLE__", title)
    page = page.replace("/*__CSS__*/", _asset("viewer.css"))
    page = page.replace("/*__JS__*/", _asset("viewer.js"))
    return page.replace("__DATA__", json.dumps(data, separators=(",", ":")))
