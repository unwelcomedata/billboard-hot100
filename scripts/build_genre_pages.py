#!/usr/bin/env python3
"""Build the genre-selection dropdown picker (Pages, NOT social).

The owner asked for genre selection as a dropdown on the GitHub Pages site, not a
social post ("Maybe make that one a drop down on the github page for genre selection,
not posted to social"). This renders ONE web-mode per-genre line chart of Hot 100
appearances-over-time (1970+) for EACH of the 12 genres into docs/genres/<slug>.png,
plus docs/genres.html with a <select> that swaps the <img> src — same pattern as the
presidential-speeches and countries-income-disparity pickers.

Defaults to METAL — the owner's genre — which is why the standalone Metal chart was
dropped from the social set and lives here instead.

docs/genres/*.png + docs/genres.html are regenerable, so they are gitignored (curated
into the release branch later). Reads DuckDB READ-ONLY; re-runnable; overwrites outputs.

Run from the project root (project .venv — matplotlib unused, charts via Pillow factory):
    .venv/bin/python scripts/build_genre_pages.py
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT.parent.parent / "shared"))

import duckdb  # noqa: E402
from colors import c  # noqa: E402
from chart_templates import line_chart  # noqa: E402

DB = PROJECT / "data" / "project.duckdb"
OUT_DIR = PROJECT / "docs" / "genres"
HTML = PROJECT / "docs" / "genres.html"
SOURCE = "Billboard Hot 100 (chart history) \u00b7 genre via MusicBrainz \u00b7 @unwelcomedata"

# All 12 genres in chart_genre_by_year. Default = Metal (owner's genre).
DEFAULT_GENRE = "Metal"
WEB_W, WEB_H = 1664, 936


def slug(name: str) -> str:
    """Filesystem-safe slug for a genre name (e.g. 'Hip-Hop/Rap' -> 'hip-hop-rap')."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)

    genres = [r[0] for r in con.execute(
        "SELECT DISTINCT genre FROM chart_genre_by_year ORDER BY genre"
    ).fetchall()]

    made: list[tuple[str, str]] = []  # (genre, slug)
    for g in genres:
        df = con.execute(
            "SELECT year, appearances FROM chart_genre_by_year "
            "WHERE genre = ? AND year >= 1970 ORDER BY year",
            [g],
        ).df()
        s = slug(g)
        img = line_chart(
            df=df, x_col="year",
            series=[{"col": "appearances", "label": g, "color": c("teal")}],
            x_axis_label="",        # year ticks are self-evident -> no axis title
            y_axis_label="Hot 100 chart appearances",
            y_min=0, markers=True, label_last=False, legend=False,
            x_tick_step=10,
            title=f"{g} on the Billboard Hot 100, by year",
            subtitle="Chart appearances per year (artists genred via MusicBrainz, from 1970).",
            source=SOURCE,
            img_width=WEB_W, img_height=WEB_H, web_mode=True,
        )
        img.save(OUT_DIR / f"{s}.png", format="PNG", optimize=True)
        made.append((g, s))

    con.close()

    build_id = str(int(time.time()))  # cache-buster
    default_slug = slug(DEFAULT_GENRE) if DEFAULT_GENRE in genres else made[0][1]
    options = "\n".join(
        f'      <option value="{s}"{" selected" if s == default_slug else ""}>{g}</option>'
        for g, s in made
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Billboard Hot 100 \u2014 genre trends by genre</title>
<style>
  body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 0;
          color: #1c2530; background: #fff; }}
  .wrap {{ max-width: 960px; margin: 0 auto; padding: 24px 16px 48px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  p.lead {{ color: #55606b; font-size: 15px; margin: 0 0 18px; line-height: 1.5; }}
  .controls {{ margin: 0 0 16px; }}
  label {{ font-weight: 600; font-size: 14px; margin-right: 8px; }}
  select {{ font-size: 15px; padding: 7px 10px; border: 1px solid #c7ced5;
            border-radius: 6px; background: #fff; min-width: 260px; }}
  .chart img {{ width: 100%; height: auto; border: 1px solid #eee; border-radius: 6px; }}
  .note {{ color: #77818b; font-size: 13px; margin-top: 14px; line-height: 1.5; }}
  a {{ color: #005F73; }}
  .backlink {{ display: inline-block; margin: 0 0 14px; font-size: 16px;
               font-weight: 600; text-decoration: underline; }}
</style>
</head>
<body>
<div class="wrap">
  <a class="backlink" href="../">&larr; Back to Billboard Hot 100</a>
  <h1>Genre trends on the Billboard Hot 100</h1>
  <p class="lead">
    Pick a genre to see its Hot 100 chart appearances per year, from 1970. Genre is assigned
    at the <b>artist</b> level from MusicBrainz tags (top-tag-wins); <b>Other/Unknown</b> is a
    coverage residual (unmatched artists + the long tail of artists with &lt; 20 Hot 100
    appearances), not a musical category. The Hot 100 ranks a blended metric (sales + airplay +
    streaming); streaming entered the formula in 2013, so cross-era comparisons carry that caveat.
  </p>
  <div class="controls">
    <label for="genre">Genre</label>
    <select id="genre" onchange="swap()">
{options}
    </select>
  </div>
  <div class="chart">
    <img id="chart" src="genres/{default_slug}.png?v={build_id}" alt="genre chart"
         onerror="this.alt='(chart not generated for this genre)';">
  </div>
  <p class="note">Source: {SOURCE}. build {build_id}</p>
</div>
<script>
  // ?v=BUILD is a cache-buster so the browser always loads the current PNGs.
  var BUILD = '{build_id}';
  function swap() {{
    var s = document.getElementById('genre').value;
    document.getElementById('chart').src = 'genres/' + s + '.png?v=' + BUILD;
    document.getElementById('chart').alt = s + ' Hot 100 appearances by year';
  }}
</script>
</body>
</html>
"""
    HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {len(made)} genre charts -> {OUT_DIR}")
    print(f"Wrote picker -> {HTML}  (default = {DEFAULT_GENRE})")


if __name__ == "__main__":
    main()
