#!/usr/bin/env python
"""Build notebooks/06-viz-social.ipynb via nbformat — publication social + web renders.

billboard-hot100 FINAL CHART LAYOUT (owner LOCKED 2026-10-15):

  SOCIAL posts (full chrome, twitter_landscape 1600x900):
    1. LEAD   — genre rank BUMP, DECADE grain (clean at phone size). 2013 streaming marker at
                the 2010s point. The kit's NEW `bump` template (this project's capability deliverable).
    2. SUPPORT— genre-share 100% stacked by decade (streaming-era caveat in subtitle).
    3+4.      — pre-streaming + streaming-era longest-charting songs, posted TOGETHER as ONE
                two-image post (owner Option B: two full-size charts, not a cramped single image).

  WEB / Pages ONLY (no social post):
    01 bump ANNUAL grain (detailed; rendered here but web-only, 1664x936, web_mode).
    05 side-by-side song comparison — FULL CHROME (title + subtitle/caveat + source footer),
       NOT web_mode. Web-only = no social post, not stripped chrome (owner 2026-10-15).

  HOMEPAGE shows BOTH bump grains (decade + annual) + 02 + 03 + 04 + 05.

⭐ ONE canonical GENRE_COLORS map (pinned to the lead decade bump's assignments) colors EVERY
genre-encoded chart — bump, stacked, both song charts, side-by-side — so a genre is the same
color everywhere (owner: "follow the colors assigned in the lead decade chart").

Metal is NOT a social chart — it is only the DEFAULT view of the genre dropdown picker
(scripts/build_genre_pages.py -> docs/genres.html).

A direct-builder helper is used because render_chart() only exports to outputs/social; the web
target is built via the factory builder fn and saved to outputs/web manually.

    .venv/bin/python scripts/_build_nb_06_viz_social.py
    .venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/06-viz-social.ipynb
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

PROJECT = Path(__file__).resolve().parents[1]
NB_PATH = PROJECT / "notebooks" / "06-viz-social.ipynb"


def md(text: str):
    return new_markdown_cell(text.strip("\n"))


def code(text: str):
    return new_code_cell(text.strip("\n"))


cells = [
    md(
        """
# 06 — Viz (social + web) · billboard-hot100

Publication-ready renders of the **4 owner-approved** charts (FINAL SET locked 2026-10-15).
Each is rendered **twice** from the same base config (the workspace two-target system):
- **social** — `twitter_landscape` 1600×900, full chrome (title, subtitle, source,
  `@unwelcomedata` watermark) → `outputs/social/`.
- **web** — `web` preset 1664×936, `web_mode=True` (drops title/subtitle/source, keeps the
  watermark, hands the freed space to the data) → `outputs/web/`.

**The social set — how music genres moved at the top of the Hot 100, four ways:**
- **01** — genre rank **BUMP**, top-6 real genres, 1970→present (LEAD). The kit's **first `bump`
  template** — this project's capability deliverable. **DECADE grain on social (clean arc),
  ANNUAL grain on the web page (detailed).**
- **02** — genre-**share** 100% stacked by decade (SUPPORT — the "how much" part-of-whole).
- **03** — **pre-streaming** longest-charting songs (top-10, first chart year 1958–2012).
- **04** — **streaming-era** longest-charting songs (top-10, first chart year 2013–2026).

**Owner framing decisions (LOCKED 2026-10-15 — not re-litigated here):** annual grain for the
bump ("I prefer the bump chart by year, not decade"), **1970 start** ("we don't need pre-1970"),
**Other/Unknown excluded** from the lead ("we don't need the chart with other"), **no "Year"
x-axis title** when the ticks are obviously years. The standalone **Metal** chart is NOT social
— it's only the default view of the genre **dropdown picker** (`docs/genres.html`, built by
`scripts/build_genre_pages.py`).

**Methodology / series break (annotated, documented):** the Hot 100 ranks a **blended** metric
(sales + radio airplay + streaming). The load-bearing break is **2013**, when on-demand/YouTube
streaming was folded into the formula (further video/bundle changes ~2018–2020). The post-2013
Hip-Hop/Rap + Pop surge — and the much longer chart runs — are **partly real and partly a
streaming-weighting artifact**, so the year-axis charts carry a dashed **"2013: streaming added"**
marker and the song charts carry a short streaming-ramp caveat. See SOURCES.md + the `_sources`
table.

