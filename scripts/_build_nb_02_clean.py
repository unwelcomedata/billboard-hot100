#!/usr/bin/env python
"""Build notebooks/02-clean.ipynb from source (nbformat).

Regenerate with:  .venv/bin/python scripts/_build_nb_02_clean.py
Then execute with: .venv/bin/python -m nbconvert --to notebook \
    --execute --inplace notebooks/02-clean.ipynb

The venv is Python 3.14 — notebooks are generated here and executed via nbconvert.
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "notebooks" / "02-clean.ipynb"


def md(src: str):
    return nbf.v4.new_markdown_cell(src)


def code(src: str):
    return nbf.v4.new_code_cell(src)


cells = [
    md(
        "# 02 — Clean\n"
        "\n"
        "**billboard-hot100** — clean the two raw ingest tables into the typed building\n"
        "blocks that `03-prepare` will shape into the genre-rank-over-time chart data.\n"
        "All cleaning happens in **DuckDB SQL** (no pandas chained transforms).\n"
        "\n"
        "This stage produces exactly two interim tables — **nothing is joined or\n"
        "aggregated across them here** (that is `03-prepare`'s job):\n"
        "\n"
        "1. **`hot100_clean`** — the ~355k chart appearances, typed and deduped, with\n"
        "   `year`/`decade` derived and `this_week` renamed to `rank`.\n"
        "2. **`artist_genre`** — one row per enriched artist, mapping the messy raw\n"
        "   MusicBrainz tags to ONE aggregate genre via a documented precedence ruleset\n"
        "   (`src/clean_quality.bucket_genre`).\n"
        "\n"
        "> ⏳ **Partial coverage, by design.** The MusicBrainz genre pull is still filling\n"
        "> `data/raw/mb_artist_cache.jsonl` toward the full ~4,427-artist target. The\n"
        "> cleaning logic is built NOW on partial coverage and is INDEPENDENT of how many\n"
        "> artists are genred: artists not yet cached (or with no genre tags) bucket to\n"
        "> **Other/Unknown**. Re-running after the pull completes changes only the\n"
        "> Other/Unknown share — never the mapping."
    ),
    code(
        "import sys, os, json\n"
        "from pathlib import Path\n"
        "\n"
        "# Navigate to project root regardless of how the kernel was launched\n"
        "PROJECT = Path.cwd()\n"
        "while not (PROJECT / 'config.yaml').exists() and PROJECT != PROJECT.parent:\n"
        "    PROJECT = PROJECT.parent\n"
        "os.chdir(PROJECT)\n"
        "sys.path.insert(0, str(PROJECT))\n"
        "\n"
        "import pandas as pd\n"
        "pd.set_option('display.max_colwidth', 80)\n"
        "\n"
        "from src.ingest import load_config\n"
        "from src.clean_quality import (\n"
        "    get_connection, run_sql, quality_report, save_interim, register_source,\n"
        "    bucket_genre, genre_fields, AGGREGATE_GENRES,\n"
        ")\n"
        "\n"
        "cfg = load_config('config.yaml')\n"
        "con = get_connection(cfg)\n"
        "print('hot100_raw          :', con.execute('SELECT COUNT(*) FROM hot100_raw').fetchone()[0], 'rows')\n"
        "print('mb_artist_genres_raw:', con.execute('SELECT COUNT(*) FROM mb_artist_genres_raw').fetchone()[0], 'rows')\n"
        "print('  matched           :', con.execute('SELECT COUNT(*) FROM mb_artist_genres_raw WHERE matched').fetchone()[0])"
    ),
    # ================================================================ step 1
    md(
        "## Step 1 — clean the chart appearances → `hot100_clean`\n"
        "\n"
        "From `hot100_raw` (one row per weekly chart appearance). In DuckDB SQL we:\n"
        "- Cast `date` → DATE and derive `year` (INT) and `decade` (INT, the decade's\n"
        "  first year, `FLOOR(year/10)*10`).\n"
        "- Trim/collapse whitespace in `song` and `artist`. We KEEP the untouched\n"
        "  artist string as **`artist_raw`** — the genre join in `03-prepare` keys on the\n"
        "  exact Billboard spelling, so the join key must survive cleaning verbatim.\n"
        "- Rename `this_week` → **`rank`** (the chart position that week; clearer than the\n"
        "  source's column name) and keep `last_week`, `peak_position`, `weeks_on_chart`.\n"
        "\n"
        "No genre, no aggregation — just a typed, trimmed copy of the appearances."
    ),
    code(
        "clean = run_sql('''\n"
        "    SELECT\n"
        "        CAST(date AS DATE)                           AS date,\n"
        "        CAST(YEAR(CAST(date AS DATE)) AS INTEGER)    AS year,\n"
        "        CAST(FLOOR(YEAR(CAST(date AS DATE)) / 10) * 10 AS INTEGER) AS decade,\n"
        "        REGEXP_REPLACE(TRIM(song),   '\\\\s+', ' ', 'g') AS song,\n"
        "        REGEXP_REPLACE(TRIM(artist), '\\\\s+', ' ', 'g') AS artist,\n"
        "        artist                                       AS artist_raw,\n"
        "        CAST(this_week      AS INTEGER)              AS rank,\n"
        "        CAST(last_week      AS INTEGER)              AS last_week,\n"
        "        CAST(peak_position  AS INTEGER)              AS peak_position,\n"
        "        CAST(weeks_on_chart AS INTEGER)              AS weeks_on_chart\n"
        "    FROM hot100_raw\n"
        "''', con)\n"
        "print('typed rows:', f'{len(clean):,}')\n"
        "clean.head(5)"
    ),
    md(
        "### Dedupe exact-duplicate (date, song, artist) appearances\n"
        "A song can only occupy one position on a given weekly chart, so any exact\n"
        "`(date, song, artist)` duplicate is a source artifact. We report how many we drop."
    ),
    code(
        "before = len(clean)\n"
        "clean = clean.drop_duplicates(subset=['date', 'song', 'artist']).reset_index(drop=True)\n"
        "dropped = before - len(clean)\n"
        "print(f'dropped {dropped:,} exact (date, song, artist) duplicate(s)')\n"
        "print(f'rows now: {len(clean):,}')"
    ),
    md(
        "### QC — assert the invariants, then a quality report\n"
        "`rank` must be 1–100; `date`, `song`, `artist` must be non-null. The\n"
        "`quality_report()` helper prints null counts, row count and duplicate count."
    ),
    code(
        "# Hard invariants (fail loudly if the source drifts)\n"
        "assert clean['rank'].between(1, 100).all(), 'rank outside 1..100'\n"
        "assert clean['date'].notna().all(),   'null date'\n"
        "assert clean['song'].notna().all(),   'null song'\n"
        "assert clean['artist'].notna().all(), 'null artist'\n"
        "assert (clean['artist'].str.len() > 0).all(), 'empty artist string'\n"
        "print('✓ invariants hold: rank 1-100, no null/empty date/song/artist')\n"
        "\n"
        "print(f'\\ndate range     : {clean[\"date\"].min()} → {clean[\"date\"].max()}')\n"
        "print(f'distinct artists: {clean[\"artist\"].nunique():,}')\n"
        "print(f'distinct songs  : {clean[\"song\"].nunique():,}')\n"
        "print(f'years           : {int(clean[\"year\"].min())} → {int(clean[\"year\"].max())}')\n"
        "print(f'decades         : {sorted(clean[\"decade\"].unique().tolist())}')\n"
        "\n"
        "quality_report(clean, 'hot100_clean', con,\n"
        "               required_columns=['date', 'year', 'decade', 'song', 'artist', 'rank'])"
    ),
    md("### Save `hot100_clean` (DuckDB table + interim Parquet)"),
    code(
        "con.execute('DROP TABLE IF EXISTS hot100_clean')\n"
        "con.execute('CREATE TABLE hot100_clean AS SELECT * FROM clean')\n"
        "save_interim(clean, cfg, 'hot100_clean.parquet')\n"
        "print('hot100_clean:', con.execute('SELECT COUNT(*) FROM hot100_clean').fetchone()[0], 'rows')"
    ),
    # ================================================================ step 2
    md(
        "## Step 2 — the genre bucketer → `artist_genre` (THE key deliverable)\n"
        "\n"
        "Billboard has no genre; `mb_artist_genres_raw` carries messy artist-level\n"
        "MusicBrainz tags (a JSON-string `tags` column of `{name, count}` objects). We\n"
        "collapse that tag soup to ONE **aggregate genre** per artist with a deterministic,\n"
        "documented ruleset in `src/clean_quality.py` — the mapping is the real deliverable,\n"
        "and it does NOT depend on which artists happen to be cached yet.\n"
        "\n"
        "**Canonical aggregate-genre set** (the only values the bucketer can return):\n"
        "> " + ", ".join(
            ["Pop", "Rock", "Hip-Hop/Rap", "R&B/Soul", "Country",
             "Dance/Electronic", "Folk", "Jazz", "Blues", "**Other/Unknown**"]
        ) + "\n"
    ),
    md(
        "### 2a. Normalize tags & drop noise (what the bucketer does first)\n"
        "\n"
        "Before any genre rule fires, each raw tag is **normalized** and noise is\n"
        "**discarded** (`_normalize_tag` + `_is_noise` in `src/clean_quality.py`):\n"
        "\n"
        "- **Normalize** (one concept → one token): lowercase/trim; unify\n"
        "  `r&b` / `rnb` / `rhythm & blues` / `rhythm and blues` → `r&b`;\n"
        "  `synthpop` / `synth pop` → `synth-pop`; `hip-hop` → `hip hop`;\n"
        "  `rock n roll` / `rock & roll` → `rock and roll`; slashes/underscores → space.\n"
        "- **Drop as noise** (never a genre): nationalities/places (`american`, `english`,\n"
        "  `british`, `uk`, `usa`…), decade/era tags (`80s`, `2010s`, bare `2008`…), and\n"
        "  role/junk tags (`singer-songwriter`, `female vocals`, `icon`, `ballad`,\n"
        "  `christmas music`, `2008 universal fire victim`, `classic pop and rock`…).\n"
        "\n"
        "A couple of worked examples so the behaviour is visible inline:"
    ),
    code(
        "from src.clean_quality import _normalize_tag, _is_noise\n"
        "examples = ['Hip-Hop', 'RnB', 'Rhythm & Blues', 'Synth Pop', 'Rock & Roll',\n"
        "            'american', '2010s', '2008 universal fire victim', 'female vocals',\n"
        "            'singer-songwriter', 'pop rock', 'country pop', 'dance-pop']\n"
        "for e in examples:\n"
        "    n = _normalize_tag(e)\n"
        "    print(f'  {e:30s} -> {n:22s} {\"[NOISE, dropped]\" if _is_noise(n) else \"\"}')"
    ),
    md(
        "### 2b. The precedence ruleset — the core judgment call\n"
        "\n"
        "An artist tagged BOTH `pop` and `hip hop`, or `country` and `pop`, needs ONE\n"
        "bucket. `pop` is the default label slapped on almost everyone, so a more\n"
        "**specific** tag should win over bare Pop. Each surviving tag is mapped to a\n"
        "bucket by substring keyword rules, walked in this fixed **precedence order**\n"
        "(high → low) — the first bucket whose keyword hits wins for that tag:\n"
        "\n"
        "> **Hip-Hop/Rap > Country > R&B/Soul > Dance/Electronic > Folk > Jazz > Blues\n"
        "> > Rock > Pop > Other/Unknown**\n"
        "\n"
        "So `country pop` → **Country**, `pop rap` → **Hip-Hop/Rap**, `pop soul` →\n"
        "**R&B/Soul**, `dance-pop` → **Dance/Electronic**, `folk pop` → **Folk**. Rock sits\n"
        "just above Pop (more specific than `pop`, less than the niche genres), so\n"
        "`pop rock` → **Rock** but `country rock` → **Country**, `folk rock` → **Folk**,\n"
        "`blues rock` → **Blues** (those earlier buckets win on order).\n"
        "\n"
        "Across an artist's whole tag list the bucketer accumulates each tag's MB\n"
        "`count` as a **tie-break weight** per bucket (a missing/zero/negative count\n"
        "floors to 1), then picks the bucket with the **highest accumulated weight**,\n"
        "breaking ties by the precedence above. Rules are **substring/keyword**, not\n"
        "exact-match, so `alternative rock`, `hard rock`, `classic rock` all resolve to\n"
        "Rock. Full logic + docstring: `bucket_genre()` in `src/clean_quality.py`.\n"
        "\n"
        "**Documented bucket-folding decisions:**\n"
        "- **Disco → Dance/Electronic** (a dance-floor genre) and **Funk → R&B/Soul**\n"
        "  (a soul/R&B lineage) — rather than their own buckets.\n"
        "- **Latin, Reggae, Metal** did not reach the tag volume to justify a dedicated\n"
        "  aggregate bucket in this corpus, so they fall through to **Other/Unknown**.\n"
        "- Artists with no usable tags (not matched / not yet cached / only-noise tags)\n"
        "  → **Other/Unknown**."
    ),
    md(
        "### 2c. Build the `artist_genre` table\n"
        "\n"
        "One row per artist in the enrichment set, carrying the aggregate `genre` plus\n"
        "the raw tags (`top_tags`) and `n_tags` for auditability. The heavy transform is\n"
        "the per-artist bucketing (`genre_fields` → `bucket_genre`); we materialize those\n"
        "three derived fields in pandas, then write the table through DuckDB. We KEEP the\n"
        "Billboard-spelling `artist` as the join key `03-prepare` will use."
    ),
    code(
        "mb = con.execute('''\n"
        "    SELECT artist, mb_name, total_appearances, matched, tags\n"
        "    FROM mb_artist_genres_raw\n"
        "''').df()\n"
        "\n"
        "# Derive genre / n_tags / top_tags from the raw tag JSON (the bucketer).\n"
        "derived = mb['tags'].apply(genre_fields)\n"
        "mb['genre']    = derived.apply(lambda t: t[0])\n"
        "mb['n_tags']   = derived.apply(lambda t: t[1])\n"
        "mb['top_tags'] = derived.apply(lambda t: t[2])\n"
        "\n"
        "artist_genre = mb[['artist', 'mb_name', 'genre', 'total_appearances',\n"
        "                   'matched', 'n_tags', 'top_tags']].copy()\n"
        "\n"
        "# Write through DuckDB (SELECT * FROM the pandas frame) + interim Parquet.\n"
        "con.execute('DROP TABLE IF EXISTS artist_genre')\n"
        "con.execute('CREATE TABLE artist_genre AS SELECT * FROM artist_genre')\n"
        "save_interim(artist_genre, cfg, 'artist_genre.parquet')\n"
        "print('artist_genre:', con.execute('SELECT COUNT(*) FROM artist_genre').fetchone()[0], 'rows')\n"
        "artist_genre.head(5)"
    ),
    # ================================================================ step 3
    md(
        "## Step 3 — audit the bucketing (sanity-check the precedence calls)\n"
        "\n"
        "Three audits, all inline: the genre distribution, the Other/Unknown share split\n"
        "into *partial-pull* vs *genuinely-unmatched/untagged*, and a spot-check of\n"
        "well-known artists against the bucket they landed in."
    ),
    md("### 3a. Genre distribution (artists per aggregate bucket)"),
    code(
        "dist = run_sql('''\n"
        "    SELECT genre, COUNT(*) AS n_artists,\n"
        "           ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct\n"
        "    FROM artist_genre\n"
        "    GROUP BY genre\n"
        "    ORDER BY n_artists DESC\n"
        "''', con)\n"
        "display(dist)"
    ),
    md(
        "### 3b. Other/Unknown — how much is partial coverage vs genuinely unmatched?\n"
        "\n"
        "Being honest about coverage: an artist is Other/Unknown either because the MB\n"
        "pull hasn't reached them yet (`matched=False` — will resolve as the cache fills)\n"
        "or because MB matched them but they carry no usable genre tags (`matched=True` but\n"
        "no rule fired). Only the first number shrinks when the pull completes."
    ),
    code(
        "audit = run_sql('''\n"
        "    SELECT\n"
        "        COUNT(*) FILTER (WHERE genre = 'Other/Unknown')                       AS other_total,\n"
        "        COUNT(*) FILTER (WHERE genre = 'Other/Unknown' AND NOT matched)        AS other_not_yet_pulled,\n"
        "        COUNT(*) FILTER (WHERE genre = 'Other/Unknown' AND matched)            AS other_matched_no_genre,\n"
        "        COUNT(*)                                                               AS total_artists,\n"
        "        COUNT(*) FILTER (WHERE matched)                                        AS matched_artists\n"
        "    FROM artist_genre\n"
        "''', con).iloc[0]\n"
        "n = int(audit['total_artists'])\n"
        "print(f'Other/Unknown total        : {audit[\"other_total\"]:>5,}  ({audit[\"other_total\"]/n:.1%} of all artists)')\n"
        "print(f'  ├─ not yet pulled (cache) : {audit[\"other_not_yet_pulled\"]:>5,}  (will resolve as the MB pull fills)')\n"
        "print(f'  └─ matched, no genre tag  : {audit[\"other_matched_no_genre\"]:>5,}  (genuinely unbucketable)')\n"
        "print(f'matched artists so far     : {audit[\"matched_artists\"]:>5,} / {n:,}')\n"
        "matched_other_pct = audit['other_matched_no_genre'] / max(int(audit['matched_artists']), 1)\n"
        "print(f'\\nAmong MATCHED artists, Other/Unknown is {matched_other_pct:.1%} — this is the share '\n"
        "      'that will NOT shrink when the pull completes.')"
    ),
    md(
        "### 3c. 15-artist spot check — do the precedence calls look right?\n"
        "\n"
        "The owner's sanity-check list. For each, the aggregate bucket plus the raw tags\n"
        "that drove it (highest MB count first). Artists not yet cached show as\n"
        "Other/Unknown with empty tags — a coverage artifact, not a mapping error."
    ),
    code(
        "spot_names = ['Taylor Swift', 'Drake', 'Michael Jackson', 'Elvis Presley',\n"
        "              'The Beatles', 'Beyonce', 'Johnny Cash', 'Eminem', 'Madonna',\n"
        "              'Nirvana', 'Whitney Houston', 'Garth Brooks', 'Kendrick Lamar',\n"
        "              'Aretha Franklin', 'Daft Punk']\n"
        "lookup = {r['artist']: r for _, r in\n"
        "          con.execute('SELECT artist, genre, matched, top_tags FROM artist_genre').df().iterrows()}\n"
        "rows = []\n"
        "for name in spot_names:\n"
        "    r = lookup.get(name)\n"
        "    if r is None:\n"
        "        rows.append({'artist': name, 'genre': '(not in enrichment set)',\n"
        "                     'matched': '', 'top_tags': ''})\n"
        "    else:\n"
        "        tt = r['top_tags'] or ''\n"
        "        rows.append({'artist': name, 'genre': r['genre'],\n"
        "                     'matched': bool(r['matched']),\n"
        "                     'top_tags': (tt[:70] + '…') if len(tt) > 70 else tt})\n"
        "display(pd.DataFrame(rows, columns=['artist', 'genre', 'matched', 'top_tags']))"
    ),
    # ================================================================ step 4
    md(
        "## Step 4 — provenance\n"
        "\n"
        "Register the two interim tables in `_sources`, consistent with how `01-ingest`\n"
        "recorded the raw tables. The methodology note states that genre is an **aggregate\n"
        "bucketing of artist-level MusicBrainz tags via a documented precedence ruleset**,\n"
        "and that coverage is **partial** pending the full MB pull (Other/Unknown includes\n"
        "not-yet-cached artists)."
    ),
    code(
        "register_source(\n"
        "    con, 'hot100_clean',\n"
        "    'Billboard Hot 100 chart appearances (cleaned)',\n"
        "    url=cfg['sources']['hot100_all']['url'],\n"
        "    license=cfg['sources']['hot100_all']['license'],\n"
        "    notes=('Typed/deduped copy of hot100_raw: date→DATE with year/decade derived, '\n"
        "           'song/artist whitespace-normalized (artist_raw keeps the exact Billboard '\n"
        "           'spelling as the genre join key), this_week renamed to rank. One row per '\n"
        "           '(date, song, artist) chart appearance.'),\n"
        "    methodology=('02-clean DuckDB SQL pass: cast types, trim/collapse whitespace, '\n"
        "                 'drop exact (date, song, artist) duplicates, assert rank in 1..100 '\n"
        "                 'and no null date/song/artist.'),\n"
        "    series_breaks=('Inherits the hot100_raw methodology break: Hot 100 ranking '\n"
        "                   'incorporated digital downloads (2005) then streaming (2007+, '\n"
        "                   'progressively), so chart presence is not measured identically '\n"
        "                   'across eras.'),\n"
        ")\n"
        "register_source(\n"
        "    con, 'artist_genre',\n"
        "    'Artist → aggregate genre (bucketed from MusicBrainz tags)',\n"
        "    url=cfg['sources']['musicbrainz_artist']['url'],\n"
        "    license=cfg['sources']['musicbrainz_artist']['license'],\n"
        "    notes=('One aggregate genre per enriched artist, bucketed from the raw '\n"
        "           'artist-level MusicBrainz tags in mb_artist_genres_raw. artist = the '\n"
        "           'Billboard spelling (join key); top_tags/n_tags kept for auditability. '\n"
        "           'Aggregate set: ' + ', '.join(AGGREGATE_GENRES) + '.'),\n"
        "    methodology=('bucket_genre() in src/clean_quality.py: normalize tags (unify '\n"
        "                 'r&b/rnb, synth-pop, etc.), drop noise (nationality/decade/role '\n"
        "                 'tags), map each surviving tag to a bucket by substring keyword '\n"
        "                 'rules walked in a fixed precedence (Hip-Hop/Rap > Country > '\n"
        "                 'R&B/Soul > Dance/Electronic > Folk > Jazz > Blues > Rock > Pop), '\n"
        "                 'accumulate MB tag counts as tie-break weight, pick the top bucket. '\n"
        "                 'Disco→Dance/Electronic, Funk→R&B/Soul; Latin/Reggae/Metal→Other.'),\n"
        "    series_breaks=('COVERAGE IS PARTIAL pending the full MusicBrainz pull — artists '\n"
        "                   'not yet cached bucket to Other/Unknown (matched=false). Re-running '\n"
        "                   'after the pull completes changes only the Other/Unknown share, not '\n"
        "                   'the mapping. Tags are crowd-sourced and artist-level (whole catalog), '\n"
        "                   'not per-song or point-in-time.'),\n"
        ")\n"
        "from src.clean_quality import get_sources\n"
        "display(get_sources(con)[['duckdb_table', 'source_name', 'retrieved']])"
    ),
    md(
        "---\n"
        "**Next:** `03-prepare.ipynb` — join `hot100_clean` to `artist_genre` on the "
        "Billboard artist spelling and build the chart-ready genre-rank-over-time tables "
        "(per-year / per-decade genre presence + rank), then export. The join and all "
        "aggregation live in 03, NOT here."
    ),
    md(
        "---\n## Cleanup\n"
        "Close the DuckDB connection so the single-writer lock is released (the background "
        "MB pull writes a JSONL file, not this DB, so it is never the writer)."
    ),
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
