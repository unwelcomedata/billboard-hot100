"""Web ingestion utilities.

Handles three source types:
  - html_table  : pandas read_html on a static page
  - html_scrape : BeautifulSoup for custom element extraction
  - csv / json  : direct download and save to data/raw

All raw files land in data/raw unchanged. Call load_config() once per notebook
to get paths and source definitions from config.yaml.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(config_path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load project config.yaml and return it as a dict."""
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def raw_path(cfg: dict, filename: str) -> Path:
    """Return a Path inside data/raw, creating the directory if needed."""
    p = Path(cfg["paths"]["data_raw"]) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_CACHE_DIR: Path | None = None


def _get_cache_dir(cfg: dict) -> Path:
    """Return the cache directory (data/raw by default)."""
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = Path(cfg["paths"]["data_raw"])
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def fetch_html(url: str, headers: dict | None = None, timeout: int = 30) -> str:
    """Fetch a URL and return the response text.

    Raises requests.HTTPError on non-2xx status.
    """
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    resp = requests.get(url, headers=hdrs, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_cached(
    url: str,
    filename: str,
    cfg: dict,
    max_age_hours: float = 24.0,
    headers: dict | None = None,
    timeout: int = 30,
) -> str:
    """Fetch a URL with local file caching.

    If a cached file exists and is younger than max_age_hours, returns its
    contents without making a network request. Otherwise fetches, saves to
    data/raw/{filename}, and returns the content.

    Args:
        url:            URL to fetch.
        filename:       Cache filename (saved in data/raw/).
        cfg:            Loaded config dict.
        max_age_hours:  Re-fetch if cache is older than this (0 = always fetch).
        headers:        Optional extra HTTP headers.
        timeout:        Request timeout in seconds.

    Returns:
        Response text (from cache or network).
    """
    cache_path = _get_cache_dir(cfg) / filename
    if cache_path.exists() and max_age_hours > 0:
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            return cache_path.read_text(encoding="utf-8")

    text = fetch_html(url, headers=headers, timeout=timeout)
    cache_path.write_text(text, encoding="utf-8")
    return text


def fetch_with_retry(
    url: str,
    headers: dict | None = None,
    timeout: int = 30,
    max_retries: int = 3,
    rate_limit_seconds: float = 1.5,
) -> str:
    """Fetch a URL with rate limiting and exponential backoff on 429s.

    Args:
        url:                 URL to fetch.
        headers:             Optional extra HTTP headers.
        timeout:             Request timeout in seconds.
        max_retries:         Max retry attempts on 429/5xx.
        rate_limit_seconds:  Minimum delay between requests.

    Returns:
        Response text.

    Raises:
        requests.HTTPError after exhausting retries.
    """
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    time.sleep(rate_limit_seconds)

    for attempt in range(max_retries + 1):
        resp = requests.get(url, headers=hdrs, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < max_retries:
                wait = rate_limit_seconds * (2 ** attempt)
                print(f"  ⚠ {resp.status_code} on {url} — retrying in {wait:.0f}s")
                time.sleep(wait)
                continue
        resp.raise_for_status()
        return resp.text

    resp.raise_for_status()  # will raise on the last failed attempt
    return ""  # unreachable


def fetch_html_js(url: str, wait_selector: str | None = None, timeout: int = 30000) -> str:
    """Fetch a JS-rendered page using Playwright (headless Chromium).

    Use this when fetch_html() returns an empty or incomplete page.
    Requires: playwright install chromium

    Args:
        url:           Page URL.
        wait_selector: Optional CSS selector to wait for before returning HTML.
        timeout:       Playwright timeout in milliseconds.
    """
    from playwright.sync_api import sync_playwright  # lazy import

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(extra_http_headers=_DEFAULT_HEADERS)
        page.goto(url, timeout=timeout)
        if wait_selector:
            page.wait_for_selector(wait_selector, timeout=timeout)
        else:
            page.wait_for_load_state("networkidle", timeout=timeout)
        html = page.content()
        browser.close()
    return html


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_html_table(html: str, table_index: int = 0) -> pd.DataFrame:
    """Extract a <table> from HTML by index and return it as a DataFrame.

    Cleans up column names: lowercase, spaces → underscores.

    Note: pandas 3.x no longer accepts a raw HTML *string* — it must be a
    file-like object — so the string is wrapped in StringIO.
    """
    from io import StringIO

    tables = pd.read_html(StringIO(html))
    if not tables:
        raise ValueError("No tables found in the provided HTML.")
    if table_index >= len(tables):
        raise IndexError(
            f"table_index {table_index} out of range — page has {len(tables)} table(s)."
        )
    df = tables[table_index]
    df.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in df.columns
    ]
    return df


def parse_html_scrape(
    html: str,
    row_selector: str,
    field_map: dict[str, str],
) -> pd.DataFrame:
    """Scrape structured rows from HTML using CSS selectors.

    Args:
        html:          Raw HTML string.
        row_selector:  CSS selector that matches each "row" element.
        field_map:     Dict mapping output column name → CSS selector
                       relative to each row element.
                       Use '' (empty string) to get the row's own text.

    Example:
        parse_html_scrape(html, "tr.data-row", {"name": "td.name", "value": "td.val"})
    """
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select(row_selector)
    records = []
    for row in rows:
        record: dict[str, str] = {}
        for col, selector in field_map.items():
            el = row.select_one(selector) if selector else row
            record[col] = el.get_text(" ", strip=True) if el else ""
        records.append(record)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path, headers: dict | None = None, timeout: int = 60) -> Path:
    """Stream-download a file (CSV, JSON, zip, etc.) to dest and return the path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    with requests.get(url, headers=hdrs, timeout=timeout, stream=True) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
    return dest


# ---------------------------------------------------------------------------
# Source-driven ingest (reads config.yaml sources block)
# ---------------------------------------------------------------------------

def ingest_source(
    name: str,
    cfg: dict,
    save_raw: bool = True,
    js_wait_selector: str | None = None,
    row_selector: str | None = None,
    field_map: dict[str, str] | None = None,
    rate_limit_seconds: float = 1.0,
) -> pd.DataFrame:
    """Ingest a named source from config.yaml and return a DataFrame.

    Args:
        name:               Key under `sources:` in config.yaml.
        cfg:                Loaded config dict (from load_config()).
        save_raw:           If True, save the raw HTML/bytes to data/raw/.
        js_wait_selector:   Passed to fetch_html_js() if js_render is true.
        row_selector:       Required for html_scrape type.
        field_map:          Required for html_scrape type.
        rate_limit_seconds: Polite delay before fetching.
    """
    source = cfg["sources"][name]
    url: str = source["url"]
    source_type: str = source.get("type", "html_table")
    js_render: bool = source.get("js_render", False)
    table_index: int = source.get("table_index", 0)

    time.sleep(rate_limit_seconds)

    if source_type == "csv":
        dest = raw_path(cfg, f"{name}.csv")
        download_file(url, dest)
        return pd.read_csv(dest, encoding=cfg["settings"]["encoding"])

    if source_type == "json":
        dest = raw_path(cfg, f"{name}.json")
        download_file(url, dest)
        with open(dest, encoding=cfg["settings"]["encoding"]) as f:
            data = json.load(f)
        return pd.json_normalize(data)

    # HTML-based types
    html = fetch_html_js(url, wait_selector=js_wait_selector) if js_render else fetch_html(url)

    if save_raw:
        raw_path(cfg, f"{name}.html").write_text(html, encoding="utf-8")

    if source_type == "html_table":
        return parse_html_table(html, table_index=table_index)

    if source_type == "html_scrape":
        if row_selector is None or field_map is None:
            raise ValueError("html_scrape requires row_selector and field_map arguments.")
        return parse_html_scrape(html, row_selector, field_map)

    raise ValueError(f"Unknown source type '{source_type}'. Use: html_table, html_scrape, csv, json.")


# ===========================================================================
# Source 1 — Billboard Hot 100 full chart history (mhollingshead/billboard-hot-100)
# ===========================================================================
#
# A single ~44 MB JSON array of weekly chart objects, keyless raw-GitHub download:
#   [{"date": "1958-08-04",
#     "data": [{"song", "artist", "this_week", "last_week",
#               "peak_position", "weeks_on_chart"}, ... up to 100 rows ...]},
#    ... ~3,500+ weekly charts ...]
#
# Ingest = DOWNLOAD (cached) + FLATTEN to one row per (date, song, artist) chart
# appearance. This is a flatten, NOT a transform: every field is kept verbatim,
# we only explode the nested per-week `data` list into long rows. All cleaning
# (typing, dedupe, artist normalization, genre bucketing) is 02-clean's job.


def download_file_cached(
    url: str,
    dest: Path,
    headers: dict | None = None,
    timeout: int = 120,
    force: bool = False,
) -> Path:
    """Stream-download a (potentially large) file to `dest`, cached on disk.

    If `dest` already exists and `force` is False, the existing file is reused —
    so a ~44 MB download is only pulled once. Pass `force=True` to re-pull.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        size_mb = dest.stat().st_size / 1_048_576
        print(f"→ using cached download: {dest} ({size_mb:.1f} MB)")
        return dest
    print(f"→ downloading {url}")
    download_file(url, dest, headers=headers, timeout=timeout)
    size_mb = dest.stat().st_size / 1_048_576
    print(f"  saved {dest} ({size_mb:.1f} MB)")
    return dest


