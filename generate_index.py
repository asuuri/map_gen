#!/usr/bin/env python3
"""
Build ./dist/ — copy KMZ and MBTiles files there and write an index.html.

Usage:
  python generate_index.py [--title "My Map Files"]
  python generate_index.py --title "Finland Airspace + Basemap"
"""

import argparse
import os
import shutil
from datetime import datetime, timezone

DIST_DIR = "dist"
KMZ_SRC  = "kmz"


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def collect_kmz() -> list[dict]:
    if not os.path.isdir(KMZ_SRC):
        return []
    return [
        {"name": f, "rel": f"kmz/{f}", "src": os.path.join(KMZ_SRC, f),
         "size": os.path.getsize(os.path.join(KMZ_SRC, f))}
        for f in sorted(os.listdir(KMZ_SRC))
        if f.endswith(".kmz")
    ]


def collect_mbtiles() -> list[dict]:
    return [
        {"name": f, "rel": f, "src": f,
         "size": os.path.getsize(f)}
        for f in sorted(os.listdir("."))
        if f.endswith(".mbtiles")
    ]


def file_rows(files: list[dict], data_attr: str = "") -> str:
    if not files:
        return '<tr><td colspan="3" class="empty">No files available.</td></tr>'
    rows = []
    for f in files:
        rows.append(
            f'<tr {data_attr}>'
            f'<td class="fname"><a href="{f["rel"]}" download>{f["name"]}</a></td>'
            f'<td class="fsize">{fmt_size(f["size"])}</td>'
            f'<td class="fdl"><a href="{f["rel"]}" download class="dl-btn" title="Download">↓</a></td>'
            f'</tr>'
        )
    return "\n".join(rows)


def render(title: str, kmz: list[dict], mbt: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root {{
  --bg:         #0b0b0b;
  --surface:    #141414;
  --border:     #1e1e1e;
  --text:       #c8c8c8;
  --muted:      #4a4a4a;
  --accent:     #3dd68c;
  --accent-bg:  rgba(61, 214, 140, 0.07);
  --mono: "Cascadia Code", "Fira Code", "JetBrains Mono", "Consolas",
          "Courier New", monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue",
          Arial, sans-serif;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.6;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}}

.wrap {{
  max-width: 820px;
  margin: 0 auto;
  padding: 56px 28px 72px;
}}

/* ── header ── */
header {{
  margin-bottom: 52px;
}}

header h1 {{
  font-size: 17px;
  font-weight: 500;
  color: #e8e8e8;
  letter-spacing: 0.01em;
}}

header .stamp {{
  margin-top: 6px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.04em;
}}

/* ── section ── */
.section {{
  margin-bottom: 44px;
}}

.section-top {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}}

.section-top h2 {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
}}

.badge {{
  font-family: var(--mono);
  font-size: 10px;
  color: var(--accent);
  background: var(--accent-bg);
  border: 1px solid rgba(61,214,140,0.15);
  padding: 1px 7px;
  border-radius: 3px;
  letter-spacing: 0.02em;
}}

/* ── tabs ── */
.tabs {{
  display: flex;
  gap: 2px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
}}

.tab-btn {{
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  padding: 8px 16px;
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
  cursor: pointer;
  transition: color 100ms, border-color 100ms;
  display: flex;
  align-items: center;
  gap: 8px;
}}

.tab-btn:hover {{ color: var(--text); }}

.tab-btn.active {{
  color: var(--text);
  border-bottom-color: var(--accent);
}}

.tab-panel {{ display: none; }}
.tab-panel.active {{ display: block; }}

/* ── search ── */
.search-wrap {{
  margin-left: auto;
}}

#kmz-search {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  font-family: var(--mono);
  font-size: 12px;
  padding: 4px 10px;
  width: 200px;
  outline: none;
  transition: border-color 120ms;
}}

#kmz-search::placeholder {{ color: var(--muted); }}
#kmz-search:focus {{ border-color: var(--accent); }}

/* ── table ── */
table {{
  width: 100%;
  border-collapse: collapse;
  border: 1px solid var(--border);
  border-radius: 5px;
  overflow: hidden;
}}

thead tr {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}}

thead tr:hover {{ background: var(--surface); }}

th {{
  padding: 8px 14px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  text-align: left;
  white-space: nowrap;
}}

th.fsize, th.fdl {{ text-align: right; }}

tbody tr {{
  border-bottom: 1px solid var(--border);
  transition: background 80ms ease;
}}

tbody tr:last-child {{ border-bottom: none; }}
tbody tr:hover {{ background: var(--surface); }}

td {{
  padding: 9px 14px;
  vertical-align: middle;
}}

.fname {{
  font-family: var(--mono);
  font-size: 12.5px;
  word-break: break-all;
}}

