#!/usr/bin/env python
"""Build notebooks/04-viz.ipynb from source (nbformat).

04-viz CONSUMES the chart-ready tables from 03-prepare and EXPLORES framings so the
owner can decide the story. It does NOT build chart data (03 owns that) — it opens
DuckDB READ-ONLY and reads the chart_* tables.

The lead chart is a BUMP (rank-over-time). The shared `bump` template does not exist
yet — that is this project's capability build, done later in 06-viz-social. So here we
explore the STORY + FRAMING using the existing shared `line` template: a bump is a
specialized line of rank-vs-year, so we plot an INVERTED rank (rank 1 at the top) by
transforming the value to (N+1-rank) and relabelling the y ticks back to '#rank'.

Charts render inline via the shared Pillow factory (the same engine social export
uses) — the venv is Python 3.14 and matplotlib RecursionErrors, so Pillow it is.

Regenerate with:  .venv/bin/python scripts/_build_nb_04_viz.py
Then execute with: .venv/bin/python -m nbconvert --to notebook \
    --execute --inplace notebooks/04-viz.ipynb
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "notebooks" / "04-viz.ipynb"


def md(src: str):
    return nbf.v4.new_markdown_cell(src)


def code(src: str):
    return nbf.v4.new_code_cell(src)


cells = [
    md(
        "# 04 — Viz (exploration)\n"
        "\n"
        "**billboard-hot100.** Explore how music **genres** rose and fell at the top of the\n"
        "Billboard Hot 100 over the decades. The framing is now **LOCKED (2026-10-15)** — see\n"
        "the ⭐ banner below; the lead **bump chart** (and the full social set) is built in\n"
        "`06-viz-social`. This notebook is the exploratory record that led to those decisions,\n"
        "updated to reflect the final story (incl. the song-level pre/post comparison in §5).\n"
        "\n"
        "> ⭐ This notebook **CONSUMES** the chart-ready tables `03-prepare` built\n"
        "> (`chart_genre_by_year`, `chart_genre_by_decade`, `chart_genre_rank_top`,\n"
        "> `chart_genre_number_ones_by_decade`). It opens DuckDB **read-only** and does\n"
        "> **not** create any `chart_*` table. If exploration shows we need a new cut, the\n"
        "> fix is to amend `03-prepare` and re-run — never to build chart data here.\n"
        "\n"
        "**On the bump template:** the shared kit has no `bump` type yet — building it is\n"
        "*this project's* capability add, scheduled for `06-viz-social`. A bump is just a\n"
        "specialised line of **rank vs year**, so for exploration we draw the rank race with\n"
        "the existing shared **`line`** template: we plot an **inverted** rank (so rank 1\n"
        "sits at the TOP) by charting `(N+1 − rank)` and relabelling the y ticks back to\n"
        "`#rank`. The goal is to let the owner SEE and choose the framing, not to produce\n"
        "the final bump.\n"
        "\n"
        "The venv is Python 3.14 (matplotlib RecursionErrors), so every chart is rendered\n"
        "with the shared **Pillow factory** (`render_chart`) and displays **inline**."
    ),
    code(
        "import sys, os\n"
        "from pathlib import Path\n"
        "\n"
        "# Navigate to project root regardless of how the kernel was launched.\n"
        "PROJECT = Path.cwd()\n"
        "while not (PROJECT / 'config.yaml').exists() and PROJECT != PROJECT.parent:\n"
        "    PROJECT = PROJECT.parent\n"
        "os.chdir(PROJECT)\n"
        "sys.path.insert(0, str(PROJECT))\n"
        "sys.path.insert(0, str(PROJECT / '..' / '..' / 'shared'))\n"
        "\n"
        "import duckdb, pandas as pd\n"
        "pd.set_option('display.max_rows', 120)\n"
        "\n"
        "from src.ingest import load_config\n"
        "from colors import c, CATEGORICAL_10\n"
        "from chart_factory import render_chart\n"
        "\n"
        "cfg = load_config('config.yaml')\n"
        "# READ-ONLY: 04-viz only consumes 03's prepared tables.\n"
        "con = duckdb.connect(cfg['settings']['duckdb_file'], read_only=True)\n"
        "print('tables:', [r[0] for r in con.execute('SHOW TABLES').fetchall()])"
    ),
    # ----------------------------------------------------------------- helper
    md(
        "## Rank-bump helper (via the `line` template)\n"
        "\n"
        "A tiny helper that turns a long `(year, genre, rank)` frame into the wide,\n"
        "inverted-rank form the `line` template wants, then renders it. We pass the\n"
        "line template a `y_fmt` lambda so the axis still reads as `#1 … #N` even though\n"
        "the plotted value is `(N+1 − rank)`. One **genre = one line**, labelled at its\n"
        "last point. This is a stand-in for the real bump template coming in `06`."
    ),
    code(
        "def bump_from_long(df_long, rank_col='rank', x_col='year', genre_col='genre',\n"
        "                   genres=None, palette=None, title='', subtitle='', source=None,\n"
        "                   filename=None, x_tick_step=10):\n"
        "    \"\"\"Render a rank bump (rank 1 at top) from a long (x, genre, rank) frame\n"
        "    using the shared `line` template. Returns nothing; displays inline.\"\"\"\n"
        "    d = df_long.copy()\n"
        "    if genres is None:\n"
        "        genres = list(d[genre_col].unique())\n"
        "    d = d[d[genre_col].isin(genres)]\n"
        "    N = int(d[rank_col].max())\n"
        "    # Invert: rank 1 -> top. Plot (N+1 - rank).\n"
        "    d['_inv'] = (N + 1) - d[rank_col]\n"
        "    wide = d.pivot_table(index=x_col, columns=genre_col, values='_inv',\n"
        "                         aggfunc='mean').reset_index()\n"
        "    if palette is None:\n"
        "        palette = CATEGORICAL_10\n"
        "    # Order series by their most-recent rank so the legend/labels read sensibly.\n"
        "    last = d.sort_values(x_col).groupby(genre_col)[rank_col].last().sort_values()\n"
        "    ordered = [g for g in last.index if g in wide.columns]\n"
        "    series = [{'col': g, 'label': g, 'color': palette[i % len(palette)]}\n"
        "              for i, g in enumerate(ordered)]\n"
        "    render_chart({\n"
        "        'type': 'line',\n"
        "        'table': wide,\n"
        "        'x_col': x_col,\n"
        "        'series': series,\n"
        "        'y_fmt': (lambda v, _N=N: f'#{int(_N + 1 - round(v))}'),\n"
        "        'x_axis_label': '',  # year/decade ticks are self-evident (project standard)\n"
        "        'y_axis_label': 'Rank among set (1 = most chart appearances)',\n"
        "        'y_min': 0.5, 'y_max': N + 0.5,\n"
        "        'markers': True, 'label_last': True, 'legend': False,\n"
        "        'x_tick_step': x_tick_step,\n"
        "        'title': title, 'subtitle': subtitle, 'source': source,\n"
        "        'filename': filename,\n"
        "    })\n"
        "\n"
        "SRC = 'Billboard Hot 100 (chart history) \u00b7 genre via MusicBrainz \u00b7 @unwelcomedata'\n"
        "print('helper ready')"
    ),
    # ============================================================= DECISION 1
    md(
        "## ⭐ FINAL STORY — LOCKED 2026-10-15 (owner)\n"
        "\n"
        "The framing below is **settled**; the cells in this notebook are the record of what\n"
        "was explored, but the decisions are no longer open. The owner picked:\n"
        "\n"
        "1. **LEAD = annual genre rank BUMP** — grain = **year** (owner: *\"I prefer the bump\n"
        "   chart by year, not decade\"*), **top-6 real genres**, **start 1970** (*\"we don't\n"
        "   need pre-1970\"*), **Other/Unknown EXCLUDED** (*\"we don't need the chart with\n"
        "   other\"*). Rank re-densed within the top-6 for 1970+. Rendered for real in\n"
        "   `06-viz-social` with the kit's **new `bump` template**.\n"
        "2. **SUPPORT = genre-share stacked** — the 100%-stacked-by-decade part-of-whole\n"
        "   (owner: *\"Like the genre share stacked chart\"*). All 12 genres incl. Other/Unknown\n"
        "   (grey) so it's a faithful part-of-whole.\n"
        "3. **Metal cut KEPT, but NOT as a social chart** — it is the **default view of the\n"
        "   genre dropdown picker** only (owner: *\"the metal chart makes no sense by itself,\n"
        "   that is just for the drop down picker\"*). **No other `Other` genre is broken out**\n"
        "   (owner asked; answer = NO — only Reggae recurs and it lacks tag volume).\n"
        "4. **Two NEW song-level social charts** — pre-streaming vs streaming-era\n"
        "   longest-charting songs (see §5 below), split at the 2013 streaming break.\n"
        "5. **Genre selection = a Pages DROPDOWN PICKER, not social** (`docs/genres.html`,\n"
        "   built by `scripts/build_genre_pages.py`; all 12 genres, defaults to Metal).\n"
        "6. **New x-axis standard:** no \"Year\" title when the ticks are obviously years\n"
        "   (pass `x_axis_label=\"\"`). Applied throughout — including §2b below, which the\n"
        "   owner specifically flagged (*\"get rid of it on chart 2\"*).\n"
        "7. **2013 streaming series break** annotated on the year-axis charts (dashed\n"
        "   \"2013: streaming added\" marker) and caveated on the categorical/song charts.\n"
        "\n"
        "---\n"
        "## 1. `Other/Unknown` handling — why the lead EXCLUDES it (settled)\n"
        "\n"
        "`Other/Unknown` is **not a genre** — it is the coverage residual (unmatched\n"
        "artists + the long tail below the ≥ 20-appearance enrichment threshold). But it is\n"
        "big: the `03` sanity check showed it ranks **#1 in the 1950s, 1960s and 1990s**.\n"
        "That is exactly why the LEAD excludes it and starts at 1970. We keep all three\n"
        "exploratory cuts below as the record of how that call was reached:\n"
        "\n"
        "- **(a) top-6 real genres only** — clean 6-line race from `chart_genre_rank_top`.\n"
        "- **(b) include `Other/Unknown`** — 7 lines; shows how 'unknown' the early decades\n"
        "  are, but a dominant grey not-a-genre line crowds the top. Rejected for the lead.\n"
        "- **(c) top-6 real, 1970-start** — ✅ **THIS is the locked lead framing**: honest\n"
        "  AND clean, it just doesn't claim to rank genres in the thin-coverage 1958–69 era."
    ),
    md("### (a) Top-6 real genres only — the clean race (`chart_genre_rank_top`)"),
    code(
        "top6 = con.execute('SELECT * FROM chart_genre_rank_top ORDER BY year, rank').df()\n"
        "bump_from_long(\n"
        "    top6,\n"
        "    title='Genre rank on the Billboard Hot 100, by year',\n"
        "    subtitle='Top 6 genres by chart appearances; Other/Unknown excluded. Coverage is thin pre-1970.',\n"
        "    source=SRC, filename='explore_bump_top6_year',\n"
        ")"
    ),
    md(
        "### (b) Include `Other/Unknown` as its own line (7 lines, re-ranked within the set)\n"
        "Take the 6 real genres **plus** `Other/Unknown` from `chart_genre_by_year`, then\n"
        "re-rank *within those seven* each year (so it's a dense 1..7 race). The grey line\n"
        "is `Other/Unknown` — watch it dominate the early decades and fade as coverage\n"
        "improves."
    ),
    code(
        "seven = con.execute('''\n"
        "    WITH keep AS (\n"
        "        SELECT * FROM chart_genre_by_year\n"
        "        WHERE genre IN (SELECT DISTINCT genre FROM chart_genre_rank_top)\n"
        "           OR genre = 'Other/Unknown'\n"
        "    )\n"
        "    SELECT year, genre, appearances, share,\n"
        "           DENSE_RANK() OVER (PARTITION BY year ORDER BY appearances DESC) AS rank\n"
        "    FROM keep\n"
        "    ORDER BY year, rank\n"
        "''').df()\n"
        "# Palette: give Other/Unknown a flat grey so it reads as 'not a genre'.\n"
        "genres7 = seven.sort_values('year').groupby('genre')['rank'].last().sort_values().index.tolist()\n"
        "pal7 = []\n"
        "ci = 0\n"
        "for g in genres7:\n"
        "    if g == 'Other/Unknown':\n"
        "        pal7.append(c('gray'))\n"
        "    else:\n"
        "        pal7.append(CATEGORICAL_10[ci % len(CATEGORICAL_10)]); ci += 1\n"
        "bump_from_long(\n"
        "    seven, genres=genres7, palette=pal7,\n"
        "    title='Genre rank on the Billboard Hot 100, by year (with Other/Unknown)',\n"
        "    subtitle='Top 6 genres + Other/Unknown (grey), re-ranked within the set. Other/Unknown is a coverage residual, not a genre.',\n"
        "    source=SRC, filename='explore_bump_seven_year',\n"
        ")"
    ),
    md(
        "### (c) Top-6 real, **1970-start** — avoid the thin-coverage era\n"
        "Same six lines as (a), but only from 1970 on. Ranks are re-densed within the\n"
        "top-6 for the 1970+ window so the race reads cleanly where coverage is strong."
    ),
    code(
        "top6_1970 = con.execute('''\n"
        "    SELECT year, genre, appearances, share,\n"
        "           DENSE_RANK() OVER (PARTITION BY year ORDER BY appearances DESC) AS rank\n"
        "    FROM chart_genre_rank_top\n"
        "    WHERE year >= 1970\n"
        "    ORDER BY year, rank\n"
        "''').df()\n"
        "bump_from_long(\n"
        "    top6_1970,\n"
        "    title='Genre rank on the Billboard Hot 100, 1970\u2013present',\n"
        "    subtitle='Top 6 genres by chart appearances, from 1970 (when genre coverage is strong). Other/Unknown excluded.',\n"
        "    source=SRC, filename='explore_bump_top6_1970',\n"
        ")"
    ),
    md(
        "**Outcome (LOCKED).** (a) hides how little we know about the 1958–69 era; (b) puts\n"
        "a fat grey not-a-genre line on top for two decades (weak lead, invites 'what is\n"
        "Other?'); **(c) was chosen** — top-6 real genres, **1970-start**, Other excluded —\n"
        "the honest-and-clean cut that simply doesn't rank genres where coverage is too thin.\n"
        "This is the lead bump in `06-viz-social` (rendered with the new `bump` template)."
    ),
    # ============================================================= DECISION 2
    md(
        "## 2. Count/rank vs share\n"
        "\n"
        "The bump ranks genres by **appearances** (count). A rank-bump answers *who's on\n"
        "top*; it hides *by how much*. The alternative framing is **share of the Hot 100** —\n"
        "a line chart with share (%) on the y-axis — which answers *how much of the chart\n"
        "each genre actually held*. The two tell slightly different stories (a genre can be\n"
        "#1 by a hair, or #2 by a mile), so we show both."
    ),
    md(
        "### 2a. Confirm the rank bump matches the `rank` column\n"
        "Sanity check: the helper re-pivots from the `rank` column `03` already computed, so\n"
        "the top-6 bump IS the stored rank. Spot-check a couple of years."
    ),
    code(
        "chk = con.execute('''\n"
        "    SELECT year, genre, appearances, rank\n"
        "    FROM chart_genre_rank_top\n"
        "    WHERE year IN (1975, 1995, 2020)\n"
        "    ORDER BY year, rank\n"
        "''').df()\n"
        "display(chk)\n"
        "print('rank is a direct read of the 03 `rank` column \u2014 the bump plots it, does not recompute it.')"
    ),
    md(
        "### 2b. Share-of-Hot-100 lines (share %, not rank) — the 'how much' framing\n"
        "Same six genres, but y = **share of that year's chart slots**. Labels at the last\n"
        "point. This shows magnitude (e.g. the rise of Hip-Hop/Rap's actual share) that a\n"
        "rank bump flattens."
    ),
    code(
        "share6 = con.execute('SELECT * FROM chart_genre_rank_top ORDER BY year').df()\n"
        "genres6 = share6.sort_values('year').groupby('genre')['share'].last().sort_values(ascending=False).index.tolist()\n"
        "wide_share = share6.pivot_table(index='year', columns='genre', values='share', aggfunc='mean').reset_index()\n"
        "series_share = [{'col': g, 'label': g, 'color': CATEGORICAL_10[i % len(CATEGORICAL_10)]}\n"
        "                for i, g in enumerate(genres6)]\n"
        "render_chart({\n"
        "    'type': 'line',\n"
        "    'table': wide_share,\n"
        "    'x_col': 'year',\n"
        "    'series': series_share,\n"
        "    'x_axis_label': '',\n"
        "    'y_axis_label': 'Share of Hot 100 chart slots (%)',\n"
        "    'y_min': 0,\n"
        "    'markers': False, 'label_last': True, 'legend': False, 'x_tick_step': 10,\n"
        "    'title': 'Genre share of the Billboard Hot 100, by year',\n"
        "    'subtitle': 'Percent of each year\\'s chart slots held by the top 6 genres. Coverage thin pre-1970.',\n"
        "    'source': SRC,\n"
        "    'filename': 'explore_share_top6_year',\n"
        "})"
    ),
    md(
        "**Outcome (LOCKED).** Lead with the **rank bump**; the **genre-share stacked**\n"
        "chart is the supporting 'how much' part-of-whole (owner likes it). The share-LINES\n"
        "explored here informed that call but the SUPPORT chart that ships is the\n"
        "100%-stacked-by-decade view (§4b), not these lines."
    ),
    # ============================================================= DECISION 3
    md(
        "## 3. Year grain vs decade grain\n"
        "\n"
        "The annual bump (69 years) shows the real crossing *years* but is noisier; the\n"
        "decade bump (`chart_genre_by_decade`, restricted to the same top-6 and re-ranked)\n"
        "is a smooth arc that reads cleanly on a phone but loses the exact hand-off year.\n"
        "Show both."
    ),
    md("### 3a. Annual bump (same as 1a, repeated here for the grain comparison)"),
    code(
        "bump_from_long(\n"
        "    top6,\n"
        "    title='Genre rank on the Billboard Hot 100, by year (annual grain)',\n"
        "    subtitle='Top 6 genres; annual rank shows the exact crossing years. Coverage thin pre-1970.',\n"
        "    source=SRC, filename='explore_bump_top6_year_grain', x_tick_step=10,\n"
        ")"
    ),
    md("### 3b. Decade bump — smoother arc for social"),
    code(
        "dec6 = con.execute('''\n"
        "    WITH keep AS (\n"
        "        SELECT * FROM chart_genre_by_decade\n"
        "        WHERE genre IN (SELECT DISTINCT genre FROM chart_genre_rank_top)\n"
        "    )\n"
        "    SELECT decade, genre, appearances, share,\n"
        "           DENSE_RANK() OVER (PARTITION BY decade ORDER BY appearances DESC) AS rank\n"
        "    FROM keep\n"
        "    ORDER BY decade, rank\n"
        "''').df()\n"
        "bump_from_long(\n"
        "    dec6, x_col='decade',\n"
        "    title='Genre rank on the Billboard Hot 100, by decade',\n"
        "    subtitle='Top 6 genres by chart appearances, re-ranked within the set per decade.',\n"
        "    source=SRC, filename='explore_bump_top6_decade', x_tick_step=10,\n"
        ")"
    ),
    md(
        "**Outcome (LOCKED).** The owner chose **annual grain** (*\"I prefer the bump chart\n"
        "by year, not decade\"*). Annual shows the genuine crossing years — the whole appeal\n"
        "of a bump — at the cost of some wiggle; decade was NOT chosen. The decade cut here\n"
        "stays only as the exploratory record."
    ),
    # ============================================================= DECISION 4
    md(
        "## 4. Supporting cuts\n"
        "\n"
        "Two cheap context charts the owner asked for."
    ),
    md(
        "### 4a. Metal's trajectory (owner's personal interest) → PICKER DEFAULT, not social\n"
        "Metal is **not** in the top-6, so it won't appear in the main bump. The owner wants\n"
        "to SEE where it lands — peak **276 appearances in 2001** — but decided the Metal\n"
        "chart **makes no sense as a standalone social post** (*\"that is just for the drop\n"
        "down picker\"*). So Metal is **not a social chart**: it is the **default view of the\n"
        "genre dropdown picker** (`docs/genres.html`, built by `scripts/build_genre_pages.py`,\n"
        "which renders this same appearances-per-year line for all 12 genres). The cell below\n"
        "stays as the exploratory record / the shape the picker shows."
    ),
    code(
        "metal = con.execute('''\n"
        "    SELECT year, appearances, share, rank\n"
        "    FROM chart_genre_by_year WHERE genre = 'Metal' ORDER BY year\n"
        "''').df()\n"
        "peak = metal.loc[metal['appearances'].idxmax()]\n"
        "print(f\"Metal peak: {int(peak['appearances'])} appearances in {int(peak['year'])} \"\n"
        "      f\"(rank #{int(peak['rank'])} that year, {peak['share']}% of the chart)\")\n"
        "render_chart({\n"
        "    'type': 'line',\n"
        "    'table': metal,\n"
        "    'x_col': 'year',\n"
        "    'series': [{'col': 'appearances', 'label': 'Metal', 'color': c('brown_red')}],\n"
        "    'x_axis_label': '',\n"
        "    'y_axis_label': 'Hot 100 chart appearances',\n"
        "    'y_min': 0, 'markers': True, 'label_last': False, 'legend': False,\n"
        "    'value_labels': False, 'x_tick_step': 10,\n"
        "    'title': 'Metal on the Billboard Hot 100, by year',\n"
        "    'subtitle': 'Chart appearances per year. Metal sits just outside the top 6 (peak 276 in 2001).',\n"
        "    'source': SRC,\n"
        "    'filename': 'explore_metal_year',\n"
        "})"
    ),
    md(
        "### 4b. Genre share by decade — 100% stacked\n"
        "A part-of-whole view: each decade's chart slots split across genres. Uses the\n"
        "shared `stacked_100pct_bars` template on `chart_genre_by_decade` (all 12 genres,\n"
        "so `Other/Unknown` is visible as its own band — honest about coverage per decade)."
    ),
    code(
        "stacked = con.execute('''\n"
        "    SELECT decade, genre, share\n"
        "    FROM chart_genre_by_decade ORDER BY decade, genre\n"
        "''').df()\n"
        "wide_stacked = stacked.pivot_table(index='decade', columns='genre', values='share',\n"
        "                                   aggfunc='sum').fillna(0).reset_index()\n"
        "# group labels must be strings for the stacked template (e.g. '1950s').\n"
        "wide_stacked['decade'] = wide_stacked['decade'].astype(int).astype(str) + 's'\n"
        "genre_order = ['Rock', 'R&B/Soul', 'Pop', 'Country', 'Hip-Hop/Rap', 'Dance/Electronic',\n"
        "               'Latin', 'Folk', 'Jazz', 'Blues', 'Metal', 'Other/Unknown']\n"
        "genre_order = [g for g in genre_order if g in wide_stacked.columns]\n"
        "segments = [\n"
        "    {'col': g, 'label': g,\n"
        "     'color': (c('gray') if g == 'Other/Unknown' else CATEGORICAL_10[i % len(CATEGORICAL_10)])}\n"
        "    for i, g in enumerate(genre_order)\n"
        "]\n"
        "try:\n"
        "    render_chart({\n"
        "        'type': 'stacked_100pct_bars',\n"
        "        'table': wide_stacked,\n"
        "        'group_col': 'decade',\n"
        "        'segments': segments,\n"
        "        'show_legend': True,\n"
        "        'title': 'Genre share of the Billboard Hot 100, by decade',\n"
        "        'subtitle': 'Each decade\\'s chart slots split across genres (Other/Unknown in grey). Coverage thin in the 1950s\u201360s.',\n"
        "        'source': SRC,\n"
        "        'filename': 'explore_genre_share_stacked_decade',\n"
        "    })\n"
        "except Exception as e:\n"
        "    # The stacked template signature can vary; if it doesn't take this shape cheaply,\n"
        "    # fall back to a plain inline table rather than over-building (03 owns chart data).\n"
        "    print('stacked_100pct_bars did not take this shape cleanly:', e)\n"
        "    print('Falling back to the numeric share-by-decade matrix (explore via the share-lines above):')\n"
        "    display(wide_stacked.round(1))"
    ),
    md(
        "**Note.** This is the SUPPORT chart that ships (owner likes the genre-share\n"
        "stacked). Kept as all 12 genres incl. Other/Unknown (grey) so it's a faithful\n"
        "part-of-whole; the 2010s/20s decades reflect the post-2013 streaming formula\n"
        "(caveat in the social subtitle)."
    ),
    # ====================================================== SONG-LEVEL (06 charts 3&4)
    md(
        "## 5. Song-level — longest-charting songs, pre-streaming vs streaming era\n"
        "\n"
        "Added to the FINAL social set (2026-10-15): two song-grain charts contrasting the\n"
        "**longest-charting Hot 100 songs** before and after the **2013 streaming break**.\n"
        "`03-prepare` owns the shaped tables (`chart_songs_pre_streaming` /\n"
        "`chart_songs_streaming_era` — top-10 songs by total weeks on chart, split on first\n"
        "chart year 1958–2012 vs 2013–2026). `04` CONSUMES them to confirm the story; `06`\n"
        "renders them (ranked bars, song = label, artist = sublabel, bar color = genre,\n"
        "shared genre palette across both). Explored inline here so this notebook reflects\n"
        "what `06` ships.\n"
        "\n"
        "**The story (verified below):** streaming-era songs run **far longer** (top ~112\n"
        "weeks vs ~87 pre-streaming) and the **genre mix flips** from Pop/Rock/Country to\n"
        "R&B-Soul / Dance-Electronic / Pop (no Rock in the streaming top-10).\n"
        "\n"
        "**Caveat (kept, not hardened):** the streaming ramp bled into the late-2000s/early-\n"
        "2010s, so the pre-streaming top is dominated by 2008–2012 songs plus perennial\n"
        "Christmas songs — the split is at 2013 with a caveat line, not a hard wall."
    ),
    code(
        "song_pre = con.execute('SELECT song, artist, genre, weeks FROM chart_songs_pre_streaming ORDER BY weeks DESC, song').df()\n"
        "song_stream = con.execute('SELECT song, artist, genre, weeks FROM chart_songs_streaming_era ORDER BY weeks DESC, song').df()\n"
        "print('PRE-STREAMING (first year 1958-2012) — top by weeks on chart:')\n"
        "display(song_pre)\n"
        "print('STREAMING ERA (first year 2013-2026) — top by weeks on chart:')\n"
        "display(song_stream)\n"
        "print(f\"pre max weeks = {int(song_pre['weeks'].max())}  |  streaming max weeks = {int(song_stream['weeks'].max())}\")\n"
        "print('pre genres:   ', sorted(song_pre['genre'].unique()))\n"
        "print('stream genres:', sorted(song_stream['genre'].unique()))"
    ),
    md(
        "**Confirmed:** pre #1 = **Radioactive / Imagine Dragons (87 wks, Rock)**; streaming\n"
        "#1 = **Lose Control / Teddy Swims (112 wks, R&B/Soul)**. The genre sets differ (Rock\n"
        "present pre, absent streaming), confirming the mix flip. These are the two song\n"
        "charts built in `06-viz-social`; the single tall STACKED comparison of the two is\n"
        "the Pages/web object (not a social post)."
    ),
    # ============================================================= STATUS
    md(
        "## Status — FINAL story locked; `06-viz-social` BUILT\n"
        "\n"
        "All framing is **LOCKED (2026-10-15)** — see the banner at the top. The social set\n"
        "is **4 charts**: (1) annual genre rank **bump** (top-6, 1970+, no Other, 2013\n"
        "streaming vline, new `bump` template), (2) genre-**share** 100%-stacked by decade,\n"
        "(3) pre-streaming + (4) streaming-era longest-charting songs. **Metal** is the\n"
        "**genre picker default**, not a social chart. Genre selection is a **Pages dropdown\n"
        "picker** (`docs/genres.html`). All year-axis charts drop the \"Year\" title; the\n"
        "**2013 streaming break** is annotated/caveated and documented in SOURCES.md +\n"
        "`_sources`. `06-viz-social` and the picker are built; this notebook reflects the\n"
        "shipped story."
    ),
    md("---\n## Cleanup\nClose the read-only DuckDB connection (single-writer lock)."),
    code("con.close()\nprint('connection closed')"),
]

nb = nbf.v4.new_notebook()
nb.cells = cells
nb.metadata = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.14"},
}
OUT.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, OUT)
print(f"wrote {OUT}")