def ingest_hot100(
    cfg: dict,
    source_name: str = "hot100_all",
    cache_filename: str = "hot100_all.json",
    force: bool = False,
) -> pd.DataFrame:
    """Download + FLATTEN the Billboard Hot 100 full history to a long table.

    Downloads the ~44 MB JSON array (cached to data/raw/{cache_filename}) and
    explodes the nested weekly `data` lists into one row per (date, song, artist)
    chart appearance. Returns a DataFrame with columns:
        date, song, artist, this_week, last_week, peak_position, weeks_on_chart

    Nothing is cleaned or typed here — fields land exactly as the source stores
    them (that is 02-clean's job).
    """
    source = cfg["sources"][source_name]
    dest = download_file_cached(source["url"], raw_path(cfg, cache_filename), force=force)

    with open(dest, encoding=cfg["settings"]["encoding"]) as f:
        charts = json.load(f)
    print(f"→ {len(charts):,} weekly charts in the array")

    rows: list[dict] = []
    for chart in charts:
        date = chart.get("date")
        for entry in chart.get("data", []):
            rows.append(
                {
                    "date": date,
                    "song": entry.get("song"),
                    "artist": entry.get("artist"),
                    "this_week": entry.get("this_week"),
                    "last_week": entry.get("last_week"),
                    "peak_position": entry.get("peak_position"),
                    "weeks_on_chart": entry.get("weeks_on_chart"),
                }
            )
    df = pd.DataFrame(rows, columns=[
        "date", "song", "artist", "this_week", "last_week",
        "peak_position", "weeks_on_chart",
    ])
    print(f"→ flattened to {len(df):,} chart appearances")
    return df


