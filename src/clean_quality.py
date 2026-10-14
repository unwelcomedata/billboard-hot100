"""DuckDB-backed cleaning and data quality utilities.

Workflow:
  1. Load raw DataFrame into DuckDB (in the project .duckdb file).
  2. Run cleaning operations as SQL — fast, inspectable, reproducible.
  3. Run quality checks and print a report before writing interim output.
  4. Save cleaned table as Parquet to data/interim/.

All functions accept and return pandas DataFrames so notebooks stay readable,
but the heavy lifting happens inside DuckDB.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


# ---------------------------------------------------------------------------
# Source provenance (_sources metadata table)
# ---------------------------------------------------------------------------

_SOURCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS _sources (
    duckdb_table  VARCHAR,
    source_name   VARCHAR,
    url           VARCHAR,
    license       VARCHAR,
    notes         VARCHAR,
    retrieved     VARCHAR,
    methodology   VARCHAR,
    series_breaks VARCHAR
)
"""

# Columns that older databases may be missing (added after the original schema).
_SOURCES_ADDED_COLUMNS = ("methodology", "series_breaks")


def _ensure_sources_columns(con: duckdb.DuckDBPyConnection) -> None:
    """Add later-added _sources columns to pre-existing databases (idempotent)."""
    existing = {row[1] for row in con.execute("PRAGMA table_info('_sources')").fetchall()}
    for col in _SOURCES_ADDED_COLUMNS:
        if col not in existing:
            con.execute(f"ALTER TABLE _sources ADD COLUMN {col} VARCHAR")


