# billboard-hot100 — Dataset Codebook
Generated: 2026-10-15

## Columns

### `year`
- **Type**: `int32`
- **Non-null**: 751 / 751 (100.0%)
- **Description**: Calendar year of the Billboard Hot 100 weekly charts (1958–2026).

### `genre`
- **Type**: `str`
- **Non-null**: 751 / 751 (100.0%)
- **Description**: Aggregate genre bucket (one of 12: Pop, Rock, Hip-Hop/Rap, R&B/Soul, Country, Dance/Electronic, Latin, Folk, Jazz, Blues, Metal, Other/Unknown), assigned per ARTIST from the artist's single highest-count non-noise MusicBrainz tag (top-tag-wins).

### `appearances`
- **Type**: `int64`
- **Non-null**: 751 / 751 (100.0%)
- **Description**: Count of weekly Hot 100 chart slots held that year by artists of that genre (one slot = one song on one weekly chart; a song in the Top 100 for 10 weeks counts 10).

### `share`
- **Type**: `float64`
- **Non-null**: 751 / 751 (100.0%)
- **Description**: The genre's appearances as a percent (0–100) of that year's total chart slots; all genres in a year sum to ~100.

### `rank`
- **Type**: `int64`
- **Non-null**: 751 / 751 (100.0%)
- **Description**: The genre's rank that year by appearances (dense rank, 1 = most appearances). Ties share a rank; the next rank is not skipped.

## Notes

billboard-hot100 — genre rank over time (v1)

WHAT THIS IS
Genre presence on the Billboard Hot 100, 1958–2026, as yearly counts, shares,
and ranks across 12 aggregate genres. Built to answer: how have music genres
risen and fallen at the top of the Hot 100 over the decades?

HOW GENRE IS ASSIGNED (and its limits)
Billboard carries no genre. Genre is derived at the ARTIST level from
MusicBrainz crowd-sourced tags: each artist is bucketed by its single
highest-MB-count non-noise tag ("top tag wins"). An artist's WHOLE catalog
therefore counts as that one genre for every chart week — a song is not
genre-tagged individually. Crossover superstars whose top MB tag is "pop"
(e.g. Michael Jackson, Beyoncé, Taylor Swift) read as Pop, so Pop runs larger
and the roots genres smaller than a lineage-based taxonomy would.

OTHER/UNKNOWN CAVEAT
Other/Unknown = chart slots whose artist has no usable genre, which is the sum
of (a) artists MusicBrainz matched but with no genre-bearing tag and (b) the
long tail of artists with fewer than 20 Hot 100 appearances, who were below
the enrichment threshold and never genre-looked-up. It is a coverage residual,
not a musical category; it is kept in the data for honesty but excluded from
the headline genre rank race.

SERIES BREAK
Billboard's Hot 100 methodology changed over the decades (sales + radio
airplay historically; digital downloads folded in 2005, streaming from 2007
and progressively weighted through the 2010s), so chart presence is not
measured identically across eras.

PII: none. Public chart data + a crowd-sourced artist→genre mapping.

Sources: Billboard Hot 100 full chart history (mhollingshead/billboard-hot-100,
GitHub; underlying chart © Billboard, non-commercial research use) and
MusicBrainz Web Service v2 artist tags (CC0 / CC-BY-NC-SA). See SOURCES.md.