All charts route through the shared **Pillow factory** (matplotlib RecursionErrors on this
Python 3.14 venv). This notebook **CONSUMES** the `chart_*` tables `03-prepare` built (opened
read-only); it does not build chart data.
        """
    ),
    code(
        """
import sys, os
from pathlib import Path

PROJECT_ROOT = Path.cwd() if (Path.cwd() / "config.yaml").exists() else Path.cwd().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent.parent / "shared"))
os.chdir(PROJECT_ROOT)

import duckdb
import pandas as pd
from PIL import Image
from IPython.display import display
from colors import c, CATEGORICAL_10
import chart_factory as cf

con = duckdb.connect(str(PROJECT_ROOT / "data" / "project.duckdb"), read_only=True)

SOCIAL = PROJECT_ROOT / "outputs" / "social"
WEB = PROJECT_ROOT / "outputs" / "web"
SOCIAL.mkdir(parents=True, exist_ok=True)
WEB.mkdir(parents=True, exist_ok=True)

# NOTE: do NOT append "· @unwelcomedata" here — the footer (_draw_footer) stamps the
# @unwelcomedata brand watermark on the right automatically, so including it in the
# source string too duplicates the watermark on social charts.
SRC = "Billboard Hot 100 (chart history) · genre via MusicBrainz"

# ⭐ ONE canonical genre->color map used by EVERY chart (owner 2026-10-15: "follow the
# colors assigned in the lead decade chart"). The 6 lead-bump genres are PINNED to the
# exact colors the lead bump assigns (CATEGORICAL_10 ordered by total chart appearances,
# computed from chart_genre_rank_top 1970+). The remaining genres (which only appear in
# the 02 stacked chart) extend from the rest of the palette; Other/Unknown stays grey.
# Any chart that colors by genre MUST read from GENRE_COLORS so a genre is the same color
# everywhere (bump, stacked, both song charts, the side-by-side).
GENRE_COLORS = {
    "Rock":             "#003049",
    "Pop":              "#0A9396",
    "R&B/Soul":         "#BB3E03",
    "Hip-Hop/Rap":      "#94D2BD",
    "Country":          "#EE9B00",
    "Dance/Electronic": "#CA6702",
    # remaining genres (02 stacked only) — rest of CATEGORICAL_10 + brand extras:
    "Blues":            "#9B2226",
    "Folk":             "#005F73",
    "Jazz":             "#F5D47D",
    "Latin":            "#5A2A82",
    "Metal":            "#AE2012",
    "Other/Unknown":    c("gray"),
}

def genre_color(g):
    \"\"\"Canonical color for a genre; falls back to grey for anything unmapped.\"\"\"
    return GENRE_COLORS.get(g, c("gray"))


def render_dual(base_config, filename):
    \"\"\"Render one chart to BOTH social and web from a single base config.

    social = twitter_landscape + full chrome; web = web preset + web_mode (no
    title/subtitle/source). Builds via the factory builder fn directly so we can
    target two output dirs. Displays the social version inline.
    \"\"\"
    ctype = base_config["type"]
    builder = cf._CHART_TYPES[ctype]

    social_cfg = {**base_config, "preset": "twitter_landscape", "web_mode": False}
    img_social = builder(social_cfg, con)
    p_social = SOCIAL / f"{filename}.png"
    img_social.save(p_social)

    web_cfg = {**base_config, "preset": "web", "web_mode": True,
               "title": "", "subtitle": None, "source": None}
    img_web = builder(web_cfg, con)
    p_web = WEB / f"{filename}.png"
    img_web.save(p_web)

    print(f"{filename}: social {img_social.size} -> {p_social.name} | web {img_web.size} -> {p_web.name}")
    display(img_social)
    return p_social, p_web

print("ready")
        """
    ),
    # ===================================================================== CHART 1
    md(
        """
## 01 — Genre rank bump, 1970–present (LEAD) — TWO GRAINS