def register_source(
    con: duckdb.DuckDBPyConnection,
    table: str,
    name: str,
    url: str = "",
    license: str = "",
    notes: str = "",
    retrieved: str = "",
    methodology: str = "",
    series_breaks: str = "",
) -> None:
    """Register a data source in the _sources metadata table.

    Call this after loading a new table into DuckDB to maintain full provenance.
    Replaces any existing entry for the same table name.

    Every source MUST document, in SOURCES.md and ideally here, how the source
    collects and defines its data (methodology) and any dates/boundaries across
    which the numbers are not comparable (series_breaks). These prevent
    apples-to-oranges comparisons (e.g. a definition that changed mid-series).

    Args:
        con:           Open DuckDB connection.
        table:         DuckDB table name this source populates.
        name:          Human-readable source name (e.g., "NHTSA FARS 2024").
        url:           Direct URL to the data file or page.
        license:       License string (e.g., "Public domain", "CC-BY 4.0").
        notes:         Any caveats or field descriptions.
        retrieved:     Date retrieved as ISO string (YYYY-MM-DD). Defaults to today.
        methodology:   How the source collects and defines the data.
        series_breaks: Dates/boundaries across which the numbers are NOT comparable.
    """
    from datetime import date as _date

    if not retrieved:
        retrieved = _date.today().isoformat()

    con.execute(_SOURCES_SCHEMA)
    _ensure_sources_columns(con)
    con.execute("DELETE FROM _sources WHERE duckdb_table = ?", [table])
    con.execute(
        """INSERT INTO _sources
           (duckdb_table, source_name, url, license, notes, retrieved,
            methodology, series_breaks)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [table, name, url, license, notes, retrieved, methodology, series_breaks],
    )


def get_sources(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return the full _sources provenance table as a DataFrame."""
    con.execute(_SOURCES_SCHEMA)
    return con.execute("SELECT * FROM _sources ORDER BY duckdb_table").df()


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_connection(cfg: dict[str, Any]) -> duckdb.DuckDBPyConnection:
    """Open (or create) the project DuckDB file and return a connection."""
    db_path = Path(cfg["settings"]["duckdb_file"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def load_to_duckdb(
    df: pd.DataFrame,
    table_name: str,
    con: duckdb.DuckDBPyConnection,
    replace: bool = True,
) -> None:
    """Register a DataFrame as a DuckDB table.

    Args:
        df:         Source DataFrame.
        table_name: Name for the table inside DuckDB.
        con:        Open DuckDB connection.
        replace:    Drop and recreate if the table already exists.
    """
    if replace:
        con.execute(f"DROP TABLE IF EXISTS {table_name}")
    # DuckDB can read a pandas DataFrame directly via the local variable name
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")


# ---------------------------------------------------------------------------
# Cleaning operations
# ---------------------------------------------------------------------------

def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase column names and replace spaces/hyphens with underscores."""
    df.columns = [
        c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns
    ]
    return df


def clean_table(
    df: pd.DataFrame,
    table_name: str,
    con: duckdb.DuckDBPyConnection,
    drop_duplicate_subset: list[str] | None = None,
    strip_columns: list[str] | None = None,
    cast_map: dict[str, str] | None = None,
    where_filter: str | None = None,
) -> pd.DataFrame:
    """Run a cleaning pass on a DataFrame inside DuckDB and return the result.

    Args:
        df:                    Raw DataFrame to clean.
        table_name:            Staging table name in DuckDB.
        con:                   Open DuckDB connection.
        drop_duplicate_subset: Column(s) to use for deduplication (None = all cols).
        strip_columns:         String columns to TRIM whitespace from.
        cast_map:              Dict of {column: duckdb_type} to cast, e.g. {"year": "INTEGER"}.
        where_filter:          Optional SQL WHERE clause (no 'WHERE' keyword) to filter rows.

    Returns:
        Cleaned DataFrame.
    """
    load_to_duckdb(df, table_name, con)

    # Build SELECT list with optional casts and trims
    col_exprs = []
    for col in df.columns:
        expr = f'"{col}"'
        if cast_map and col in cast_map:
            expr = f"TRY_CAST({expr} AS {cast_map[col]}) AS \"{col}\""
        elif strip_columns and col in strip_columns:
            expr = f"TRIM({expr}) AS \"{col}\""
        else:
            expr = f"{expr}"
        col_exprs.append(expr)

    select_clause = ", ".join(col_exprs)
    query = f"SELECT {select_clause} FROM {table_name}"
    if where_filter:
        query += f" WHERE {where_filter}"

    cleaned = con.execute(query).df()

    # Deduplication via pandas (easier to express cross-DB)
    if drop_duplicate_subset is not None:
        cleaned = cleaned.drop_duplicates(subset=drop_duplicate_subset)
    else:
        cleaned = cleaned.drop_duplicates()

    return cleaned.reset_index(drop=True)


def run_sql(sql: str, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Run arbitrary SQL against the open DuckDB connection and return a DataFrame.

    Useful for custom joins, aggregations, and feature engineering in notebooks.

    Example:
        run_sql("SELECT state, AVG(rate) as avg_rate FROM cleaned GROUP BY state", con)
    """
    return con.execute(sql).df()


# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------

def quality_report(
    df: pd.DataFrame,
    table_name: str,
    con: duckdb.DuckDBPyConnection,
    required_columns: list[str] | None = None,
    max_null_pct: float = 0.10,
) -> dict[str, Any]:
    """Run quality checks and print a summary report.

    Checks:
      - Row count
      - Null percentage per column (warns if above max_null_pct)
      - Duplicate row count
      - Presence of required columns

    Returns a dict with check results (useful for notebook assertions).
    """
    load_to_duckdb(df, f"_qc_{table_name}", con, replace=True)

    row_count = con.execute(f"SELECT COUNT(*) FROM _qc_{table_name}").fetchone()[0]
    dup_count = row_count - con.execute(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT * FROM _qc_{table_name})"
    ).fetchone()[0]

    null_pcts: dict[str, float] = {}
    warnings: list[str] = []
    for col in df.columns:
        nulls = con.execute(
            f'SELECT COUNT(*) FROM _qc_{table_name} WHERE "{col}" IS NULL'
        ).fetchone()[0]
        pct = nulls / row_count if row_count else 0.0
        null_pcts[col] = round(pct, 4)
        if pct > max_null_pct:
            warnings.append(f"  ⚠  '{col}' is {pct:.1%} null (threshold {max_null_pct:.0%})")

    missing_cols: list[str] = []
    if required_columns:
        missing_cols = [c for c in required_columns if c not in df.columns]
        if missing_cols:
            warnings.append(f"  ✗  Missing required columns: {missing_cols}")

    print(f"\n── Quality report: {table_name} ──────────────────")
    print(f"  Rows       : {row_count:,}")
    print(f"  Duplicates : {dup_count:,}")
    print(f"  Null %     :")
    for col, pct in null_pcts.items():
        flag = " ⚠" if pct > max_null_pct else ""
        print(f"    {col:<30} {pct:.1%}{flag}")
    if warnings:
        print("\n  Warnings:")
        for w in warnings:
            print(w)
    else:
        print("\n  ✓  No issues found.")
    print("─" * 50)

    return {
        "row_count": row_count,
        "duplicate_count": dup_count,
        "null_pcts": null_pcts,
        "missing_required_columns": missing_cols,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

def save_interim(df: pd.DataFrame, cfg: dict[str, Any], filename: str) -> Path:
    """Save a cleaned DataFrame to data/interim/ as Parquet."""
    out = Path(cfg["paths"]["data_interim"]) / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False, engine=cfg["settings"]["parquet_engine"])
    print(f"Saved interim → {out}  ({len(df):,} rows)")
    return out


def save_processed(df: pd.DataFrame, cfg: dict[str, Any], filename: str) -> Path:
    """Save an analysis-ready DataFrame to data/processed/ as Parquet."""
    out = Path(cfg["paths"]["data_processed"]) / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False, engine=cfg["settings"]["parquet_engine"])
    print(f"Saved processed → {out}  ({len(df):,} rows)")
    return out


# ===========================================================================
# Genre bucketing — raw MusicBrainz tags  →  a small aggregate-genre set
# ===========================================================================
#
# Billboard carries no genre; 01-ingest stored per-ARTIST MusicBrainz tags RAW
# (a messy mix: "pop", "pop rock", "dance-pop", plus noise like "american",
# "2010s", "female vocals", "2008 universal fire victim"). This section collapses
# that tag soup down to ONE aggregate genre per artist, deterministically.
#
# The mapping is the real deliverable and is INDEPENDENT of which artists happen
# to be cached yet: an artist with no usable tags (not matched / not cached /
# only-noise tags) buckets to "Other/Unknown", so re-running after the full MB
# pull changes only the Other/Unknown share, never the rule set.

# Canonical aggregate-genre set (the only values bucket_genre can return).
AGGREGATE_GENRES = [
    "Pop",
    "Rock",
    "Hip-Hop/Rap",
    "R&B/Soul",
    "Country",
    "Latin",
    "Dance/Electronic",
    "Folk",
    "Jazz",
    "Blues",
    "Metal",
    "Other/Unknown",
]

OTHER_UNKNOWN = "Other/Unknown"

# --- Tag noise: things that are never a genre -------------------------------
# Nationalities / places, decade tags, and role/junk tags. Filtered out BEFORE
# bucketing so they can never influence the result.
_NOISE_EXACT = {
    # nationality / place
    "american", "america", "usa", "us", "u.s.", "english", "british", "uk",
    "u.k.", "britain", "canadian", "canada", "australian", "australia",
    "irish", "ireland", "scottish", "welsh", "german", "germany", "french",
    "france", "italian", "swedish", "sweden", "norwegian", "jamaican",
    "jamaica", "latin american",
    # role / descriptor junk (NOT a genre)
    "singer-songwriter", "singer/songwriter", "singer songwriter",
    "female vocals", "male vocals", "female vocalist", "male vocalist",
    "icon", "legend", "ballad", "ballads", "christmas music", "holiday",
    "seasonal", "cover", "covers", "instrumental", "vocal", "soundtrack",
    "composer", "producer", "band", "duo", "group", "trio", "solo",
    "2008 universal fire victim", "pop and chart", "classic pop and rock",
    "rock and indie", "one-hit wonder", "various", "unknown",
}
# Substring markers that mark a tag as noise (decades, era buckets).
_NOISE_SUBSTR = (
    "19", "20", "'s", "fire victim", "vocal",
)
_DECADE_RE = re.compile(r"^\d{2,4}s$|^\d{4}$")


def _normalize_tag(tag: str) -> str:
    """Lowercase, strip, and unify spelling variants of a single tag.

    Collapses the common synonym clusters so one concept = one token:
      r&b / rnb / rhythm & blues / rhythm and blues  -> "r&b"
      synthpop / synth pop                            -> "synth-pop"
      rock and roll / rock & roll                     -> "rock and roll"
      hip-hop                                         -> "hip hop"
    """
    t = tag.strip().lower()
    t = t.replace("&", " and ")          # "r&b" -> "r and b", normalized below
    t = re.sub(r"[/_]", " ", t)          # slashes/underscores -> space
    t = re.sub(r"\s+", " ", t).strip()
    # synonym unification
    t = re.sub(r"\brhythm and blues\b", "r and b", t)
    t = re.sub(r"\brnb\b", "r and b", t)
    t = t.replace("r and b", "r&b")
    t = t.replace("hip-hop", "hip hop")
    t = t.replace("synthpop", "synth-pop")
    t = t.replace("synth pop", "synth-pop")
    t = t.replace("rock and roll", "rock and roll")
    t = t.replace("rock n roll", "rock and roll")
    return t


def _is_noise(tag: str) -> bool:
    """True if a normalized tag carries no genre signal (place/decade/role/junk)."""
    if not tag:
        return True
    if tag in _NOISE_EXACT:
        return True
    if _DECADE_RE.match(tag):
        return True
    # pure decade / era tokens like "80s", "2010s", "2008 universal fire victim"
    for marker in _NOISE_SUBSTR:
        if marker in tag:
            return True
    return False


# --- Bucket keyword rules ---------------------------------------------------
# Each aggregate bucket owns a set of substring keywords. A normalized tag is
# scored into a bucket if ANY of the bucket's keywords is a substring of it.
# The ORDER of this list IS the precedence: a tag that matches more than one
# bucket's keywords is assigned to the FIRST (highest-precedence) bucket, so a
# specific genre always beats the catch-all "pop". Precedence, high -> low:
#
#   Metal > Hip-Hop/Rap > Country > Latin > R&B/Soul > Dance/Electronic > Folk
#   > Jazz > Blues > Rock > Pop
#
# Rationale: "pop" is the default label slapped on almost everyone, so any more
# specific tag should win. "country pop" -> Country, "pop rap" -> Hip-Hop/Rap,
# "pop soul" -> R&B/Soul, "dance-pop" -> Dance/Electronic, "folk pop" -> Folk,
# "latin pop" -> Latin. Rock sits just above Pop (more specific than pop, less
# than the niche genres), so "pop rock" -> Rock but "country rock" -> Country,
# "folk rock" -> Folk, "blues rock" -> Blues (those earlier buckets win on order).
# Metal sits at the top so a metal subgenre top tag ("nu metal", "metalcore")
# lands in Metal, NOT Rock (metal was previously a Rock keyword and absorbed).
#
# Disco & funk FOLD INTO Dance/Electronic and R&B/Soul respectively (documented
# choice): disco is a dance-floor genre, funk is a soul/R&B lineage. **Latin** and
# **Metal** now have their own aggregate buckets (owner decision 2026-10-14):
# Latin recovers reggaeton/Latin-pop/salsa chart presence previously dumped in
# Other, and Metal is broken out of Rock so metal acts read as Metal. Reggae still
# lacks the tag volume to justify a bucket in this corpus and falls to Other.
_BUCKET_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Metal", (
        "metal", "thrash", "metalcore", "djent", "grindcore", "deathcore",
    )),
    ("Hip-Hop/Rap", (
        "hip hop", "rap", "trap", "grime", "drill", "crunk", "g-funk",
    )),
    ("Country", (
        "country", "bluegrass", "americana", "honky", "nashville", "western swing",
    )),
    ("Latin", (
        "latin", "reggaeton", "salsa", "bachata", "merengue", "regional mexican",
        "ranchera", "mariachi", "cumbia", "banda", "norteno", "norteño", "tejano",
        "bossa nova", "samba", "corrido",
    )),
    ("R&B/Soul", (
        "r&b", "soul", "funk", "motown", "new jack swing", "quiet storm",
        "doo-wop", "doo wop", "gospel",
    )),
    ("Dance/Electronic", (
        "dance", "electronic", "electro", "house", "techno", "edm", "disco",
        "trance", "dubstep", "synth-pop", "eurodance", "club", "hi-nrg",
        "freestyle",
    )),
    ("Folk", (
        "folk", "acoustic",
    )),
    ("Jazz", (
        "jazz", "swing", "bebop", "big band",
    )),
    ("Blues", (
        "blues", "rhythm and blues",  # (already normalized to r&b, kept as guard)
    )),
    ("Rock", (
        "rock", "grunge", "punk", "new wave", "britpop", "indie",
        "alternative", "emo",
    )),
    ("Pop", (
        "pop", "adult contemporary", "easy listening",
    )),
]