.fname a {{
  color: var(--text);
  text-decoration: none;
  transition: color 80ms;
}}

.fname a:hover {{ color: var(--accent); }}

.fsize {{
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--muted);
  text-align: right;
  white-space: nowrap;
  width: 72px;
}}

.fdl {{
  width: 36px;
  text-align: right;
  padding-left: 0;
}}

.dl-btn {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  color: var(--muted);
  text-decoration: none;
  font-size: 14px;
  transition: color 80ms, background 80ms;
}}

.dl-btn:hover {{
  color: var(--accent);
  background: var(--accent-bg);
}}

.empty {{
  font-family: var(--mono);
  font-size: 12px;
  color: var(--muted);
  padding: 18px 14px;
  text-align: center;
}}

#kmz-empty {{
  display: none;
  font-family: var(--mono);
  font-size: 12px;
  color: var(--muted);
  padding: 14px;
  text-align: center;
}}

/* ── footer ── */
footer {{
  margin-top: 56px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.03em;
}}
</style>
</head>
<body>
<div class="wrap">

  <header>
    <h1>{title}</h1>
    <p class="stamp">Generated {now}</p>
  </header>

  <nav class="tabs">
    <button class="tab-btn" data-tab="mbt">
      MBTiles — Basemap <span class="badge">{len(mbt)}</span>
    </button>
    <button class="tab-btn active" data-tab="kmz">
      KMZ — Airspace Zones <span class="badge" id="kmz-count">{len(kmz)}</span>
    </button>
  </nav>

  <div id="tab-mbt" class="tab-panel">
    <table>
      <thead>
        <tr>
          <th class="fname">File</th>
          <th class="fsize">Size</th>
          <th class="fdl"></th>
        </tr>
      </thead>
      <tbody>
        {file_rows(mbt)}
      </tbody>
    </table>
  </div>

  <div id="tab-kmz" class="tab-panel active">
    <div class="section-top">
      <div class="search-wrap">
        <input id="kmz-search" type="search" placeholder="Filter…" autocomplete="off" spellcheck="false">
      </div>
    </div>
    <table id="kmz-table">
      <thead>
        <tr>
          <th class="fname">Designator</th>
          <th class="fsize">Size</th>
          <th class="fdl"></th>
        </tr>
      </thead>
      <tbody id="kmz-body">
        {file_rows(kmz)}
      </tbody>
    </table>
    <p id="kmz-empty">No matches.</p>
  </div>

  <footer>{len(kmz) + len(mbt)} file(s) &nbsp;·&nbsp; {title}</footer>

</div>
<script>
(function () {{
  // ── tabs ──
  document.querySelectorAll('.tab-btn').forEach(function (btn) {{
    btn.addEventListener('click', function () {{
      document.querySelectorAll('.tab-btn').forEach(function (b) {{ b.classList.remove('active'); }});
      document.querySelectorAll('.tab-panel').forEach(function (p) {{ p.classList.remove('active'); }});
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    }});
  }});

  // ── kmz search ──
  var input = document.getElementById('kmz-search');
  var rows  = document.getElementById('kmz-body').getElementsByTagName('tr');
  var count = document.getElementById('kmz-count');
  var empty = document.getElementById('kmz-empty');
  var total = rows.length;

  input.addEventListener('input', function () {{
    var q = this.value.trim().toLowerCase();
    var visible = 0;
    for (var i = 0; i < rows.length; i++) {{
      var cell = rows[i].querySelector('.fname');
      var show = !q || (cell && cell.textContent.toLowerCase().indexOf(q) !== -1);
      rows[i].style.display = show ? '' : 'none';
      if (show) visible++;
    }}
    count.textContent = q ? visible + ' / ' + total : total;
    empty.style.display = visible === 0 ? '' : 'none';
  }});
}})();
</script>
</body>
</html>
"""


def main():
    p = argparse.ArgumentParser(description="Generate dist/ distribution site.")
    p.add_argument("--title", default="Map Files", help="Page title")
    args = p.parse_args()

    kmz = collect_kmz()
    mbt = collect_mbtiles()

    # build dist/
    os.makedirs(os.path.join(DIST_DIR, "kmz"), exist_ok=True)

    for f in kmz:
        shutil.copy2(f["src"], os.path.join(DIST_DIR, "kmz", f["name"]))

    for f in mbt:
        shutil.copy2(f["src"], os.path.join(DIST_DIR, f["name"]))

    html_path = os.path.join(DIST_DIR, "index.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render(args.title, kmz, mbt))

    print(f"dist/  →  {len(kmz)} KMZ, {len(mbt)} MBTiles, index.html")


if __name__ == "__main__":
    main()
