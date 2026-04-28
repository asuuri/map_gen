# mbtiles-downloader

Download map tiles from a WMTS server and package them into an [MBTiles](https://github.com/mapbox/mbtiles-spec) file.

## Requirements

```bash
pip install requests
```

Python 3.10 or newer.

## Usage

```bash
python mbtiles_downloader.py <api-key> [output.mbtiles] [options]
```

The script appends the API key to the capabilities URL, fetches the document, walks you through selecting a layer and coordinate system, prompts for a bounding box and zoom range, then downloads all tiles into a single `.mbtiles` file.

The default capabilities URL points to the Finnish NLS (Maanmittauslaitos) WMTS service. Use `--capabilities` to target a different server.

## Example — Finnish NLS (Maanmittauslaitos)

Get your free API key from [maanmittauslaitos.fi](https://www.maanmittauslaitos.fi/rajapinnat/api-avaimen-ohje).

### Fully interactive

```bash
python mbtiles_downloader.py <API-KEY>
```

Example session:

```
Fetching https://avoin-karttakuva.maanmittauslaitos.fi/…

Found 8 layer(s):
    1.  Taustakartta          [taustakartta]
    2.  Maastokartta          [maastokartta]
    3.  Ortokuva              [ortokuva]
    4.  Kiinteistöjaotus      [kiinteistojaotus]
    …

Select layer [1–8]: 1

Auto-selected Web Mercator TileMatrixSet: WGS84_Pseudo-Mercator

Enter bounding box corners in decimal degrees (WGS-84):
  NW = top-left corner,  SE = bottom-right corner

  NW latitude  (north) (-90.0 to 90.0):   60.35
  NW longitude (west)  (-180.0 to 180.0): 24.78
  SE latitude  (south) (-90.0 to 60.35):  60.10
  SE longitude (east)  (24.78 to 180.0):  25.25

Available zoom levels: 0–15
  Min zoom [0]: 10
  Max zoom [10]: 14

────────────────────────────────────────────────────────────
  Layer:    Taustakartta
  CRS:      urn:ogc:def:crs:EPSG::3857
  Bbox:     W=24.78 S=60.1 E=25.25 N=60.35
  Zoom:     10–14
  Output:   taustakartta.mbtiles
────────────────────────────────────────────────────────────

Start download? [Y/n]: y

Tiles to fetch: 1,360  (zoom 10–14)
  1360/1360  100.0%  skipped=0
Done — wrote 1,360 tiles to taustakartta.mbtiles
```

### Non-interactive (scripted)

Pass all options as flags to skip every prompt:

```bash
python mbtiles_downloader.py <API-KEY> helsinki.mbtiles \
  --nw 60.35,24.78 --se 60.10,25.25 \
  --zoom-min 10 --zoom-max 14
```

### Custom WMTS server

```bash
python mbtiles_downloader.py <API-KEY> output.mbtiles \
  --capabilities "https://example.com/wmts/WMTSCapabilities.xml" \
  --nw 60.35,24.78 --se 60.10,25.25 \
  --zoom-min 10 --zoom-max 14
```

## Options

| Flag | Default | Description |
|---|---|---|
| `api_key` | *(required)* | API key appended to the capabilities URL as `?api-key=` |
| `output` | `<layer_id>.mbtiles` | Output file path |
| `--capabilities URL` | NLS WMTS URL | WMTSCapabilities.xml URL or local file path |
| `--nw LAT,LON` | *(prompted)* | NW (top-left) corner of bounding box |
| `--se LAT,LON` | *(prompted)* | SE (bottom-right) corner of bounding box |
| `--zoom-min Z` | *(prompted)* | Lowest zoom level to download |
| `--zoom-max Z` | *(prompted)* | Highest zoom level to download |
| `--workers N` | `8` | Parallel download threads |
| `--retries N` | `3` | Retry attempts per failed tile |
| `--header KEY:VALUE` | — | Extra HTTP request header (repeatable) |
| `--log FILE` | — | Log all tile results (OK/SKIP) to FILE |
| `--name` | layer title | Override MBTiles `name` metadata field |
| `--description` | — | MBTiles `description` metadata field |
| `--attribution` | — | MBTiles `attribution` metadata field |

## Bounding box coordinates

The bounding box is defined by two corner points in decimal degrees (WGS-84):
- **NW** — north-west (top-left): `LAT,LON` where LAT is the northern edge and LON is the western edge
- **SE** — south-east (bottom-right): `LAT,LON` where LAT is the southern edge and LON is the eastern edge

Both comma-decimal (`60,35,24,78`) and period-decimal (`60.35,24.78`) formats are accepted, as is space-separated (`60.35 24.78`).

| City | `--nw` | `--se` |
|---|---|---|
| Helsinki | `60.35,24.78` | `60.10,25.25` |
| Tampere | `61.60,23.60` | `61.40,23.90` |
| Turku | `60.55,22.10` | `60.35,22.40` |
| Oulu | `65.10,25.35` | `64.95,25.65` |

## Notes

- **Tile limit** — high zoom levels produce exponentially more tiles. Zoom 15 over a city can be tens of thousands of tiles; zoom 18+ over a large area can be millions.
- **Rate limiting** — the default 8 worker threads are a reasonable balance. Reduce with `--workers` if the server returns HTTP 429 errors.
- **Coordinate system** — the script works correctly with Web Mercator (EPSG:3857) tile matrix sets. When a non-Mercator CRS is selected, a warning is shown as tile coordinates may not align with the given WGS-84 bounding box.
- **MBTiles Y axis** — MBTiles uses TMS tile convention (Y origin at bottom). The script flips the XYZ Y coordinate automatically before writing to the database.

---

# airspace-to-kml

Fetch active airspace zones from the [Fintraffic Sky API](https://api.sky.fintraffic.fi) and write one KML and KMZ file per zone.

## Requirements

No external dependencies — stdlib only.

## Usage

```bash
python airspace_to_kml.py [MM/DD/YYYY]   # date defaults to today
python airspace_to_kml.py 04/28/2026
```

Output is written to:
- `kml/<designator>.kml`
- `kmz/<designator>.kmz`

## Data sources

Fetches from two endpoints for the given date:

| Endpoint | Content |
|---|---|
| `getaipsuptempozonesactivatedbynotam` | AUP/TEMPO zones activated by NOTAM |
| `getzonesbynotam` | Airspace zones activated by NOTAM |

Each zone becomes one file, named by its `designator` value (e.g. `EFD504F.kml`). KMZ files are standard ZIP archives containing `doc.kml`.