The rank race at the top of the Hot 100: each of the **top-6 genres by chart appearances**
(Rock, R&B/Soul, Pop, Country, Hip-Hop/Rap, Dance/Electronic) tracked by its rank, rank **#1 at
the top**. Rock leads the early years; **Hip-Hop/Rap climbs to #1 by the mid-1990s** and holds it.
This is the project's capability deliverable — the kit's **first `bump` template**.

**⭐ TWO GRAIN VERSIONS (owner 2026-10-15):** the annual bump is dense/noisy at phone size, so the
**social post uses the DECADE grain** (clean arc) while the **Pages/web page keeps the ANNUAL
(by-year) grain** (the detailed version for study). This is the one chart where the social and web
renders differ by *grain* — so we do NOT use `render_dual`; we render the decade bump to
`outputs/social/01_genre_rank_bump.png` and the annual bump to `outputs/web/01_genre_rank_bump.png`
explicitly.

**Framing (LOCKED 2026-10-15):** **start 1970** (pre-1970 genre coverage is too thin to rank);
**Other/Unknown excluded** (coverage residual, not a genre); rank **re-densed within the top-6**.
**No "Year"/"Decade" x-axis title** (the ticks are self-evident — the project standard).

**2013 streaming marker:** the dashed line flags where on-demand streaming entered the Hot 100
formula. On the **annual (web)** bump it sits at x=2013. On the **decade (social)** bump the x axis
is decades (1970s…2020s), so the marker is placed at the **2010s** point with the same label; the
2010s is the decade the streaming formula took hold.

> Edge case handled by the template: on the annual grain Hip-Hop/Rap is **absent in 1975–1978**
> (only 5 ranked genres those years), so its line is drawn only across the years it actually ranks.
        """
    ),
    code(
        """
# --- top-6 genres (annual table drives the ordering; colors come from the canonical map) ---
df_bump_year = con.execute('''
    SELECT year, genre, appearances,
           DENSE_RANK() OVER (PARTITION BY year ORDER BY appearances DESC) AS rank
    FROM chart_genre_rank_top
    WHERE year >= 1970
    ORDER BY year, rank
''').df()
_order = (df_bump_year.groupby('genre')['appearances'].sum()
          .sort_values(ascending=False).index.tolist())
# Canonical colors (GENRE_COLORS was defined FROM these lead-bump assignments).
series_bump = [{"key": g, "label": g, "color": genre_color(g)} for g in _order]

# --- DECADE grain (SOCIAL): re-dense the same top-6 within each decade, 1970s on ---
df_bump_decade = con.execute('''
    WITH keep AS (
        SELECT decade, genre, appearances
        FROM chart_genre_by_decade
        WHERE genre IN (SELECT DISTINCT genre FROM chart_genre_rank_top)
          AND decade >= 1970
    )
    SELECT decade, genre, appearances,
           DENSE_RANK() OVER (PARTITION BY decade ORDER BY appearances DESC) AS rank
    FROM keep
    ORDER BY decade, rank
''').df()

builder_bump = cf._CHART_TYPES["bump"]

# SOCIAL = decade grain, full chrome, twitter_landscape.
social_bump_cfg = {
    "type": "bump", "preset": "twitter_landscape", "web_mode": False,
    "table": df_bump_decade,
    "x_col": "decade", "series_col": "genre", "rank_col": "rank",
    "series": series_bump,
    "x_axis_label": "",          # decade ticks are self-evident -> no axis title
    "x_tick_step": 10,
    "vlines": [{"x": 2010, "label": "2013: streaming added", "dash": True}],
    "title": "Genre rank on the Billboard Hot 100, by decade",
    "subtitle": "Rank of the top 6 genres by chart appearances, per decade · genre via MusicBrainz · rank #1 = most Hot 100 slots",
    "source": SRC,
}
img_social_bump = builder_bump(social_bump_cfg, con)
img_social_bump.save(SOCIAL / "01_genre_rank_bump.png")

