#!/usr/bin/env python3
"""
Fetch active airspace zones from the Fintraffic Sky API and write
one KML file per entry into a ./kml/ directory.

Fetches from two endpoints:
  - getaipsuptempozonesactivatedbynotam  (AUP/TEMPO zones)
  - getzonesbynotam                      (NOTAM zones)

Usage:
  python airspace_to_kml.py [date]          # date defaults to today (MM/DD/YYYY)
  python airspace_to_kml.py 04/28/2026
"""

import json
import os
import sys
import zipfile
from datetime import date
from urllib.request import Request, urlopen

API_URLS = [
    "https://api.sky.fintraffic.fi/api/airspace/getaipsuptempozonesactivatedbynotam?date={date}",
    "https://api.sky.fintraffic.fi/api/airspace/getzonesbynotam?date={date}",
]
KML_DIR = "kml"
KMZ_DIR = "kmz"


def fetch_zones(query_date: str) -> list:
    zones = []
    for template in API_URLS:
        url = template.format(date=query_date)
        print(f"Fetching {url} …")
        req = Request(url, headers={"User-Agent": "airspace-kml/1.0", "Accept": "application/json"})
        with urlopen(req, timeout=20) as r:
            payload = json.loads(r.read())
        if payload.get("error"):
            msgs = payload.get("errorMessages") or []
            sys.exit("API error: " + "; ".join(msgs))
        zones.extend(payload.get("data", []))
    return zones


def parse_coords(coord_str: str) -> list[tuple[float, float]]:
    """Return [(lon, lat), …] from 'lat lon,lat lon,…' string."""
    pairs = []
    for token in coord_str.strip().split(","):
        parts = token.strip().split()
        if len(parts) == 2:
            lat, lon = float(parts[0]), float(parts[1])
            pairs.append((lon, lat))
    return pairs


def hex_to_kml_color(hex_color: str, opacity: float) -> str:
    """Convert #rrggbb + 0-1 opacity to KML aabbggrr hex string."""
    hex_color = hex_color.lstrip("#")
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    a = format(round(opacity * 255), "02x")
    return f"{a}{b}{g}{r}"


def zone_to_kml(zone: dict) -> str:
    coords = parse_coords(zone.get("coordinates", ""))
    if not coords:
        return ""

    # Close the ring if needed
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    coord_str = " ".join(f"{lon},{lat},0" for lon, lat in coords)

    fill_color   = hex_to_kml_color(zone.get("fillColor",   "#e77f67"), zone.get("fillOpacity",   0.1))
    stroke_color = hex_to_kml_color(zone.get("strokeColor", "#e77f67"), zone.get("strokeOpacity", 1.0))
    stroke_width = zone.get("strokeWeight", 2.0)

    designator  = zone.get("designator", "unknown")
    description = designator

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{designator}</name>
    <Style id="zone_style">
      <LineStyle>
        <color>{stroke_color}</color>
        <width>{stroke_width}</width>
      </LineStyle>
      <PolyStyle>
        <color>{fill_color}</color>
      </PolyStyle>
    </Style>
    <Placemark>
      <name>{designator}</name>
      <description>{description}</description>
      <styleUrl>#zone_style</styleUrl>
      <Polygon>
        <tessellate>1</tessellate>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>{coord_str}</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""


def main():
    query_date = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%m/%d/%Y")

    zones = fetch_zones(query_date)
    if not zones:
        print("No zones returned.")
        return

    os.makedirs(KML_DIR, exist_ok=True)
    os.makedirs(KMZ_DIR, exist_ok=True)

    written = 0
    skipped = 0
    for zone in zones:
        designator = zone.get("designator", "").strip()
        if not designator:
            skipped += 1
            continue

        kml = zone_to_kml(zone)
        if not kml:
            skipped += 1
            continue

        safe_name = designator.replace("/", "_").replace("\\", "_")

        kml_path = os.path.join(KML_DIR, f"{safe_name}.kml")
        with open(kml_path, "w", encoding="utf-8") as f:
            f.write(kml)

        kmz_path = os.path.join(KMZ_DIR, f"{safe_name}.kmz")
        with zipfile.ZipFile(kmz_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("doc.kml", kml)

        written += 1

    print(f"Written {written} KML/KMZ files to ./{KML_DIR}/ and ./{KMZ_DIR}/  ({skipped} skipped)")


if __name__ == "__main__":
    main()
