#!/usr/bin/env python3
"""
Download WMTS map tiles and create an MBTiles file.

Usage:
  python mbtiles_downloader.py <WMTSCapabilities.xml URL or path> [output.mbtiles] [options]

The script fetches the capabilities, lets you pick a layer and coordinate
system interactively, then downloads all tiles into an MBTiles SQLite file.
"""

import argparse
import math
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen

import requests


# ── WMTS namespaces ───────────────────────────────────────────────────────────

NS = {
    "wmts":  "http://www.opengis.net/wmts/1.0",
    "ows":   "http://www.opengis.net/ows/1.1",
    "xlink": "http://www.w3.org/1999/xlink",
}

# CRS identifiers treated as XYZ/Web-Mercator compatible
_MERCATOR_CRS = {
    "urn:ogc:def:crs:epsg::3857",
    "urn:ogc:def:crs:epsg:6.18.3:3857",
    "urn:ogc:def:crs:epsg:6.3:3857",
    "epsg:3857",
    "googlemapscompatible",
    "webmercatorquad",
    "pseudomercator",
    "wgs84pseudomercator",
    "wgs84pseudomercator",
}

def is_mercator(crs: str) -> bool:
    return crs.lower().replace(" ", "").replace("_", "").replace("-", "") in {
        c.replace("_", "").replace("-", "") for c in _MERCATOR_CRS
    }


# ── WMTS XML helpers ──────────────────────────────────────────────────────────

def _txt(el: ET.Element, xpath: str) -> str:
    found = el.find(xpath, NS)
    return (found.text or "").strip() if found is not None else ""


def load_capabilities(source: str) -> ET.Element:
    if source.startswith(("http://", "https://")):
        print(f"Fetching {source} …")
        req = Request(source, headers={"User-Agent": "mbtiles-downloader/2.0"})
        with urlopen(req, timeout=20) as r:
            data = r.read()
    else:
        with open(source, "rb") as f:
            data = f.read()
    return ET.fromstring(data)


def parse_tile_matrix_sets(root: ET.Element) -> dict:
    sets = {}
    contents = root.find("wmts:Contents", NS)
    if contents is None:
        return sets
    for tms in contents.findall("wmts:TileMatrixSet", NS):
        tms_id   = _txt(tms, "ows:Identifier")
        crs      = _txt(tms, "ows:SupportedCRS")
        matrices = [_txt(tm, "ows:Identifier")
                    for tm in tms.findall("wmts:TileMatrix", NS)]
        if tms_id:
            sets[tms_id] = {"crs": crs, "matrices": matrices}
    return sets


def parse_layers(root: ET.Element) -> list:
    contents = root.find("wmts:Contents", NS)
    if contents is None:
        return []
    layers = []
    for layer in contents.findall("wmts:Layer", NS):
        layer_id = _txt(layer, "ows:Identifier")
        title    = _txt(layer, "ows:Title") or layer_id
        formats  = [el.text.strip() for el in layer.findall("wmts:Format", NS) if el.text]
        tms_links = [_txt(link, "wmts:TileMatrixSet")
                     for link in layer.findall("wmts:TileMatrixSetLink", NS)]
        styles = [_txt(s, "ows:Identifier") for s in layer.findall("wmts:Style", NS)]
        resource_urls = [
            {"format": ru.get("format", ""), "template": ru.get("template", "")}
            for ru in layer.findall("wmts:ResourceURL", NS)
            if ru.get("resourceType") == "tile"
        ]
        if layer_id:
            layers.append({
                "id":            layer_id,
                "title":         title,
                "formats":       formats,
                "tms_links":     tms_links,
                "default_style": styles[0] if styles else "default",
                "resource_urls": resource_urls,
            })
    return layers


