#!/usr/bin/env python3
"""Pre-publish validation — re-check the billboard-hot100 chart data before publishing.

Run this BEFORE curating the release branch / flipping the repo public. It re-derives,
straight from the DuckDB source tables, what each of the 4 published social charts should
show, and confirms:

  1. LEAD bump (genre rank, top-6, 1970+, Other excluded, re-densed): spot-check
     years match the chart; Hip-Hop/Rap rose; Rock led the early years; 1970-2026 span;
     every year has 5-6 ranked genres (the Hip-Hop-absent early-70s edge case).
     NOTE: the LEAD bump ships in TWO grains — DECADE on social, ANNUAL on web — but both
     derive from the same chart_genre_rank_top rank facts asserted here (grain-agnostic).
  2. SUPPORT genre-share 100%-stacked by decade: per-decade shares sum to ~100.
  3/4. Song charts (longest-charting, per era): the #1 song + a spot value per era, the
     genre-mix flip (Rock present pre, absent streaming era), top weeks 87 vs 112.
  5. Export CSVs match their DuckDB source tables (no drift) — conditional on being present.
  6. Social/web parity across the 4 published chart filenames (+ the web-only stacked
     comparison); social = 1600x900, web landscape = 1664x936.
  7. Methodology break: the 2013 streaming break is documented in _sources (so it can't
     silently drop); the on-chart dashed marker is eyeball-verified in 06-viz-social.

Metal is NOT a published social chart (it's only the genre-picker default), so there are
no Metal social-chart assertions here. The Metal peak (276 in 2001) is still checked as a
data fact behind the picker.

Exit code 0 = all checks passed, safe to publish. Non-zero = do NOT publish.

Usage:
    .venv/bin/python scripts/validate_charts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT = Path(__file__).resolve().parent
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent
sys.path.insert(0, str(PROJECT))
from src.ingest import load_config  # noqa: E402

failures: list[str] = []
checks: list[str] = []

# The 4 published social charts (base filenames; both outputs/social & outputs/web).
PUBLISHED = {
    "01_genre_rank_bump",
    "02_genre_share_by_decade",
    "03_longest_charting_pre_streaming",
    "04_longest_charting_streaming_era",
}
# Web-only extra: the stacked pre/post song comparison (Pages object, not social).
WEB_ONLY = {"05_longest_charting_comparison"}


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        checks.append(f"  PASS  {name}")
    else:
        failures.append(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def approx(a: float, b: float, tol: float = 0.005) -> bool:
    if b == 0:
        return a == 0
    return abs(a - b) / abs(b) <= tol


def main() -> int:
    cfg = load_config("config.yaml")
    db = str(PROJECT / cfg["settings"]["duckdb_file"])
    export_dir = PROJECT / cfg["paths"]["export"]
    con = duckdb.connect(db, read_only=True)

    # ── Chart 1 — LEAD annual genre rank bump (top-6, 1970+, re-densed) ───
    bump = con.execute(
        """
        SELECT year, genre,
               DENSE_RANK() OVER (PARTITION BY year ORDER BY appearances DESC) AS rank
        FROM chart_genre_rank_top
        WHERE year >= 1970
        ORDER BY year, rank
        """
    ).df()

    def rank_of(yr: int, genre: str):
        row = bump[(bump.year == yr) & (bump.genre == genre)]
        return int(row["rank"].iloc[0]) if len(row) else None

    check("chart1: 1970+ span is 1970-2026",
          int(bump.year.min()) == 1970 and int(bump.year.max()) == 2026,
          f"got {int(bump.year.min())}-{int(bump.year.max())}")
    per_year = bump.groupby("year").size()
    check("chart1: every year has 5-6 ranked genres (Hip-Hop absent early-70s)",
          bool(((per_year >= 5) & (per_year <= 6)).all()),
          f"min {int(per_year.min())}, max {int(per_year.max())}")
    # Spot-check years (verified 2026-10-15 against the DB).
    check("chart1: 1975 Rock #1, R&B/Soul #2",
          rank_of(1975, "Rock") == 1 and rank_of(1975, "R&B/Soul") == 2,
          f"Rock {rank_of(1975,'Rock')}, R&B/Soul {rank_of(1975,'R&B/Soul')}")
    check("chart1: 1995 Hip-Hop/Rap #1, Rock #2",
          rank_of(1995, "Hip-Hop/Rap") == 1 and rank_of(1995, "Rock") == 2,
          f"HH {rank_of(1995,'Hip-Hop/Rap')}, Rock {rank_of(1995,'Rock')}")
    check("chart1: 2020 Hip-Hop/Rap #1",
          rank_of(2020, "Hip-Hop/Rap") == 1, f"got {rank_of(2020,'Hip-Hop/Rap')}")
    # Hip-Hop/Rap ROSE: worse (higher-number) rank in the early 70s than #1 in 2020.
    hh_1970 = rank_of(1970, "Hip-Hop/Rap")
    check("chart1: Hip-Hop/Rap rose (early-70s rank worse than its 2020 #1)",
          hh_1970 is not None and hh_1970 > 1 and rank_of(2020, "Hip-Hop/Rap") == 1,
          f"1970 HH rank {hh_1970}, 2020 {rank_of(2020,'Hip-Hop/Rap')}")
    # Rock's early lead: it reaches #1 across 1975-1978 (R&B/Soul led the very early 70s).
    rock_mid70s = [rank_of(y, "Rock") for y in (1975, 1976, 1977, 1978)]
    check("chart1: Rock led the mid-1970s (rank 1 in 1975-1978)",
          all(r == 1 for r in rock_mid70s), f"got {rock_mid70s}")

    # ── Chart 2 — genre-share 100% stacked by decade (part-of-whole) ──────
    dec = con.execute("SELECT decade, SUM(share) AS tot FROM chart_genre_by_decade "
                      "GROUP BY decade ORDER BY decade").df()
    check("chart2: every decade's genre shares sum to ~100%",
          bool((dec["tot"].sub(100).abs() <= 0.5).all()),
          f"off-decades: {dec[dec['tot'].sub(100).abs() > 0.5].to_dict('records')}")

    # ── Charts 3 & 4 — longest-charting songs per era ─────────────────────
    pre = con.execute(
        "SELECT song, artist, genre, weeks FROM chart_songs_pre_streaming "
        "ORDER BY weeks DESC, song").df()
    stream = con.execute(
        "SELECT song, artist, genre, weeks FROM chart_songs_streaming_era "
        "ORDER BY weeks DESC, song").df()
    check("chart3: pre-streaming top-10 rows", len(pre) == 10, f"got {len(pre)}")
    check("chart4: streaming-era top-10 rows", len(stream) == 10, f"got {len(stream)}")
    p0 = pre.iloc[0]
    check("chart3: pre #1 = Radioactive / Imagine Dragons, 87 wks (Rock)",
          p0["song"] == "Radioactive" and p0["artist"] == "Imagine Dragons"
          and int(p0["weeks"]) == 87 and p0["genre"] == "Rock",
          f"got {p0['song']!r}/{p0['artist']!r} {int(p0['weeks'])} {p0['genre']!r}")
    s0 = stream.iloc[0]
    check("chart4: streaming #1 = Lose Control / Teddy Swims, 112 wks (R&B/Soul)",
          s0["song"] == "Lose Control" and s0["artist"] == "Teddy Swims"
          and int(s0["weeks"]) == 112 and s0["genre"] == "R&B/Soul",
          f"got {s0['song']!r}/{s0['artist']!r} {int(s0['weeks'])} {s0['genre']!r}")
    check("chart3/4: streaming-era songs run longer (max 112 > pre max 87)",
          int(stream["weeks"].max()) == 112 and int(pre["weeks"].max()) == 87,
          f"pre {int(pre['weeks'].max())}, stream {int(stream['weeks'].max())}")
    # Genre-mix flip: Rock in the pre top-10, absent from the streaming top-10.
    check("chart3/4: genre mix flips (Rock in pre top-10, absent streaming top-10)",
          "Rock" in set(pre["genre"]) and "Rock" not in set(stream["genre"]),
          f"pre {sorted(set(pre['genre']))}, stream {sorted(set(stream['genre']))}")

    # ── Metal data fact (behind the picker, not a social chart) ───────────
    myear, mpeak = con.execute(
        "SELECT year, MAX(appearances) FROM chart_genre_by_year WHERE genre='Metal' "
        "GROUP BY year ORDER BY 2 DESC LIMIT 1").fetchone()
    check("picker: Metal peak = 276 appearances in 2001",
          int(mpeak) == 276 and int(myear) == 2001, f"got {int(mpeak)} in {int(myear)}")

    # ── Methodology break present in _sources (can't silently drop) ───────
    sb = con.execute(
        "SELECT series_breaks FROM _sources WHERE duckdb_table='chart_genre_by_year'"
    ).fetchone()
    check("methodology: 2013 streaming break documented in _sources (chart_genre_by_year)",
          sb is not None and "2013" in (sb[0] or ""), f"got {sb}")

    # ── Export CSVs match DuckDB (no drift) — conditional ─────────────────
    def check_export(name: str, table: str, keycols: list[str]) -> None:
        path = export_dir / f"{name}.csv"
        if not path.exists():
            checks.append(f"  SKIP  export {name}.csv not on disk (regenerable via 03-prepare)")
            return
        src = con.execute(f"SELECT {', '.join(keycols)} FROM {table}").df()
        csv = pd.read_csv(path)
        try:
            a = src[keycols].reset_index(drop=True)
            b = csv[keycols].reset_index(drop=True)
            same = a.shape == b.shape
            detail = "" if same else f"row count {a.shape[0]} vs {b.shape[0]}"
            if same:
                a = a.sort_values(keycols).reset_index(drop=True)
                b = b.sort_values(keycols).reset_index(drop=True)
                for col in keycols:
                    if pd.api.types.is_numeric_dtype(a[col]):
                        diff = (a[col].astype("float64") - b[col].astype("float64")).abs()
                        col_ok = bool(((diff <= 0.001) | (a[col].isna() & b[col].isna())).all())
                    else:
                        col_ok = bool((a[col].fillna("\x00").astype(str) ==
                                       b[col].fillna("\x00").astype(str)).all())
                    if not col_ok:
                        same, detail = False, f"column {col!r} differs"
                        break
            check(f"export: {name}.csv matches DuckDB on key columns", same,
                  (detail + " — regenerate 03-prepare") if detail else "")
        except KeyError as e:
            check(f"export: {name}.csv has expected columns {keycols}", False, str(e))

    check_export("billboard_hot100_longest_charting_pre_streaming",
                 "chart_songs_pre_streaming", ["song", "artist", "genre", "weeks"])
    check_export("billboard_hot100_longest_charting_streaming_era",
                 "chart_songs_streaming_era", ["song", "artist", "genre", "weeks"])

    con.close()

    # ── Social vs web chart parity ────────────────────────────────────────
    social_dir = PROJECT / "outputs" / "social"
    web_dir = PROJECT / "outputs" / "web"
    social = {p.stem for p in social_dir.glob("*.png")} if social_dir.exists() else set()
    web = {p.stem for p in web_dir.glob("*.png")} if web_dir.exists() else set()
    if social and web:
        # Consider only the published charts (exploration explore_* PNGs are ignored).
        pub_social = social & PUBLISHED
        pub_web = web & PUBLISHED
        check("parity: all 4 published charts present in outputs/social",
              pub_social == PUBLISHED, f"missing social: {sorted(PUBLISHED - pub_social)}")
        check("parity: all 4 published charts present in outputs/web",
              pub_web == PUBLISHED, f"missing web: {sorted(PUBLISHED - pub_web)}")
        check("parity: social & web cover the same published filenames",
              pub_social == pub_web,
              f"only social: {sorted(pub_social - pub_web)}; only web: {sorted(pub_web - pub_social)}")
        check("parity: the web-only stacked song comparison exists",
              WEB_ONLY <= web, f"missing web-only: {sorted(WEB_ONLY - web)}")
        try:
            from PIL import Image
            s_dims = {Image.open(social_dir / f"{n}.png").size for n in PUBLISHED}
            check("parity: every published social chart is 1600x900",
                  s_dims == {(1600, 900)}, f"got {sorted(s_dims)}")
            w_dims = {Image.open(web_dir / f"{n}.png").size for n in PUBLISHED}
            check("parity: every published web chart is the 1664-wide web canvas (1664x936)",
                  w_dims == {(1664, 936)}, f"got {sorted(w_dims)}")
            combo = Image.open(web_dir / "05_longest_charting_comparison.png")
            check("parity: web-only song comparison is the 1664-wide web canvas",
                  combo.size[0] == 1664, f"got {combo.size}")
        except ImportError:
            pass
    else:
        checks.append("  SKIP  chart parity (outputs/ not rendered on this checkout)")

    # ── Report ────────────────────────────────────────────────────────────
    print("Pre-publish chart-data validation — billboard-hot100 (Hot 100 genre & song trends)")
    print("=" * 64)
    for line in checks:
        print(line)
    for line in failures:
        print(line)
    print("=" * 64)
    if failures:
        print(f"RESULT: {len(failures)} FAILURE(S) — DO NOT PUBLISH.")
        return 1
    n_pass = len([c for c in checks if "PASS" in c])
    print(f"RESULT: all {n_pass} checks passed — safe to publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