def _bucket_for_tag(norm_tag: str) -> str | None:
    """Return the aggregate bucket for ONE normalized tag, or None if no rule fires.

    Walks _BUCKET_RULES in precedence order and returns the first bucket whose
    keyword set has a substring hit in the tag — so "country pop" matches Country
    (checked before Pop) and "pop rock" matches Rock (checked before Pop).
    """
    for bucket, keywords in _BUCKET_RULES:
        for kw in keywords:
            if kw in norm_tag:
                return bucket
    return None


def bucket_genre(tags: Any) -> str:
    """Collapse an artist's raw MusicBrainz tag list to ONE aggregate genre.

    This is the canonical genre-bucketing rule for billboard-hot100. It is
    deterministic and independent of enrichment coverage: an artist with no
    usable tags returns "Other/Unknown".

    RULE — "top tag wins" (owner decision 2026-10-14): an artist's genre is the
    bucket of its SINGLE highest-MusicBrainz-count non-noise tag. This matches how
    the public actually perceives an artist ("when I think Taylor Swift I think
    Pop", not Country), rather than crediting an artist's full tag profile. It is
    a deliberate change from an earlier weighted-sum rule, which siphoned crossover
    stars into their roots/origin genre (Taylor Swift → Country via the summed
    country-family tags; Michael Jackson / Beyoncé → R&B/Soul). Under top-tag-wins
    those read as Pop, because "pop" is literally their most-voted MB tag.

    Algorithm:
      1. Parse `tags` (JSON string, list of {name, count} dicts, or list of
         strings) into (tag, count) pairs; a missing count = 0.
      2. Sort tags by MB count, highest first.
      3. Walk them in that order; normalize each (lowercase, unify r&b/rnb,
         synth-pop, etc.), skip noise (nationalities, decades, roles/junk), and
         return the bucket of the FIRST tag that maps to one. That first mapping
         is the artist's single most-voted genre tag.
      4. On an exact count TIE between the top competing tags, the ordered keyword
         rules (_BUCKET_RULES) still decide via the usual precedence (a specific
         genre beats the catch-all "pop"); this only matters when counts are equal.
      5. No bucket matched / only-noise tags / empty → "Other/Unknown".

    KNOWN CAVEAT (document in SOURCES.md): crossover superstars whose single
    top MB tag is "pop" (Michael Jackson, Beyoncé, Rihanna, Bruno Mars, Adele,
    Taylor Swift) read as Pop, so Pop absorbs them rather than their R&B/soul or
    country roots. This is intended under "what the public perceives", but it means
    Pop runs larger and the roots genres smaller than a lineage-based taxonomy would.

    PRECEDENCE (tiebreaker only, high → low):
        Metal > Hip-Hop/Rap > Country > Latin > R&B/Soul > Dance/Electronic
        > Folk > Jazz > Blues > Rock > Pop > Other/Unknown
    Disco folds into Dance/Electronic and funk into R&B/Soul (documented).
    Latin and Metal are their own aggregate buckets (owner decision 2026-10-14):
    Latin recovers reggaeton/Latin-pop/salsa; Metal is broken out of Rock. Reggae
    still lacks the tag volume for its own bucket and falls to Other/Unknown.

    Args:
        tags: JSON string, list[dict{name,count}], or list[str] of raw MB tags.

    Returns:
        One of AGGREGATE_GENRES.
    """
    # 1. Parse into (name, count) pairs ------------------------------------
    if tags is None:
        return OTHER_UNKNOWN
    if isinstance(tags, str):
        tags = tags.strip()
        if not tags:
            return OTHER_UNKNOWN
        try:
            tags = json.loads(tags)
        except (ValueError, TypeError):
            return OTHER_UNKNOWN
    if not isinstance(tags, (list, tuple)) or len(tags) == 0:
        return OTHER_UNKNOWN

    pairs: list[tuple[str, int]] = []
    for item in tags:
        if isinstance(item, dict):
            name = item.get("name", "")
            cnt = item.get("count", 0) or 0
        else:
            name, cnt = str(item), 0
        try:
            cnt = int(cnt)
        except (ValueError, TypeError):
            cnt = 0
        if name:
            pairs.append((name, cnt))

    if not pairs:
        return OTHER_UNKNOWN

    # 2. Sort by MB count, highest first. On an exact count tie, order the tied
    #    tags by their bucket precedence (lower _BUCKET_RULES index = higher
    #    precedence) so a specific genre beats bare "pop" only when counts are equal.
    _prec = {bucket: i for i, (bucket, _) in enumerate(_BUCKET_RULES)}

    def _tag_prec(name: str) -> int:
        b = _bucket_for_tag(_normalize_tag(name))
        return _prec.get(b, 999)

    pairs.sort(key=lambda p: (-p[1], _tag_prec(p[0])))

    # 3. First (highest-count, non-noise) tag that maps to a bucket wins.
    for name, _cnt in pairs:
        norm = _normalize_tag(name)
        if _is_noise(norm):
            continue
        bucket = _bucket_for_tag(norm)
        if bucket is not None:
            return bucket

    # 5. Nothing mapped.
    return OTHER_UNKNOWN