def parse_kvp_endpoint(root: ET.Element) -> str:
    ops = root.find("ows:OperationsMetadata", NS)
    if ops is None:
        return ""
    for op in ops.findall("ows:Operation", NS):
        if op.get("name") == "GetTile":
            get_el = op.find(".//ows:Get", NS)
            if get_el is not None:
                href = get_el.get("{http://www.w3.org/1999/xlink}href", "")
                return href.rstrip("?")
    return ""


def zoom_from_matrix_id(matrix_id: str) -> int | None:
    m = re.search(r"(\d+)$", matrix_id)
    return int(m.group(1)) if m else None


def matrix_prefix(matrices: list[str]) -> str:
    if not matrices:
        return ""
    m = re.match(r"^(.*?)(\d+)$", matrices[0])
    if not m:
        return ""
    p = m.group(1)
    return p if all(mid.startswith(p) for mid in matrices) else ""


def build_url_template(layer: dict, tms_id: str, tms_info: dict, kvp_base: str) -> str | None:
    prefix        = matrix_prefix(tms_info["matrices"])
    z_placeholder = f"{prefix}{{z}}" if prefix else "{z}"
    style         = layer["default_style"]

    for ru in layer["resource_urls"]:
        tmpl = ru["template"]
        if not tmpl:
            continue
        tmpl = tmpl.replace("{TileMatrixSet}", tms_id)
        tmpl = tmpl.replace("{style}", style).replace("{Style}", style)
        tmpl = tmpl.replace("{TileMatrix}", z_placeholder)
        tmpl = tmpl.replace("{TileRow}", "{y}").replace("{TileCol}", "{x}")
        return tmpl

    if kvp_base:
        fmt    = next(iter(layer["formats"]), "image/png")
        params = (
            f"SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
            f"&LAYER={layer['id']}&STYLE={style}"
            f"&FORMAT={fmt}&TILEMATRIXSET={tms_id}"
            f"&TILEMATRIX={z_placeholder}&TILEROW={{y}}&TILECOL={{x}}"
        )
        return f"{kvp_base}?{params}"

    return None


# ── interactive prompts ───────────────────────────────────────────────────────