# WEB = annual grain, web_mode (no chrome), web preset.
web_bump_cfg = {
    "type": "bump", "preset": "web", "web_mode": True,
    "table": df_bump_year,
    "x_col": "year", "series_col": "genre", "rank_col": "rank",
    "series": series_bump,
    "x_axis_label": "",
    "x_tick_step": 10,
    "vlines": [{"x": 2013, "label": "2013: streaming added", "dash": True}],
    "title": "", "subtitle": None, "source": None,
}
img_web_bump = builder_bump(web_bump_cfg, con)
img_web_bump.save(WEB / "01_genre_rank_bump.png")

print(f"01 bump: social DECADE {img_social_bump.size} | web ANNUAL {img_web_bump.size}")
display(img_social_bump)
        """
    ),
    # ===================================================================== CHART 2
    md(
        """
## 02 — Genre share of the Hot 100, by decade (SUPPORT)

The "how much" companion to the rank bump: each decade's chart slots split across genres as a
**100% stacked bar** — a faithful **part-of-whole**. Where the bump shows *who's on top*, this
shows *by how much*, and makes the **Rock "mountain" (~1970s–80s)** and the **Hip-Hop/Rap surge
(2010s–20s)** read as area.

**Genre handling (choice stated):** unlike the lead, this chart keeps **all 12 genres including
Other/Unknown** (drawn in grey). That is deliberate — a part-of-whole must sum to 100%, so hiding
the coverage residual would misrepresent the early decades (where Other/Unknown is large). Showing
it in grey is the honest choice and labels it as "not a genre" visually. Shares are each decade's
true share of all chart slots (they already sum to 100 in `chart_genre_by_decade`).

**Streaming-era caveat:** the x-axis here is a **categorical decade** axis, so no 2013 vline is
forced. Instead: the **2010s/2020s decades reflect the post-2013 streaming formula** (streaming
reshaped the genre mix) — noted in the subtitle.
        """
    ),
    code(
        """
stacked = con.execute('''
    SELECT decade, genre, share
    FROM chart_genre_by_decade ORDER BY decade, genre
''').df()
wide_stacked = (stacked.pivot_table(index='decade', columns='genre', values='share', aggfunc='sum')
                .fillna(0).reset_index())
wide_stacked['decade'] = wide_stacked['decade'].astype(int).astype(str) + 's'

# Genre order (dominant real genres first; Other/Unknown last, grey).
genre_order = ['Rock', 'R&B/Soul', 'Pop', 'Country', 'Hip-Hop/Rap', 'Dance/Electronic',
               'Latin', 'Folk', 'Jazz', 'Blues', 'Metal', 'Other/Unknown']
genre_order = [g for g in genre_order if g in wide_stacked.columns]
segments = [
    {"col": g, "label": g, "color": genre_color(g)}  # canonical palette (lead-bump colors)
    for g in genre_order
]

render_dual({
    "type": "stacked_100pct_bars",
    "table": wide_stacked,
    "group_col": "decade",
    "segments": segments,
    "show_legend": True,
    "title": "Genre share of the Billboard Hot 100, by decade",
    "subtitle": "Each decade’s chart slots split across genres (Other/Unknown = coverage residual, grey) · 2010s–20s reflect the post-2013 streaming formula",
    "source": SRC,
}, "02_genre_share_by_decade")
        """
    ),
    # ===================================================================== songs setup
    md(
        """
## 03 & 04 — Longest-charting songs, pre-streaming vs streaming era

Two song-grain charts (top-10 Hot 100 songs by **total weeks on chart**), split at the **2013
streaming break**: chart 03 = first chart year **1958–2012** (pre-streaming), chart 04 = first
chart year **2013–2026** (streaming era). Shaped tables come from `03-prepare`
(`chart_songs_pre_streaming` / `chart_songs_streaming_era`); this notebook only renders them.

Each bar is a **song** (title as the label, **artist as the muted sublabel**), **colored by
genre** with a shared genre legend. The genre→color map is built **once over the union of genres
in both top-10s** so a genre is the **same color in both charts** — and in the chart-05 web
side-by-side below.

**Streaming-ramp caveat (owner wants this; split kept at 2013, not hardened):** the streaming
ramp bled into the **late-2000s/early-2010s**, so the pre-streaming top is dominated by 2008–2012
songs plus perennial Christmas songs. The real contrast still holds: **pre max ~87 weeks vs
streaming-era 112**, and the genre mix flips from **Pop / Rock / Country** toward **R&B-Soul /
Dance-Electronic / Pop** (no Rock in the streaming top-10).
        """
    ),
    code(
        """
