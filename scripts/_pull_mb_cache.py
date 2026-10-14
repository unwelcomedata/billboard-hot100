#!/usr/bin/env python
"""One-off helper: pre-warm the resumable MusicBrainz artist-genre cache.

Runs the same ingest the notebook calls, so the slow (~1 req/sec) MusicBrainz
pull can proceed in the background. The cache (data/raw/mb_artist_cache.jsonl)
makes it resumable — the notebook later reuses it instantly.

Usage:  .venv/bin/python scripts/_pull_mb_cache.py [min_appearances]
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from src.ingest import load_config, ingest_hot100, ingest_musicbrainz_genres  # noqa: E402

if __name__ == "__main__":
    min_app = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    import os
    os.chdir(PROJECT)
    cfg = load_config("config.yaml")
    df = ingest_hot100(cfg)
    ingest_musicbrainz_genres(
        cfg, df, min_appearances=min_app, rate_limit_seconds=1.1, progress_every=50
    )
    print("BACKGROUND PULL COMPLETE")