def genre_fields(tags: Any) -> tuple[str, int, str]:
    """Return (genre, n_tags, top_tags) for an artist's raw tag list.

    Convenience companion to bucket_genre() used by 02-clean to build the
    `artist_genre` table in one pass:
      - genre    : the aggregate bucket (bucket_genre).
      - n_tags   : number of NON-NOISE tags that survived normalization.
      - top_tags : the raw tag names (comma-joined, highest MB count first),
                   kept verbatim for auditability.
    """
    genre = bucket_genre(tags)

    # Parse again (cheap) for the audit fields.
    parsed = tags
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed) if parsed.strip() else []
        except (ValueError, TypeError):
            parsed = []
    if not isinstance(parsed, (list, tuple)):
        parsed = []

    named: list[tuple[str, int]] = []
    n_signal = 0
    for item in parsed:
        if isinstance(item, dict):
            name = item.get("name", "")
            cnt = item.get("count", 0) or 0
        else:
            name, cnt = str(item), 0
        try:
            cnt = int(cnt)
        except (ValueError, TypeError):
            cnt = 0
        if not name:
            continue
        named.append((name, cnt))
        if not _is_noise(_normalize_tag(name)):
            n_signal += 1

    named.sort(key=lambda x: x[1], reverse=True)
    top_tags = ", ".join(n for n, _ in named)
    return genre, n_signal, top_tags