df_pre = con.execute(
    "SELECT song, artist, genre, weeks FROM chart_songs_pre_streaming ORDER BY weeks DESC, song"
).df()
df_stream = con.execute(
    "SELECT song, artist, genre, weeks FROM chart_songs_streaming_era ORDER BY weeks DESC, song"
).df()

# Colors come from the ONE canonical GENRE_COLORS map (so a genre is the same color
# in the bump, the stacked chart, both song charts, and the side-by-side).
union_genres = sorted(set(df_pre['genre']) | set(df_stream['genre']))

def prep_song_df(df):
    d = df.copy()
    d['bar_color'] = d['genre'].map(genre_color)
    d['weeks_label'] = d['weeks'].astype(int).astype(str) + ' wks'
    return d

df_pre_r = prep_song_df(df_pre)
df_stream_r = prep_song_df(df_stream)

# Shared legend = only the genres that actually appear, in a stable order, canonical colors.
song_legend = [{"label": g, "color": genre_color(g)} for g in union_genres]
print("song genres (canonical colors):", {g: genre_color(g) for g in union_genres})
print("pre top:", df_pre_r.iloc[0]['song'], df_pre_r.iloc[0]['weeks'], "| stream top:",
      df_stream_r.iloc[0]['song'], df_stream_r.iloc[0]['weeks'])
        """
    ),
    # ===================================================================== CHART 3
    md(
        """
### 03 — Pre-streaming longest-charting songs (1958–2012)

Top-10 by total weeks on chart, first chart year 1958–2012. **Radioactive (Imagine Dragons, Rock)
at 87 weeks** leads — but note how many entries are 2008–2012 songs or perennial Christmas songs,
the streaming ramp already bleeding in.
        """
    ),
    code(
        """
render_dual({
    "type": "single_ranked_bars",
    "table": df_pre_r,
    "category_col": "song",
    "value_col": "weeks",
    "label_col": "weeks_label",
    "sublabel_col": "artist",
    "color_col": "bar_color",
    "legend": song_legend,
    "sort": "desc",
    "title": "Longest-charting Hot 100 songs, 1958–2012 (pre-streaming)",
    "subtitle": "Total weeks on the Billboard Hot 100 · bar color = genre · the streaming ramp bled into 2008–12 (perennial Christmas songs rank high)",
    "source": SRC,
}, "03_longest_charting_pre_streaming")
        """
    ),
    # ===================================================================== CHART 4
    md(
        """
### 04 — Streaming-era longest-charting songs (2013–2026)

Top-10 by total weeks on chart, first chart year 2013–2026. **Lose Control (Teddy Swims, R&B/Soul)
at 112 weeks** leads — longer runs than any pre-streaming song, and the genre mix flips to
**R&B/Soul, Dance/Electronic, Pop, Country** (no Rock). Same genre colors as chart 03.
        """
    ),
    code(
        """
render_dual({
    "type": "single_ranked_bars",
    "table": df_stream_r,
    "category_col": "song",
    "value_col": "weeks",
    "label_col": "weeks_label",
    "sublabel_col": "artist",
    "color_col": "bar_color",
    "legend": song_legend,
    "sort": "desc",
    "title": "Longest-charting Hot 100 songs, 2013–2026 (streaming era)",
    "subtitle": "Total weeks on the Billboard Hot 100 · bar color = genre · streaming-era songs run far longer (up to 112 weeks) and the genre mix flips",
    "source": SRC,
}, "04_longest_charting_streaming_era")
        """
    ),
    # ===================================================================== web side-by-side combo
    md(
        """
### 05 — Web comparison: a TRUE side-by-side (Pages/web object)

