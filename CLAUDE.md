# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the script

```bash
# Install the single dependency
pip install requests

# Interactive mode (prompts for layer, bbox, zoom)
python mbtiles_downloader.py <api-key>

# Non-interactive (fully scripted)
python mbtiles_downloader.py <api-key> output.mbtiles \
  --nw 60.35,24.78 --se 60.10,25.25 \
  --zoom-min 10 --zoom-max 14

# Custom WMTS source
python mbtiles_downloader.py <api-key> --capabilities "https://example.com/WMTSCapabilities.xml"

# Extra options
  --workers N       Parallel download threads (default: 8)
  --retries N       Per-tile retry attempts (default: 3)
  --header KEY:VAL  Extra HTTP header (repeatable)
  --log FILE        Log all tile results to FILE
  --name / --description / --attribution   MBTiles metadata overrides
```

Python 3.10+ is required (`int | None` union syntax).

The default WMTS source is the Maanmittauslaitos (NLS Finland) open WMTS. Free API keys at maanmittauslaitos.fi.

## Architecture

Everything lives in `mbtiles_downloader.py` — no modules, packages, or tests. Execution flow:

1. **WMTS parsing** (`load_capabilities`, `parse_layers`, `parse_tile_matrix_sets`, `parse_kvp_endpoint`) — fetches and parses OGC WMTSCapabilities XML via `xml.etree.ElementTree` with namespace dict `NS`.
2. **Interactive selection** (`select_layer_and_tms`, `_pick`, `ask_bbox`, `ask_zoom`) — walks the user through layer, TileMatrixSet, bounding box, and zoom range. Auto-selects when there is only one option or exactly one Web Mercator TMS.
3. **URL template construction** (`build_url_template`) — prefers `ResourceURL` REST templates; falls back to KVP query-string style. Query params from the capabilities URL (e.g. `api-key`) are forwarded to tile URLs automatically via `parse_qs`/`urlencode`.
4. **Coordinate math** (`deg_to_tile`, `tile_bounds`, `iter_tiles`) — converts WGS-84 bbox corners to XYZ tile coordinates per zoom level using Web Mercator formula.
5. **Download** (`download`, `fetch_tile`) — `ThreadPoolExecutor` with configurable workers; tiles written in batches of 200 to SQLite via `init_db`. Y is flipped from XYZ to TMS convention (`xyz_to_tms_y`) before writing.

### MBTiles output

Standard SQLite file with `metadata` and `tiles` tables. WAL mode + NORMAL synchronous writes for performance. Tiles keyed by `(zoom_level, tile_column, tile_row)` where `tile_row` uses TMS bottom-origin Y.

### CRS handling

`is_mercator()` normalises CRS identifiers against `_MERCATOR_CRS`. When a non-Mercator TMS is selected, a warning is printed — `deg_to_tile` uses the Web Mercator formula and tile boundaries will be wrong for other projections.

### `--nw`/`--se` parsing

`parse_latlon()` in `main()` accepts multiple decimal formats: `"60.35,24.78"`, `"60,35 24,78"` (comma as decimal separator, space-separated), and `"60,35,24,78"` (four-part comma form). Both `--nw` and `--se` must be provided together or omitted entirely.

## airspace_to_kml.py

Fetches active airspace zones from two Fintraffic Sky API endpoints and writes one KML file per zone into `./kml/` and one KMZ file into `./kmz/`, both named by `designator`.

```bash
python airspace_to_kml.py [MM/DD/YYYY]   # defaults to today
python airspace_to_kml.py 04/28/2026
```

No external dependencies — stdlib only. Key details:

- Fetches `getaipsuptempozonesactivatedbynotam` and `getzonesbynotam`; results are merged. If the same designator appears in both, the second overwrites the first.
- API returns coordinates as `"lat lon,lat lon,…"`; `parse_coords` swaps to KML's `lon,lat,alt` order.
- `hex_to_kml_color` converts `#rrggbb` + opacity to KML's `aabbggrr` format, preserving the API's fill/stroke colours.
- Polygon rings are closed automatically if the first and last point don't match.
- KMZ files are deflate-compressed ZIPs containing `doc.kml`.