# ===========================================================================
# Source 2 — MusicBrainz artist genre tags (keyless Web Service v2)
# ===========================================================================
#
# Billboard carries NO genre. We derive genre at the ARTIST level from MusicBrainz
# artist `tags`, collapsing the ~350k chart appearances down to the set of unique
# artists. We store the RAW tag list per artist (name + count) and do NOT bucket
# them into aggregate genres — the tags are messy (Taylor Swift → pop, country,
# synth-pop, 'female vocals', 'icon', '2000s') and bucketing is 02-clean's job.
#
# MusicBrainz REQUIRES a descriptive User-Agent or it returns 403, and asks for
# <= ~1 request/second. Every lookup is cached to a single JSONL file so a re-run
# RESUMES (skips already-cached artists) instead of re-pulling the slow endpoint.

MUSICBRAINZ_ARTIST_URL = "https://musicbrainz.org/ws/2/artist"

# A descriptive User-Agent is REQUIRED by the MusicBrainz Web Service.
_MB_HEADERS = {
    "User-Agent": "unwelcomedata/1.0 ( https://github.com/unwelcomedata )",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Billboard credit → MusicBrainz artist-name normalization
# ---------------------------------------------------------------------------
#
# MusicBrainz keys on an artist's CANONICAL name. Billboard credit strings carry
# featuring/backing-band/collaboration formatting ("Elvis Presley With The
# Jordanaires", "Prince And The Revolution", "Drake & 21 Savage") that never match
# MB's canonical name, so the first enrichment pass left 1,281 of 4,427 artists
# unmatched. `normalize_artist_for_mb()` derives the PRIMARY artist from a credit
# string for a cleaner MB lookup:
#
#   1. Cut featuring/with/backing credits at the first join token
#      (" feat.", " featuring", " with", " duet", " vs", " x ", "starring", "&
#      his/her", "and his/her", etc.).
#   2. Split a remaining collaboration on " & ", " and ", ",", "/", " + " and take
#      the FIRST (primary) artist. For a true co-bill ("Drake & 21 Savage") this
#      takes the primary ("Drake") — the right call for an ARTIST-LEVEL genre, and
#      a deliberately documented choice (SOURCES.md).
#   3. Strip trailing backing-band / orchestra tails ("His Orchestra", "And The
#      Vandellas", "His Twangy Guitar And The Rebels", "(Vocal By ...)").
#   4. Strip a leading "The ".
#
# A small CURATED ALIAS MAP handles the stubborn high-appearance names that
# cleaning alone can't fix (digit/word, punctuation, or outright different canonical
# names). It is applied to the ORIGINAL Billboard string BEFORE normalization and
# short-circuits the result. Each entry was verified to resolve on MB before adding.

# Applied to the ORIGINAL Billboard credit (exact, case-insensitive) and used verbatim.
#
# NOTE: alias values are fed to the forgiving UNQUOTED MB query (quoted=False), so
# they only need to be close enough to score the right artist first — each was
# verified to resolve to the intended artist on MB before adding.
_MB_ALIAS_MAP: dict[str, str] = {
    "daryl hall john oates": "Daryl Hall & John Oates",
    "'n sync": "*NSYNC",
    "jackson 5": "The Jackson 5",
    "the 4 seasons": "The Four Seasons",
    "ke$ha": "Kesha",
    "thirty eight special": ".38 Special",
    "dixie chicks": "The Chicks",
}

# Join tokens that introduce a FEATURING / backing / co-bill credit. The primary
# artist is everything BEFORE the first of these (word-boundary, case-insensitive).
_MB_CUT_PATTERNS = [
    r"\s+feat\.?\s+",
    r"\s+featuring\s+",
    r"\s+ft\.?\s+",
    r"\s+with\s+",
    r"\s+duet\s+with\s+",
    r"\s+duet\s+",
    r"\s+vs\.?\s+",
    r"\s+x\s+",
    r"\s+starring\s+",
    r"\s+presents\s+",
    r"\s+introducing\s+",
    r"\s+&\s+his\s+",
    r"\s+&\s+her\s+",
    r"\s+and\s+his\s+",
    r"\s+and\s+her\s+",
]
_MB_CUT_RE = __import__("re").compile("|".join(_MB_CUT_PATTERNS), __import__("re").IGNORECASE)

# Trailing orchestra / vocal-credit tails to strip from the primary artist. We
# deliberately strip ONLY the "His/Her Orchestra/Band" and "(Vocal By ...)" style
# session-credit tails — NOT "& The <Band>" / "And The <Band>", because for Motown-
# era acts the full "<Lead> & The <Group>" IS the canonical MusicBrainz name
# ("Martha & The Vandellas", "Diana Ross & The Supremes", "Gladys Knight & The
# Pips"). Those are handled by the co-bill split guard below, which keeps a
# "& The ..." group intact and only splits a true two-artist co-bill.
_MB_TAIL_RE = __import__("re").compile(
    r"\s*\(vocal by.*?\)\s*$"                        # "(Vocal By ...)"
    r"|\s+and\s+his\s+orchestra\s*$"                 # "And His Orchestra"
    r"|\s+and\s+her\s+orchestra\s*$"
    r"|\s+his\s+orchestra\s*$"                        # "His Orchestra"
    r"|\s+her\s+orchestra\s*$"
    r"|\s+his\s+.*\b(band|orchestra|rebels)\s*$"      # "His Twangy Guitar And The Rebels"
    r"|\s+her\s+.*\b(band|orchestra)\s*$",
    __import__("re").IGNORECASE,
)

# A trailing parenthetical ("Silk Sonic (Bruno Mars & Anderson .Paak)") — drop it,
# keeping the act name before the paren.
_MB_PAREN_RE = __import__("re").compile(r"\s*\(.*?\)\s*$")

# Co-bill separators. We split on these and keep the FIRST (primary) artist — BUT
# only when the SECOND side is itself a standalone artist, not a "The <Group>"
# backing group (so "Diana Ross & The Supremes" stays whole, while "Marvin Gaye &
# Tammi Terrell" and "Drake & 21 Savage" reduce to the primary).
_MB_COBILL_RE = __import__("re").compile(
    r"\s+&\s+(?!the\s)|\s+and\s+(?!the\s|his\s|her\s)|\s*,\s*|\s*/\s*|\s+\+\s+",
    __import__("re").IGNORECASE,
)


def normalize_artist_for_mb(raw: str) -> str:
    """Derive the PRIMARY artist from a Billboard credit string for MB lookup.

    See the module comment above for the full rationale. Returns a cleaned,
    canonical-ish artist name; an exact curated alias short-circuits everything.

    Examples:
        "Elvis Presley With The Jordanaires"            -> "Elvis Presley"
        "Prince And The Revolution"                     -> "Prince"            (co-bill cut)
        "Drake & 21 Savage"                             -> "Drake"
        "Paul McCartney And Wings"                      -> "Paul McCartney"
        "Marvin Gaye & Tammi Terrell"                   -> "Marvin Gaye"
        "Diana Ross & The Supremes"                     -> "Diana Ross & The Supremes" (kept whole)
        "The Weeknd & Ariana Grande"                    -> "The Weeknd"
        "Daryl Hall John Oates"                         -> "Hall & Oates"      (alias)
        "Jackson 5"                                     -> "The Jackson 5"     (alias)
    """
    import re

    if not raw:
        return ""
    s = re.sub(r"\s+", " ", str(raw)).strip()

    # 1. Curated alias (exact, case-insensitive) short-circuits.
    alias = _MB_ALIAS_MAP.get(s.lower())
    if alias:
        return alias

    # 2. Cut at the first featuring/with/co-bill-credit token ("feat.", "with",
    #    "& his", "and her", "starring", ...). This removes session/guest credits
    #    like "... Featuring Mark Lindsay" and "Paul McCartney And Wings"
    #    ("and his/her" is in the cut set; "And Wings" is a plain "and" → handled
    #    by the co-bill split in step 5).
    m = _MB_CUT_RE.search(s)
    if m:
        s = s[: m.start()].strip()

    # 3. Drop a trailing parenthetical.
    s = _MB_PAREN_RE.sub("", s).strip()

    # 4. Strip an orchestra / session-band tail (NOT "& The <Group>").
    prev = None
    while prev != s:
        prev = s
        s = _MB_TAIL_RE.sub("", s).strip()

    # 5. Split a true co-bill and keep the FIRST (primary) artist. A trailing
    #    "& The <Group>" / "and his/her ..." is NOT a co-bill separator here
    #    (negative lookahead), so Motown "<Lead> & The <Group>" names stay whole.
    #    "Paul McCartney And Wings" -> "Paul McCartney" (Wings is a plain "and").
    parts = [p.strip() for p in _MB_COBILL_RE.split(s) if p.strip()]
    if len(parts) > 1:
        s = parts[0]

    return s or str(raw).strip()


def artist_appearance_counts(df_hot100: pd.DataFrame) -> pd.DataFrame:
    """Count total Hot 100 chart appearances per (Billboard-spelling) artist.

    Returns a DataFrame [artist, total_appearances] sorted descending — the
    coverage ranking used to decide which artists to enrich with genre.
    """
    counts = (
        df_hot100.groupby("artist", dropna=True)
        .size()
        .reset_index(name="total_appearances")
        .sort_values("total_appearances", ascending=False)
        .reset_index(drop=True)
    )
    return counts


def _mb_fetch_artist(name: str, rate_limit_seconds: float = 1.1,
                     max_retries: int = 4, query_name: str | None = None,
                     quoted: bool = True) -> dict:
    """Query MusicBrainz for the top artist match and return its raw tag list.

    The cache record is keyed by the ORIGINAL Billboard `name` (so downstream joins
    still work), but the MusicBrainz query uses `query_name` when supplied — the
    normalized primary-artist name — and records it as `query_name` for auditability.

    `quoted` controls the Lucene query form. `artist:"<name>"` (quoted=True, the
    original ingest behavior) demands a near-exact name and misses credit-formatted
    strings; `artist:<name>` (quoted=False) is a forgiving fuzzy search that returns
    a score-ranked list — far better for the re-query of unmatched artists, so the
    re-query path passes quoted=False and takes the top (highest-score) match.

    Returns a dict: {artist, query_name, mb_artist_id, mb_name,
    tags (list of {name,count}), matched (bool)}. On no match, matched=False with
    empty tags. Rate-limited with exponential backoff on 429/5xx.
    """
    q = query_name if query_name else name
    query = f'artist:"{q}"' if quoted else f"artist:{q}"
    params = {"query": query, "fmt": "json", "limit": 1}
    time.sleep(rate_limit_seconds)
    for attempt in range(max_retries + 1):
        resp = requests.get(
            MUSICBRAINZ_ARTIST_URL, params=params, headers=_MB_HEADERS, timeout=45
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < max_retries:
                wait = rate_limit_seconds * (2 ** attempt)
                print(f"    ⚠ {resp.status_code} from MusicBrainz — retry in {wait:.0f}s")
                time.sleep(wait)
                continue
        resp.raise_for_status()
        data = resp.json()
        artists = data.get("artists", [])
        if not artists:
            return {"artist": name, "query_name": q, "mb_artist_id": None,
                    "mb_name": None, "tags": [], "matched": False}
        top = artists[0]
        return {
            "artist": name,
            "query_name": q,
            "mb_artist_id": top.get("id"),
            "mb_name": top.get("name"),
            "tags": top.get("tags", []) or [],
            "matched": True,
        }
    resp.raise_for_status()
    return {"artist": name, "query_name": q, "mb_artist_id": None,
            "mb_name": None, "tags": [], "matched": False}


def _load_mb_cache(cache_path: Path) -> dict[str, dict]:
    """Load the resumable MusicBrainz cache (one JSON object per line)."""
    cached: dict[str, dict] = {}
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                cached[rec["artist"]] = rec
    return cached


def requery_unmatched_mb(
    cfg: dict,
    cache_filename: str = "mb_artist_cache.jsonl",
    rate_limit_seconds: float = 1.1,
    progress_every: int = 25,
    max_fetch: int | None = None,
) -> dict[str, int]:
    """Re-query the currently-UNMATCHED cached artists with normalized names.

    Reads the resumable cache (`data/raw/mb_artist_cache.jsonl`), finds every artist
    whose latest record is `matched=False`, derives a cleaner MusicBrainz query via
    `normalize_artist_for_mb()` (primary-artist extraction + curated alias map), and
    re-queries ONLY those. Each result is APPENDED to the same JSONL cache keyed by
    the ORIGINAL Billboard artist name — so `_load_mb_cache` (last-line-wins) picks up
    the improved record and the downstream join is unaffected. The normalized
    `query_name` is recorded on every new record for auditability.

    Fully RESUMABLE: a record is only re-queried if its latest cache state is still
    unmatched AND the normalized name actually differs from a query already tried for
    it. Rate-limited (>=1.1s); progress printed every `progress_every` artists.

    Returns a summary dict: {unmatched_before, attempted, newly_matched, still_unmatched}.
    """
    cache_path = raw_path(cfg, cache_filename)
    cached = _load_mb_cache(cache_path)

    unmatched = {a: rec for a, rec in cached.items() if not rec.get("matched")}
    print(f"→ cache has {len(cached):,} artists; {len(unmatched):,} currently unmatched")

    # Build the re-query list. We re-attempt EVERY still-unmatched artist, because
    # the re-query differs from the original pass in TWO ways that both help:
    #   (a) the query NAME is the normalized primary-artist (credit stripping + alias), and
    #   (b) the query FORM switches from exact-quoted to a forgiving unquoted Lucene
    #       search (quoted=False in the fetch) that returns a score-ranked match.
    # So even an artist whose normalized name == its raw name is worth re-querying,
    # since the forgiving query form alone often resolves it. A record that was ALREADY
    # re-queried in a prior resumable pass (its latest cache line carries query_name and
    # is still unmatched) is skipped so repeated runs don't re-hammer dead names.
    to_requery: list[tuple[str, str]] = []  # (original billboard name, normalized query)
    skipped_already_requeried = 0
    for name, rec in unmatched.items():
        if rec.get("query_name"):
            # Already went through a normalized re-query in a prior pass and still
            # didn't match — don't keep retrying a confirmed dead end.
            skipped_already_requeried += 1
            continue
        to_requery.append((name, normalize_artist_for_mb(name)))

    if skipped_already_requeried:
        print(f"→ {skipped_already_requeried:,} unmatched artists skipped "
              f"(already re-queried with a normalized name in a prior pass — confirmed no match)")

    if max_fetch is not None:
        to_requery = to_requery[:max_fetch]

    print(f"→ re-querying {len(to_requery):,} unmatched artists with normalized names "
          f"+ forgiving query (~{len(to_requery) * rate_limit_seconds / 60:.0f}+ min "
          f"at {rate_limit_seconds}s each)")

    newly_matched = 0
    transient_skipped = 0
    with open(cache_path, "a", encoding="utf-8") as cache_f:
        for i, (name, norm) in enumerate(to_requery, 1):
            try:
                rec = _mb_fetch_artist(
                    name, rate_limit_seconds=rate_limit_seconds, query_name=norm,
                    quoted=False, max_retries=6,
                )
            except Exception as e:  # noqa: BLE001 — transient network/5xx after retries
                # Do NOT write a record on a transient failure — leaving it absent
                # of a new query_name means a resumed run will retry it rather than
                # permanently marking a (possibly matchable) artist as a dead end.
                print(f"    ⚠ transient re-query failure for {name!r} (as {norm!r}), "
                      f"will retry on resume: {e}")
                transient_skipped += 1
                continue
            cache_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            cache_f.flush()
            cached[name] = rec
            if rec.get("matched"):
                newly_matched += 1
            if i % progress_every == 0 or i == len(to_requery):
                print(f"  [{i:>5}/{len(to_requery)}] re-queried "
                      f"(newly matched so far: {newly_matched})")

    if transient_skipped:
        print(f"→ {transient_skipped:,} artists hit transient failures and were "
              f"left for a resume pass (not marked unmatched)")

    still_unmatched = sum(1 for a, rec in cached.items() if not rec.get("matched"))
    summary = {
        "unmatched_before": len(unmatched),
        "attempted": len(to_requery),
        "newly_matched": newly_matched,
        "still_unmatched": still_unmatched,
    }
    print(f"\n→ re-query done: attempted {summary['attempted']:,}, "
          f"newly matched {summary['newly_matched']:,}; "
          f"{summary['still_unmatched']:,} still unmatched in cache")
    return summary


def ingest_musicbrainz_genres(
    cfg: dict,
    df_hot100: pd.DataFrame,
    min_appearances: int = 10,
    cache_filename: str = "mb_artist_cache.jsonl",
    rate_limit_seconds: float = 1.1,
    progress_every: int = 50,
    fetch: bool = True,
    max_fetch: int | None = None,
) -> pd.DataFrame:
    """Enrich chart artists with raw MusicBrainz genre tags, RESUMABLE + cached.

    Only artists with >= `min_appearances` total Hot 100 appearances are enriched
    (a deliberate ingest-scope decision — the lead chart is genre rank over time,
    which only needs genre for artists that matter to the ranking). Lower-appearance
    artists are left ungenred for now (02-clean/03 treat them as Other/unknown).

    Every lookup is appended to data/raw/{cache_filename} (one JSON object per line,
    keyed by the Billboard artist name). A re-run loads the cache and SKIPS any
    artist already present, so an interrupted pull resumes where it left off.

    MusicBrainz is slow (~1 req/sec), so a full target set can take hours. To keep a
    notebook run tractable the actual network pull is typically done ahead of time by
    `scripts/_pull_mb_cache.py` (which calls this with fetch=True) and the notebook
    calls with `fetch=False` to simply CONSUME the warm cache without blocking. In
    either mode the enrichment table is built from whatever is cached, and artists not
    yet cached are returned with matched=False (honest coverage).

    Args:
        fetch:     If True, fetch any not-yet-cached target artists from MusicBrainz
                   (appending to the cache). If False, only read the existing cache.
        max_fetch: Optional cap on how many artists to fetch this call (None = all).

    Returns a DataFrame with columns:
        artist, mb_artist_id, mb_name, tags (JSON string), total_appearances, matched
    """
    cache_path = raw_path(cfg, cache_filename)

    counts = artist_appearance_counts(df_hot100)
    targets = counts[counts["total_appearances"] >= min_appearances].reset_index(drop=True)
    appearances = dict(zip(targets["artist"], targets["total_appearances"]))
    print(f"→ {len(counts):,} unique artists; "
          f"{len(targets):,} with >= {min_appearances} appearances (enrichment set)")

    cached = _load_mb_cache(cache_path)
    if cached:
        print(f"→ cache has {len(cached):,} artists already looked up")

    to_fetch = [a for a in targets["artist"].tolist() if a not in cached]
    if max_fetch is not None:
        to_fetch = to_fetch[:max_fetch]

    if fetch and to_fetch:
        print(f"→ fetching {len(to_fetch):,} not-yet-cached artists "
              f"(~{len(to_fetch) * rate_limit_seconds / 60:.0f}+ min at {rate_limit_seconds}s each)")
        with open(cache_path, "a", encoding="utf-8") as cache_f:
            for i, name in enumerate(to_fetch, 1):
                try:
                    rec = _mb_fetch_artist(name, rate_limit_seconds=rate_limit_seconds)
                except Exception as e:  # noqa: BLE001 — log, keep going; cache resumes
                    print(f"    ⚠ lookup failed for {name!r}: {e}")
                    rec = {"artist": name, "mb_artist_id": None, "mb_name": None,
                           "tags": [], "matched": False}
                cache_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                cache_f.flush()
                cached[name] = rec
                if i % progress_every == 0 or i == len(to_fetch):
                    hits = sum(1 for n in to_fetch[:i] if cached[n]["matched"])
                    print(f"  [{i:>5}/{len(to_fetch)}] fetched (matched so far: {hits})")
    elif to_fetch:
        print(f"→ fetch=False: {len(to_fetch):,} target artists not yet in cache "
              f"(returned with matched=False — resumable via scripts/_pull_mb_cache.py)")

    # Assemble the enrichment table for ALL target artists (tags → JSON string).
    # Artists not in the cache are kept with matched=False so coverage is honest.
    rows: list[dict] = []
    for name in targets["artist"].tolist():
        rec = cached.get(name, {"mb_artist_id": None, "mb_name": None,
                                "tags": [], "matched": False})
        rows.append(
            {
                "artist": name,
                "mb_artist_id": rec.get("mb_artist_id"),
                "mb_name": rec.get("mb_name"),
                "tags": json.dumps(rec.get("tags", []), ensure_ascii=False),
                "total_appearances": int(appearances[name]),
                "matched": bool(rec.get("matched", False)),
            }
        )
    df = pd.DataFrame(rows, columns=[
        "artist", "mb_artist_id", "mb_name", "tags", "total_appearances", "matched",
    ])
    print(f"→ enrichment table: {len(df):,} artists "
          f"({int(df['matched'].sum()):,} matched, {int((~df['matched']).sum()):,} unmatched/uncached)")
    return df