For the Pages site the pre/post song comparison reads best as **one true side-by-side** — the two
eras as left/right panels on a **shared x-scale**, so the reader sees the contrast (pre max ~87 →
streaming-era 112 weeks, and the genre-mix flip) in a single honest glance. This replaces the old
hand-stacked two-panel canvas with the extended shared **`side_by_side_bars`** template (same one
the abortion project uses), now carrying the additive **per-row `color_col`** (bar colored by
genre), **`sublabel_col`** (artist under each song title), and a shared genre **`legend`** — the
exact flexible-side-by-side the owner asked for. The two SEPARATE charts 03 & 04 above are the
SOCIAL objects — posted TOGETHER as one **two-image post** (owner Option B). THIS side-by-side is
the WEB/Pages object (`outputs/web/` only, no social post), rendered at the web canvas (1664-wide)
**with FULL CHROME** — title + subtitle (carrying the caveat) + source footer. "Web-only" here
means it isn't posted to social, NOT that its chrome is stripped (owner 2026-10-15).

Both panels read `bar_color` (canonical `GENRE_COLORS`) and share the one genre `legend`, so a
genre is the same color left and right — and matches charts 01–04. The shared x-scale is already
how the template works — the streaming-era bars sit visibly longer (up to 112 wks) vs pre ~87.
        """
    ),
    code(
        """
# TRUE side-by-side via the extended shared side_by_side_bars template (web/Pages object).
# left = pre-streaming top-10, right = streaming-era top-10; shared x-scale; per-row genre
# color (color_col) + artist sublabel (sublabel_col) + the one shared genre legend.
# ⭐ FULL CHROME (owner 2026-10-15): web-only means "no social POST", NOT "stripped chrome" —
# this chart keeps its title + subtitle (caveat) + source footer, so web_mode=False.
builder_sbs = cf._CHART_TYPES["side_by_side_bars"]

sbs_cfg = {
    "type": "side_by_side_bars",
    "preset": "web", "web_mode": False,
    "table_left": df_pre_r, "table_right": df_stream_r,
    "category_col": "song", "value_col": "weeks", "label_col": "weeks_label",
    "left_title": "1958–2012 (pre-streaming)", "right_title": "2013–2026 (streaming era)",
    "color_col": "bar_color", "sublabel_col": "artist", "legend": song_legend,
    "title": "Longest-charting Hot 100 songs: before vs during the streaming era",
    "subtitle": "Total weeks on the Billboard Hot 100 · bar color = genre · streaming-era songs run far longer (up to 112 vs ~87 weeks) and the genre mix flips · the streaming ramp bled into 2008–12",
    "source": SRC,
}
combo = builder_sbs(sbs_cfg, con)
p_combo = WEB / "05_longest_charting_comparison.png"
combo.save(p_combo)
print(f"05_longest_charting_comparison (web/Pages, full chrome side-by-side): {combo.size} -> {p_combo.name}")
display(combo)
        """
    ),
    # ===================================================================== picker note
    md(
        """
## Genre dropdown picker (Pages, NOT social)

The owner asked for genre selection as a **dropdown on the GitHub Pages site, not a social post**
("Maybe make that one a drop down on the github page for genre selection, not posted to social").
A separate script — **`scripts/build_genre_pages.py`** — renders one web-mode per-genre line
chart (**appearances over time, 1970+**) for **all 12 genres** (Blues, Country, Dance/Electronic,
Folk, Hip-Hop/Rap, Jazz, Latin, **Metal**, Other/Unknown, Pop, R&B/Soul, Rock) into
`docs/genres/`, plus a `docs/genres.html` `<select>` that swaps the `<img>` (same pattern as the
presidential-speeches and countries-income-disparity pickers). It **defaults to Metal** — the
owner's genre, which is why the standalone Metal chart was dropped from the social set and lives
here instead. The `docs/genres/` PNGs + `docs/genres.html` are regenerable, so they are gitignored
(curated into the release branch later). Run it with
`.venv/bin/python scripts/build_genre_pages.py`.
        """
    ),
    md("## Cleanup"),
    code(
        """
con.close()
print("connection closed — 4 social charts + web comparison rendered")
        """
    ),
]

nb = new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nb.metadata["language_info"] = {"name": "python", "version": "3.14"}

NB_PATH.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, NB_PATH)
print(f"wrote {NB_PATH.relative_to(PROJECT)}  ({len(cells)} cells)")
