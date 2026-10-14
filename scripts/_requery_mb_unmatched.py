#!/usr/bin/env python
"""One-off helper: re-query the UNMATCHED MusicBrainz artists with normalized names.

The first enrichment pass queried MusicBrainz with the raw Billboard credit string
and an exact-quoted Lucene query, leaving 1,281 of 4,427 enrichment artists
unmatched (credit formatting + the strict query form). This re-queries ONLY those
with `normalize_artist_for_mb()` (primary-artist extraction + curated alias map) and
a forgiving unquoted query, appending improved records to the SAME resumable cache
(data/raw/mb_artist_cache.jsonl, keyed by the original Billboard name).

Fully resumable: re-run until it reports no remaining first-attempt unmatched.

Usage:  .venv/bin/python scripts/_requery_mb_unmatched.py
"""
import os
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

from src.ingest import load_config, requery_unmatched_mb  # noqa: E402

if __name__ == "__main__":
    cfg = load_config("config.yaml")
    t0 = time.time()
    summary = requery_unmatched_mb(cfg, rate_limit_seconds=1.3, progress_every=25)
    print("SUMMARY", summary)
    print(f"ELAPSED_MIN {(time.time() - t0) / 60:.1f}")
    print("RE-QUERY COMPLETE")