def _pick(prompt: str, items: list, label_fn) -> int:
    """Print a numbered menu and return the 0-based index of the user's choice."""
    print()
    for i, item in enumerate(items):
        print(f"  {i+1:>3}.  {label_fn(item)}")
    print()
    while True:
        raw = input(f"{prompt} [1–{len(items)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return int(raw) - 1
        print(f"       Please enter a number between 1 and {len(items)}.")


def _ask_float(prompt: str, lo: float, hi: float) -> float:
    while True:
        raw = input(f"  {prompt} ({lo} to {hi}): ").strip()
        try:
            v = float(raw)
            if lo <= v <= hi:
                return v
        except ValueError:
            pass
        print(f"    Enter a number between {lo} and {hi}.")


def _ask_int(prompt: str, lo: int, hi: int, default: int) -> int:
    while True:
        raw = input(f"  {prompt} [{default}]: ").strip()
        if raw == "":
            return default
        if raw.lstrip("-").isdigit():
            v = int(raw)
            if lo <= v <= hi:
                return v
        print(f"    Enter an integer between {lo} and {hi}.")


def ask_bbox() -> tuple[float, float, float, float]:
    print("\nEnter bounding box corners in decimal degrees (WGS-84):")
    print("  NW = top-left corner,  SE = bottom-right corner\n")
    nw_lat = _ask_float("NW latitude  (north)", -90.0,   90.0)
    nw_lon = _ask_float("NW longitude (west) ", -180.0, 180.0)
    se_lat = _ask_float("SE latitude  (south)", -90.0,  nw_lat)
    se_lon = _ask_float("SE longitude (east) ", nw_lon, 180.0)
    return nw_lon, se_lat, se_lon, nw_lat  # west, south, east, north


def ask_zoom(z_min_avail: int, z_max_avail: int) -> tuple[int, int]:
    print(f"\nAvailable zoom levels: {z_min_avail}–{z_max_avail}")
    z_min = _ask_int("Min zoom", z_min_avail, z_max_avail, z_min_avail)
    z_max = _ask_int("Max zoom", z_min,        z_max_avail, z_max_avail)
    return z_min, z_max


def select_layer_and_tms(root: ET.Element) -> tuple[dict, str, dict, str]:
    """Interactively pick a layer and TileMatrixSet; return (layer, tms_id, tms_info, url_template)."""
    tms_sets = parse_tile_matrix_sets(root)
    layers   = parse_layers(root)
    kvp_base = parse_kvp_endpoint(root)

    if not layers:
        sys.exit("No layers found in the capabilities document.")

    # layer selection (auto-pick if only one)
    if len(layers) == 1:
        layer = layers[0]
        print(f"\nOne layer available, selected: {layer['title']}")
    else:
        print(f"\nFound {len(layers)} layer(s):")
        idx = _pick(
            "Select layer",
            layers,
            lambda l: l["title"] + (f"  [{l['id']}]" if l["title"] != l["id"] else ""),
        )
        layer = layers[idx]

    # TileMatrixSet selection
    linked = [(tid, tms_sets[tid]) for tid in layer["tms_links"] if tid in tms_sets]
    if not linked:
        sys.exit(f"Layer '{layer['title']}' has no linked TileMatrixSets in the capabilities.")

    mercator = [(tid, info) for tid, info in linked if is_mercator(info["crs"])]

    if len(linked) == 1:
        tms_id, tms_info = linked[0]
        print(f"One TileMatrixSet available, selected: {tms_id}")
    elif len(mercator) == 1:
        tms_id, tms_info = mercator[0]
        print(f"\nAuto-selected Web Mercator TileMatrixSet: {tms_id}")
    else:
        def tms_label(item):
            tid, info = item
            tag = "  [Web Mercator — recommended]" if is_mercator(info["crs"]) else ""
            n   = len(info["matrices"])
            return f"{tid}  |  {info['crs']}  |  {n} zoom levels{tag}"

        print(f"\nAvailable TileMatrixSets for '{layer['title']}':")
        idx = _pick("Select TileMatrixSet", linked, tms_label)
        tms_id, tms_info = linked[idx]

    if not is_mercator(tms_info["crs"]):
        print(f"\n  Warning: '{tms_info['crs']}' is not Web Mercator.")
        print("  Tile coordinates may not align correctly with WGS-84 bounds.\n")

    url_template = build_url_template(layer, tms_id, tms_info, kvp_base)
    if not url_template:
        sys.exit("Could not construct a tile URL template from the capabilities.")

    return layer, tms_id, tms_info, url_template


# ── coordinate math ───────────────────────────────────────────────────────────

def deg_to_tile(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    n       = 2 ** zoom
    x       = int((lon_deg + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat_deg)
    y       = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def xyz_to_tms_y(y: int, zoom: int) -> int:
    return (2 ** zoom) - 1 - y


def tile_bounds(bbox: tuple, zoom: int) -> tuple[int, int, int, int]:
    west, south, east, north = bbox
    x_min, y_min = deg_to_tile(north, west, zoom)
    x_max, y_max = deg_to_tile(south, east, zoom)
    return x_min, y_min, x_max, y_max


def iter_tiles(bbox: tuple, zoom_min: int, zoom_max: int):
    for z in range(zoom_min, zoom_max + 1):
        x_min, y_min, x_max, y_max = tile_bounds(bbox, z)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                yield z, x, y


def count_tiles(bbox: tuple, zoom_min: int, zoom_max: int) -> int:
    total = 0
    for z in range(zoom_min, zoom_max + 1):
        x_min, y_min, x_max, y_max = tile_bounds(bbox, z)
        total += (x_max - x_min + 1) * (y_max - y_min + 1)
    return total


# ── MBTiles database ──────────────────────────────────────────────────────────

def init_db(path: str, meta: dict) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (
            name  TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS tiles (
            zoom_level  INTEGER NOT NULL,
            tile_column INTEGER NOT NULL,
            tile_row    INTEGER NOT NULL,
            tile_data   BLOB,
            PRIMARY KEY (zoom_level, tile_column, tile_row)
        );
    """)
    conn.executemany(
        "INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)",
        [(k, str(v)) for k, v in meta.items()],
    )
    conn.commit()
    return conn


# ── tile fetching & download ──────────────────────────────────────────────────

def fetch_tile(
    session: requests.Session,
    url_template: str,
    z: int, x: int, y: int,
    retries: int = 3,
) -> tuple[int, int, int, bytes | None]:
    url = url_template.format(z=z, x=x, y=y)
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                return z, x, y, resp.content
            if resp.status_code == 404:
                return z, x, y, None
        except requests.RequestException:
            pass
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    return z, x, y, None


def download(
    url_template: str,
    output: str,
    bbox: tuple,
    zoom_min: int,
    zoom_max: int,
    workers: int,
    headers: dict,
    meta: dict,
    retries: int,
):
    total = count_tiles(bbox, zoom_min, zoom_max)
    w     = len(str(total))
    print(f"\nTiles to fetch: {total:,}  (zoom {zoom_min}–{zoom_max})")

    conn    = init_db(output, meta)
    session = requests.Session()
    session.headers.update(headers)

    done    = 0
    skipped = 0
    batch: list[tuple] = []
    BATCH  = 200

    def flush():
        conn.executemany(
            "INSERT OR REPLACE INTO tiles (zoom_level, tile_column, tile_row, tile_data)"
            " VALUES (?, ?, ?, ?)",
            batch,
        )
        conn.commit()
        batch.clear()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_tile, session, url_template, z, x, y, retries): None
            for z, x, y in iter_tiles(bbox, zoom_min, zoom_max)
        }
        for future in as_completed(futures):
            z, x, y, data = future.result()
            done += 1
            if data:
                batch.append((z, x, xyz_to_tms_y(y, z), data))
                if len(batch) >= BATCH:
                    flush()
            else:
                skipped += 1

            if done % 50 == 0 or done == total:
                pct = done / total * 100
                print(f"\r  {done:{w}}/{total}  {pct:5.1f}%  skipped={skipped}",
                      end="", flush=True)

    if batch:
        flush()
    conn.close()
    print(f"\nDone — wrote {done - skipped:,} tiles to {output}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Download WMTS tiles and create an MBTiles file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "capabilities",
        help="WMTSCapabilities.xml URL or local file path",
    )
    p.add_argument(
        "output", nargs="?", default=None,
        help="Output .mbtiles path (default: <layer_id>.mbtiles)",
    )

    bbox = p.add_argument_group("bounding box (prompted interactively if omitted)")
    bbox.add_argument("--nw", metavar="LAT,LON", help="NW corner, e.g. 60.35,24.78")
    bbox.add_argument("--se", metavar="LAT,LON", help="SE corner, e.g. 60.10,25.25")

    zoom = p.add_argument_group("zoom (prompted interactively if omitted)")
    zoom.add_argument("--zoom-min", type=int, default=None, metavar="Z")
    zoom.add_argument("--zoom-max", type=int, default=None, metavar="Z")

    dl = p.add_argument_group("download")
    dl.add_argument("--workers", type=int, default=8,  help="Parallel download threads")
    dl.add_argument("--retries", type=int, default=3,  help="Per-tile retry attempts")
    dl.add_argument(
        "--header", action="append", default=[], metavar="KEY:VALUE",
        help="Extra HTTP request header (repeatable)",
    )

    meta = p.add_argument_group("MBTiles metadata overrides")
    meta.add_argument("--name",        default=None, help="Layer name (default: layer title)")
    meta.add_argument("--description", default="")
    meta.add_argument("--attribution", default="")

    return p.parse_args()


def main():
    args = parse_args()

    # ── parse headers ─────────────────────────────────────────────────────────
    headers: dict[str, str] = {}
    for h in args.header:
        if ":" not in h:
            sys.exit(f"Bad --header (expected KEY:VALUE): {h!r}")
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()

    # ── WMTS: layer + TMS selection ───────────────────────────────────────────
    root = load_capabilities(args.capabilities)
    layer, tms_id, tms_info, url_template = select_layer_and_tms(root)

    # ── bounding box ──────────────────────────────────────────────────────────
    def parse_latlon(value: str, flag: str) -> tuple[float, float]:
        try:
            lat, lon = value.split(",")
            return float(lat.strip()), float(lon.strip())
        except ValueError:
            sys.exit(f"Error: {flag} must be LAT,LON (e.g. 60.35,24.78), got: {value!r}")

    if args.nw is not None and args.se is not None:
        nw_lat, nw_lon = parse_latlon(args.nw, "--nw")
        se_lat, se_lon = parse_latlon(args.se, "--se")
        if not (se_lat < nw_lat):
            sys.exit("Error: NW latitude must be greater than SE latitude.")
        if not (nw_lon < se_lon):
            sys.exit("Error: NW longitude must be less than SE longitude.")
        west, south, east, north = nw_lon, se_lat, se_lon, nw_lat
    elif args.nw is not None or args.se is not None:
        sys.exit("Error: provide both --nw and --se or neither.")
    else:
        west, south, east, north = ask_bbox()

    bbox = (west, south, east, north)

    # ── zoom range ────────────────────────────────────────────────────────────
    zoom_levels = sorted(
        z for z in (zoom_from_matrix_id(m) for m in tms_info["matrices"])
        if z is not None
    )
    z_avail_min = zoom_levels[0]  if zoom_levels else 0
    z_avail_max = zoom_levels[-1] if zoom_levels else 18

    if args.zoom_min is not None and args.zoom_max is not None:
        zoom_min, zoom_max = args.zoom_min, args.zoom_max
        if zoom_min > zoom_max:
            sys.exit("Error: --zoom-min must be ≤ --zoom-max")
    else:
        zoom_min, zoom_max = ask_zoom(z_avail_min, z_avail_max)

    # ── output path ───────────────────────────────────────────────────────────
    output = args.output or f"{layer['id']}.mbtiles"

    # ── tile format ───────────────────────────────────────────────────────────
    fmt = next(
        (f.split("/")[-1] for f in layer["formats"] if "png" in f.lower()),
        next((f.split("/")[-1] for f in layer["formats"]), "png"),
    )

    # ── summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  Layer:    {layer['title']}")
    print(f"  CRS:      {tms_info['crs']}")
    print(f"  Bbox:     W={west} S={south} E={east} N={north}")
    print(f"  Zoom:     {zoom_min}–{zoom_max}")
    print(f"  Output:   {output}")
    print(f"{'─'*60}")

    confirm = input("\nStart download? [Y/n]: ").strip().lower()
    if confirm not in ("", "y", "yes"):
        print("Aborted.")
        sys.exit(0)

    # ── download ──────────────────────────────────────────────────────────────
    metadata = {
        "name":        args.name or layer["title"],
        "description": args.description,
        "format":      fmt,
        "type":        "baselayer",
        "version":     "1.1",
        "attribution": args.attribution,
        "minzoom":     zoom_min,
        "maxzoom":     zoom_max,
        "bounds":      f"{west},{south},{east},{north}",
        "center":      f"{(west+east)/2:.6f},{(south+north)/2:.6f},{zoom_min}",
    }

    download(
        url_template=url_template,
        output=output,
        bbox=bbox,
        zoom_min=zoom_min,
        zoom_max=zoom_max,
        workers=args.workers,
        headers=headers,
        meta=metadata,
        retries=args.retries,
    )


if __name__ == "__main__":
    main()
